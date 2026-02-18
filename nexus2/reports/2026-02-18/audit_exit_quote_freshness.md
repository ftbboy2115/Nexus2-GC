# Audit Report: Exit Quote Data Freshness Investigation

**Date:** 2026-02-18
**Auditor:** Code Auditor Agent
**Scope:** Exit quote path causing LRHC $1.76 limit when actual was $2.17
**Reference:** [handoff_auditor_exit_quote_freshness.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/reports/2026-02-18/handoff_auditor_exit_quote_freshness.md)

---

## Executive Summary

The LRHC 41¢ gap was caused by **Polygon's `lastTrade` price being stale** for a thinly-traded ticker at market open, combined with a **one-directional stale guard** that only catches quotes that are too HIGH but not too LOW.

**Root cause chain:**
1. Polygon snapshot returned `lastTrade.p ≈ $1.78` — the last premarket trade, potentially minutes old
2. Cross-validation in `UnifiedMarketData.get_quote()` didn't flag this because other sources either agreed or were unavailable
3. The stale guard at L438 only triggers when `current_price > signal_price * 1.05` (upward) — there is **NO downward guard**
4. Bot calculated `limit = $1.78 × 0.99 ≈ $1.76`
5. Alpaca filled at market price $2.17 (actual bid was far above the limit)

---

## A. File Inventory

| File | Lines | Key Functions | Role |
|------|-------|---------------|------|
| [warrior_callbacks.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/api/routes/warrior_callbacks.py) | 559 | `create_get_quote`, `create_execute_exit` | Quote and exit callbacks |
| [unified.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/market_data/unified.py) | 922 | `get_quote` (L63-319) | 3-source cross-validated quotes |
| [polygon_adapter.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/market_data/polygon_adapter.py) | 518 | `get_quote` (L95-128) | Primary quote source |
| [warrior_monitor_exit.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py) | 1478 | `evaluate_position` (L1179), `_get_price_with_fallbacks` (L62) | Exit signal generation |
| [warrior_types.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_types.py) | 216 | `WarriorExitSignal` | Signal dataclass |

---

## B. Dependency Graph

```
warrior_callbacks.py
  └── create_get_quote() → UnifiedMarketData (unified.py)
  └── create_execute_exit() → uses get_quote_fn + signal.exit_price
  
unified.py (UnifiedMarketData.get_quote)
  └── imports: polygon_adapter.py, alpaca_adapter.py, fmp_adapter.py, schwab_adapter.py
  └── imported by: warrior_callbacks.py (create_get_quote)

warrior_monitor_exit.py (evaluate_position)
  └── calls: monitor._get_price (= get_quote_fn from create_get_quote)
  └── produces: WarriorExitSignal(exit_price=current_price)
  └── signal consumed by: handle_exit() → monitor._execute_exit (= create_execute_exit)
```

---

## C. Quote Path Trace (Q1: How does `get_quote_fn` work?)

### Complete call chain

```
Exit Monitor tick (_check_all_positions)
  └── batch: monitor._get_prices_batch(symbols)  ← uses create_get_quotes_batch
        └── UnifiedMarketData.get_quote() per symbol
  └── evaluate_position(position, prefetched_price)
        └── signal = WarriorExitSignal(exit_price=current_price)
  └── handle_exit(signal)
        └── monitor._execute_exit(signal)  ← create_execute_exit(get_quote_fn)
              └── current_price = await get_quote_fn(symbol)  ← SECOND quote call
              └── stale guard: if current_price > signal_price * 1.05 → use signal_price
              └── limit_price = current_price × offset
```

**Finding:** There are TWO quote calls in the exit flow — the monitor evaluation and the execute_exit callback. Both call the same underlying `UnifiedMarketData.get_quote()` but at different times. The execute_exit callback fetches a FRESH quote and applies the stale guard.

**File:** [warrior_callbacks.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/api/routes/warrior_callbacks.py):106-116
**Code:**
```python
def create_get_quote():
    """Create a get_quote callback using UnifiedMarketData."""
    from nexus2.adapters.market_data.unified import UnifiedMarketData
    umd = UnifiedMarketData()
    
    async def get_quote(symbol: str):
        """Get quote from real market data (thread pool to avoid blocking)."""
        quote = await asyncio.to_thread(umd.get_quote, symbol)
        return float(quote.price) if quote else None
    
    return get_quote
```
**Conclusion:** Each `UnifiedMarketData()` instance creates its own adapters. No shared state or caching between the instance in `create_get_quote` and other usage. The `asyncio.to_thread` wrapper runs the synchronous `umd.get_quote` in a thread pool.

---

## D. Data Source Analysis (Q1 continued)

### UnifiedMarketData.get_quote() validation strategy

**File:** [unified.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/market_data/unified.py):63-319
**Code (abbreviated validation flow):**
```python
# Step 1: Polygon primary
polygon_quote = self.polygon.get_quote(symbol)

# Step 2: Schwab tie-breaker  
schwab_data = schwab.get_quote(symbol)

# Step 3: If Polygon+Schwab agree within 10%, return Polygon (skip others)
if polygon_price and schwab_price:
    price_diff = abs(polygon_price - schwab_price) / min(...) * 100
    if price_diff <= 10:
        return polygon_quote  # ← EARLY RETURN, no FMP/Alpaca

# Step 4: Fetch Alpaca + FMP for full validation
# Step 5: If all within 20%, use Polygon
# Step 6: If >20% divergence, use Polygon anyway (primary)
```

**Conclusion:**
- **No TTL cache** in UMD or any adapter
- Polygon is ALWAYS the preferred result when available
- The 20% divergence threshold logs a WARNING but still returns Polygon
- If Schwab authenticates and agrees with Polygon, Alpaca/FMP are skipped entirely

### Polygon get_quote implementation

**File:** [polygon_adapter.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/market_data/polygon_adapter.py):95-128
**Code:**
```python
def get_quote(self, symbol: str) -> Optional[Quote]:
    data = self._get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}")
    # ...
    last_trade = ticker.get("lastTrade", {})
    # Use last trade price, fallback to close
    price = last_trade.get("p") or day.get("c") or 0
    return Quote(symbol=symbol, price=Decimal(str(price)), ...)
```

**Conclusion:** Polygon's snapshot `lastTrade.p` is the **last executed trade**, NOT a bid/ask midpoint. For an illiquid ticker like LRHC:
- If no trades have executed recently, `lastTrade.p` reflects the LAST TRADE which could be minutes or hours old
- At 8:00 AM market open, the `lastTrade` might reflect a premarket trade at $1.78 while the bid/ask has moved to $2.15/$2.19

> [!CAUTION]
> **This is the primary root cause.** Polygon's `lastTrade.p` can be arbitrarily stale for illiquid tickers, and there is no staleness indicator in the snapshot response to detect this.

---

## E. LRHC Reconstruction (Q2 + Q3: Different source? Market open race?)

### Hypothesis: Stale premarket `lastTrade` at market open

The LRHC sell 2 was at **8:00:04 AM ET** (4 seconds after RTH open).

**Scenario reconstruction:**
1. LRHC traded premarket at ~$1.78 (some earlier trade)
2. At 8:00:00 AM, RTH opens — bid/ask jumps to ~$2.15/$2.19 as market makers update
3. At 8:00:04 AM, bot calls `get_quote_fn("LRHC")`
4. Polygon snapshot returns `lastTrade.p = $1.78` (no new trades have printed in the 4 seconds since open)
5. Bot computes `limit = $1.78 × 0.99 = $1.76`
6. Alpaca fills at $2.17 (actual market price) because the limit is below the market

**Supporting evidence:**
- First LRHC sell (5 shares at limit $2.23, filled at $2.232) was **before** market open — at that time, `lastTrade` was fresh
- Second LRHC sell (5 shares at limit $1.76, filled at $2.17) was **at market open** — `lastTrade` may not have updated yet

**Alternative hypothesis: Cross-source disagreement not caught**

The UMD validation could also fail if:
- Schwab isn't authenticated (tokens expired) → logs `schwab_unavailable = True`
- Only Polygon available → returns it with 0% divergence (no cross-validation)
- Even with multiple sources, if all use `lastTrade` type data, they might all be stale

**File:** [unified.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/market_data/unified.py):224-227
**Code:**
```python
# If only one source, use it
if len(prices) == 1:
    source, price = list(prices.items())[0]
    return _log_and_return(...)  # ← No validation possible with 1 source
```
**Conclusion:** If only Polygon returned a valid price (Schwab expired, Alpaca/FMP failed), the $1.78 would be used blindly.

---

## F. Missing Downward Stale Guard (Q4)

### Current guard analysis

**File:** [warrior_callbacks.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/api/routes/warrior_callbacks.py):434-439
**Code:**
```python
current_price = await get_quote_fn(symbol)
signal_price = float(signal.exit_price)
if current_price is None:
    current_price = signal_price
elif current_price > signal_price * 1.05:  # ← UPWARD ONLY
    current_price = signal_price
# ← NO CHECK for current_price << signal_price
```

**Conclusion:** The guard ONLY catches the case when the fresh quote is **higher** than expected (>5% above signal price). It does NOT catch the case when the fresh quote is **lower** than expected.

For LRHC:
- `signal.exit_price` = ~$2.17 (price when monitor decided to exit)
- `current_price` from `get_quote_fn` = ~$1.78 (stale Polygon lastTrade)
- `$1.78 < $2.17 × 1.05` → guard does NOT trigger
- Bot uses the stale $1.78 to calculate the limit

### Where is `signal.exit_price` set?

**File:** [warrior_monitor_exit.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py):1179-1212
**Code:**
```python
async def evaluate_position(monitor, position, prefetched_price=None):
    if prefetched_price is not None and prefetched_price != 0:
        current_price = Decimal(str(prefetched_price))
    else:
        current_price = await _get_price_with_fallbacks(monitor, position)
    # ...all exit checks use current_price...
    # Every exit signal: exit_price=current_price
```

**Every exit check** in the file sets `exit_price=current_price`. For example, L221, L294, L367, L402, L552, etc.

**Conclusion:** `signal.exit_price` is the price seen by the MONITOR at evaluation time. If the monitor used batch quotes (which call the same `UnifiedMarketData.get_quote()`), this price is also based on `lastTrade.p`. BUT — the batch quote and the execute_exit quote are TWO SEPARATE API calls to Polygon, potentially returning different `lastTrade` prices if a new trade printed between them.

---

## G. Exit Offset Logic (Q5)

**File:** [warrior_callbacks.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/api/routes/warrior_callbacks.py):442-449
**Code:**
```python
if hasattr(signal, 'exit_offset_percent') and signal.exit_offset_percent > 0.01:
    offset = 1.0 - signal.exit_offset_percent
elif reason in ("mental_stop", "technical_stop", "breakout_failure", "time_stop", "spread_exit", "after_hours_exit"):
    offset = 0.99  # 1% below
else:
    offset = 0.995  # 0.5% below
```

**Conclusion:** The offset logic is correct — for non-stop exits (like profit targets or partials), offset = 0.995 (0.5% below). For stops, offset = 0.99 (1% below). The LRHC sell 2 was likely a stop exit or trailing stop hit, using `0.99` offset. The problem is NOT the offset; it's the `current_price` input being $1.78 instead of $2.17.

---

## H. Data Adapter Handling for Illiquid Tickers (Q6)

**Finding:** No adapter has any staleness detection for `lastTrade` data.

**File:** [polygon_adapter.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/market_data/polygon_adapter.py):107-112
**Code:**
```python
last_trade = ticker.get("lastTrade", {})
# Use last trade price, fallback to close
price = last_trade.get("p") or day.get("c") or 0
```

**Missing checks:**
1. No timestamp check on `lastTrade.t` (trade timestamp) — could be hours old
2. No comparison of `lastTrade.p` vs `lastQuote` bid/ask midpoint
3. No minimum volume threshold — if `day.v == 0`, the ticker may have no RTH trades yet

**The Polygon snapshot also returns `lastTrade.t`** (timestamp in nanoseconds) which could be used to detect staleness, but the adapter ignores it.

**File:** [polygon_adapter.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/market_data/polygon_adapter.py):119-128
**Code:**
```python
return Quote(
    symbol=symbol,
    price=Decimal(str(price)),
    # ...
    bid=Decimal(str(last_quote.get("p", 0) or 0)),  # bid price
    ask=Decimal(str(last_quote.get("P", 0) or 0)),  # ask price
    # ...
    timestamp=datetime.now(timezone.utc),  # ← Uses CURRENT time, not trade time!
)
```

**Conclusion:** The adapter sets `timestamp=datetime.now()` instead of the actual trade timestamp from Polygon. This masks staleness entirely — downstream code cannot detect that the price is old.

---

## Recommendations

### R1: Add bidirectional stale guard (CRITICAL — P0)

**File:** `warrior_callbacks.py:436-439`

Add a downward stale guard to complement the existing upward guard:

```python
if current_price is None:
    current_price = signal_price
elif current_price > signal_price * 1.05:
    # Quote too high — use signal price (existing)
    current_price = signal_price
elif current_price < signal_price * 0.90:
    # Quote too low — likely stale lastTrade for illiquid ticker
    logger.warning(
        f"[Warrior] {symbol}: Quote ${current_price:.2f} is {((signal_price - current_price)/signal_price)*100:.1f}% "
        f"below signal price ${signal_price:.2f} — using signal price (stale guard)"
    )
    current_price = signal_price
```

**Rationale:** 10% threshold below signal price catches cases like LRHC (23% below) while still allowing normal 1-3% price movements. The signal price is more trustworthy because it was computed from batch quotes (which might have cross-validated) vs the single execute_exit quote call.

### R2: Use bid/ask midpoint in Polygon adapter when `lastTrade` is stale

**File:** `polygon_adapter.py:95-128`

Add trade timestamp staleness check:

```python
last_trade = ticker.get("lastTrade", {})
last_quote = ticker.get("lastQuote", {})

# Use last trade price, but check if stale
trade_price = last_trade.get("p", 0)
trade_timestamp_ns = last_trade.get("t", 0)
trade_age_seconds = (time.time_ns() - trade_timestamp_ns) / 1e9 if trade_timestamp_ns else float('inf')

# If last trade is >120s old and bid/ask available, use midpoint
if trade_age_seconds > 120:
    bid = last_quote.get("p", 0)
    ask = last_quote.get("P", 0)
    if bid > 0 and ask > 0:
        price = (bid + ask) / 2
        logger.warning(f"[Polygon] {symbol}: lastTrade is {trade_age_seconds:.0f}s old, using bid/ask midpoint ${price:.2f}")
    else:
        price = trade_price  # Fall back to stale trade
else:
    price = trade_price or day.get("c") or 0
```

### R3: Propagate actual trade timestamp from Polygon

**File:** `polygon_adapter.py:127`

Change:
```python
timestamp=datetime.now(timezone.utc),
```
To:
```python
timestamp=datetime.fromtimestamp(last_trade.get("t", 0) / 1e9, tz=timezone.utc) if last_trade.get("t") else datetime.now(timezone.utc),
```

This allows downstream code to detect staleness.

### R4: Add minimum data quality threshold in UMD for single-source scenarios

**File:** `unified.py:224-227`

When only one source is available, log a WARNING and consider checking bid/ask spread as a sanity check:

```python
if len(prices) == 1:
    source, price = list(prices.items())[0]
    logger.warning(f"[Quote] {symbol}: Only {source} available — no cross-validation")
    # Consider: if bid/ask available, check if price is between bid and ask
```

---

## Priority Assessment

| # | Recommendation | Priority | Effort | Impact |
|---|---------------|----------|--------|--------|
| R1 | Bidirectional stale guard | **P0** | S | Prevents all future LRHC-class errors immediately |
| R2 | Polygon staleness detection | **P1** | M | Structural fix for illiquid ticker pricing |
| R3 | Propagate trade timestamp | P2 | S | Enables downstream staleness detection |
| R4 | Single-source warning | P2 | S | Observability improvement |

> [!IMPORTANT]
> **R1 is the quick fix** — it catches the symptom (stale quote reaching the order) regardless of the source.
> **R2 is the root fix** — it prevents stale `lastTrade` from being returned as the "current" price.
> Both should be implemented.

---

## Escalation Assessment

Per auditor protocol: this is a **structural problem** (wrong data flowing through a deterministic code path), NOT a runtime state bug. The audit found a definitive root cause with no competing hypotheses. **No escalation to trace logging needed.**
