# Technical Specification: Quote Data Quality — Staleness Detection & Mitigation

**Date:** 2026-02-18  
**Author:** Backend Planner (Coordinator research)  
**Status:** Draft — awaiting Clay approval  
**Scope:** `polygon_adapter.py`, `protocol.py`, `unified.py`, `warrior_callbacks.py`

---

## Problem Statement

Polygon's `/v2/snapshot` API returns `lastTrade.p` as the primary price. For illiquid tickers (e.g., LRHC), this trade can be **minutes or hours old** while the NBBO bid/ask (`lastQuote`) updates in real time. Our adapter currently:

1. **Masks staleness** by stamping `datetime.now(timezone.utc)` (not the actual trade time)
2. **Uses stale price** for entry decisions, stop calculations, and exit limit prices
3. **Provides no warning** when only one quote source is available in `unified.py`

**Impact:** The LRHC exit on 2026-02-18 used a $1.78 lastTrade price while the bid/ask midpoint was ~$2.17 — a 23% deviation that resulted in a suboptimal limit price.

---

## Root Cause Analysis

### Bug 1: Fake Timestamps in `polygon_adapter.py`

Three methods set `timestamp=datetime.now(timezone.utc)` instead of the real trade time:

| Method | Line | Polygon Field Available |
|--------|------|------------------------|
| `get_quote()` | L127 | `lastTrade.t` (nanosecond SIP timestamp) |
| `get_last_trade()` | L180 | `results.t` (nanosecond SIP timestamp) |
| `get_quotes_batch()` | L228 | `lastTrade.t` per ticker (nanosecond SIP timestamp) |

**Polygon API:** `lastTrade.t` is a **nanosecond Unix timestamp** (SIP time). `lastQuote.t` is also available.

### Bug 2: No Bid/Ask Midpoint Fallback

When `lastTrade` is stale, the adapter should use the NBBO midpoint as a more current price estimate.  
Currently, `bid` and `ask` are extracted (L124-125) but only stored — never used as a price fallback.

### Bug 3: Single-Source Silent Acceptance in `unified.py`

At [unified.py L224-244](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/market_data/unified.py#L224-L244), if only Polygon is available:
```python
if len(prices) == 1:
    source, price = list(prices.items())[0]
    if source == "Polygon":
        return _log_and_return(polygon_quote, "Polygon", 0.0)
```
No warning is logged that cross-validation was impossible.

---

## Proposed Changes

### Change 1: Propagate Real Timestamp in `polygon_adapter.py`

#### [MODIFY] [polygon_adapter.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/market_data/polygon_adapter.py)

**a) Add a helper to parse nanosecond timestamps:**

```python
def _parse_polygon_timestamp(ns_timestamp) -> datetime:
    """Convert Polygon nanosecond Unix timestamp to datetime (UTC).
    
    Polygon API returns timestamps in nanoseconds since epoch.
    Falls back to datetime.now(UTC) if parsing fails.
    """
    if not ns_timestamp:
        return datetime.now(timezone.utc)
    try:
        # Nanoseconds → seconds
        seconds = int(ns_timestamp) / 1_000_000_000
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return datetime.now(timezone.utc)
```

**b) Update `get_quote()` (L127):**

```diff
-            timestamp=datetime.now(timezone.utc),
+            timestamp=self._parse_polygon_timestamp(last_trade.get("t")),
```

**c) Update `get_last_trade()` (L180):**

```diff
-            timestamp=datetime.now(timezone.utc),
+            timestamp=self._parse_polygon_timestamp(result.get("t")),
```

**d) Update `get_quotes_batch()` (L228):**

```diff
-                timestamp=datetime.now(timezone.utc),
+                timestamp=self._parse_polygon_timestamp(last_trade.get("t")),
```

---

### Change 2: Bid/Ask Midpoint Fallback When `lastTrade` Is Stale

#### [MODIFY] [polygon_adapter.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/market_data/polygon_adapter.py)

In `get_quote()` (after building the Quote), add staleness detection:

```python
STALE_TRADE_THRESHOLD_SECONDS = 120  # 2 minutes

def get_quote(self, symbol: str) -> Optional[Quote]:
    # ... existing snapshot fetch ...
    
    trade_timestamp = self._parse_polygon_timestamp(last_trade.get("t"))
    trade_age_seconds = (datetime.now(timezone.utc) - trade_timestamp).total_seconds()
    
    # Primary price: lastTrade
    price = last_trade.get("p") or day.get("c") or 0
    bid_price = last_quote.get("p", 0) or 0
    ask_price = last_quote.get("P", 0) or 0
    
    # STALENESS FALLBACK: Use bid/ask midpoint if lastTrade is old
    price_source = "lastTrade"
    if trade_age_seconds > STALE_TRADE_THRESHOLD_SECONDS and bid_price > 0 and ask_price > 0:
        midpoint = (float(bid_price) + float(ask_price)) / 2
        # Only use midpoint if it meaningfully differs from lastTrade
        if abs(midpoint - float(price)) / float(price) > 0.01:  # >1% deviation
            logger.warning(
                f"[Polygon] {symbol}: lastTrade is {trade_age_seconds:.0f}s old "
                f"(${price:.2f}), using bid/ask midpoint ${midpoint:.2f} "
                f"(bid=${bid_price:.2f}, ask=${ask_price:.2f})"
            )
            price = midpoint
            price_source = "midpoint"
    
    # ... build and return Quote with real timestamp ...
```

Apply similar logic in `get_quotes_batch()`.

> [!IMPORTANT]
> The midpoint fallback should **only** activate during market hours. Pre-market and after-hours quotes can have wide spreads where the midpoint is unreliable. Add a market-hours guard.

---

### Change 3: Quote Age Field on `Quote` Dataclass

#### [MODIFY] [protocol.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/market_data/protocol.py)

Add an optional `quote_age_seconds` field so consumers can inspect freshness without computing it:

```diff
 @dataclass
 class Quote:
     """Real-time quote data."""
     symbol: str
     price: Decimal
     change: Decimal
     change_percent: Decimal
     volume: int
     timestamp: datetime
     day_low: Optional[Decimal] = None
     day_high: Optional[Decimal] = None
     bid: Optional[Decimal] = None
     ask: Optional[Decimal] = None
     year_high: Optional[Decimal] = None
     year_low: Optional[Decimal] = None
+    quote_age_seconds: Optional[float] = None  # Age of lastTrade at fetch time
+    price_source: Optional[str] = None  # "lastTrade" | "midpoint" | "day_close"
```

**Why:** Downstream consumers (scanner, entry guards, exit logic) can check `quote.quote_age_seconds` without reimplementing timestamp math. The `price_source` field makes it explicit when a midpoint fallback was used.

---

### Change 4: Single-Source Warning in `unified.py`

#### [MODIFY] [unified.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/market_data/unified.py)

At L224, before returning the single-source quote:

```diff
 if len(prices) == 1:
     source, price = list(prices.items())[0]
-    logger.debug(f"[Quote] {symbol}: Only {source} available (${price:.2f})")
+    logger.warning(
+        f"[Quote] {symbol}: SINGLE SOURCE only ({source}, ${price:.2f}) — "
+        f"no cross-validation possible"
+    )
     if source == "Polygon":
+        # Propagate staleness info if available
+        if polygon_quote and polygon_quote.quote_age_seconds and polygon_quote.quote_age_seconds > 120:
+            logger.warning(
+                f"[Quote] {symbol}: Polygon lastTrade is {polygon_quote.quote_age_seconds:.0f}s old — "
+                f"price may be stale for illiquid ticker"
+            )
         return _log_and_return(polygon_quote, "Polygon", 0.0)
```

---

## Change Surface Enumeration

### All Sites That Use Quote Data

| # | File | Line(s) | Usage | Staleness Risk | Action Needed |
|---|------|---------|-------|----------------|---------------|
| 1 | `polygon_adapter.py` | L127 | `get_quote` — sets `timestamp=now()` | **Critical** — masks real age | Fix: propagate `lastTrade.t` |
| 2 | `polygon_adapter.py` | L180 | `get_last_trade` — sets `timestamp=now()` | **Critical** | Fix: propagate `results.t` |
| 3 | `polygon_adapter.py` | L228 | `get_quotes_batch` — sets `timestamp=now()` | **Critical** | Fix: propagate `lastTrade.t` |
| 4 | `unified.py` | L106-109 | Polygon+Schwab agree → return Polygon | Medium | OK if Polygon timestamp is now real |
| 5 | `unified.py` | L224-244 | Single source → return without warning | **High** | Fix: add warning log |
| 6 | `unified.py` | L321-329 | `get_quotes_batch` → Polygon directly | Medium | OK once adapter is fixed |
| 7 | `warrior_callbacks.py` | L106-116 | `create_get_quote` → returns `float(quote.price)` only | **High** — discards timestamp | Phase 2: return `(price, age)` tuple |
| 8 | `warrior_callbacks.py` | L434-451 | Stale guard (bidirectional) | Low | Already fixed in recent PR |
| 9 | `warrior_scanner_service.py` | L668 | `unified_quote` for gap recalc | Medium | OK once adapter is fixed |
| 10 | `warrior_engine_entry.py` | L352 | `get_quote(symbol)` for entry trigger | **High** — entry on stale data | Phase 2: check `quote_age_seconds` |
| 11 | `warrior_monitor_exit.py` | L62-136 | `_get_price_with_fallbacks` chain | Medium | OK — already has multi-source fallback |
| 12 | `trade_event_service.py` | L135 | `umd.get_quote("SPY")` for market context | Low | Non-trading, informational only |

---

## Risk Assessment

### What Could Go Wrong

| Risk | Likelihood | Severity | Mitigation |
|------|-----------|----------|------------|
| Polygon changes `lastTrade.t` format | Low | Medium | `_parse_polygon_timestamp` has try/except fallback to `now()` |
| Midpoint uses wide spread as price | Medium | High | Only activate during market hours; require spread < 5% |
| Midpoint flash crashes on thin bid | Low | High | Require both bid > 0 AND ask > 0 AND spread < 5% |
| `quote_age_seconds` breaks downstream | Low | Low | Optional field with default `None` — backward compatible |
| Pre-market wide spreads create bad midpoints | Medium | High | **Guard: skip midpoint before 9:30 AM ET** |

### Pre-Market Guard for Midpoint

```python
# Only use midpoint during regular market hours
from nexus2.utils.time_utils import is_market_hours
if is_market_hours() and trade_age_seconds > STALE_TRADE_THRESHOLD_SECONDS:
    # ... midpoint logic ...
```

If `is_market_hours()` doesn't exist, we need to add it or use the existing time check pattern from `warrior_scanner_service.py` (L584-587):

```python
import pytz
et = pytz.timezone("US/Eastern")
current_et = datetime.now(et)
is_regular_hours = (current_et.hour >= 9 and current_et.minute >= 30) or current_et.hour >= 10
```

---

## Phasing

### Phase 1 (This PR) — Foundation

1. Add `_parse_polygon_timestamp()` helper
2. Propagate real timestamps in all 3 methods (L127, L180, L228)
3. Add `quote_age_seconds` and `price_source` to `Quote` dataclass
4. Implement bid/ask midpoint fallback with market-hours guard
5. Add single-source warning in `unified.py`

### Phase 2 (Future) — Consumer Awareness

1. Modify `create_get_quote` to return `(price, age)` tuple or a richer object
2. Add `quote_age_seconds` checks in `warrior_engine_entry.py` before entry
3. Add quote age telemetry (log distribution of quote ages to telemetry DB)
4. Scanner gap recalc: warn when unified quote is stale

> [!NOTE]
> Phase 2 touches many consumer files and requires coordination with the trading engine.
> Phase 1 is self-contained within the adapter and protocol layers.

---

## Verification Plan

### Automated Tests

**New test file:** `tests/unit/adapters/test_polygon_quote_freshness.py`

```
pytest tests/unit/adapters/test_polygon_quote_freshness.py -v
```

Test cases:
1. `test_parse_polygon_timestamp_valid` — nanosecond timestamp → correct datetime
2. `test_parse_polygon_timestamp_none` — `None` → falls back to `now()`
3. `test_parse_polygon_timestamp_invalid` — bad value → falls back to `now()`
4. `test_get_quote_propagates_real_timestamp` — mock snapshot with `lastTrade.t` → Quote.timestamp matches
5. `test_get_quote_midpoint_fallback` — stale lastTrade + valid bid/ask → price = midpoint
6. `test_get_quote_no_midpoint_premarket` — stale lastTrade + valid bid/ask but pre-market → price = lastTrade (no fallback)
7. `test_get_quotes_batch_timestamps` — batch snapshot → all quotes have real timestamps
8. `test_quote_age_seconds_calculated` — verify `quote_age_seconds` field is populated

### Existing Tests (Regression)

```
pytest tests/unit/ -v --tb=short
```

Run full unit suite to catch any breakage from the new optional fields.

### Manual Verification

1. **Live smoke test** during market hours:
   - Start the backend server
   - Call `GET /api/quotes/AAPL` and verify `timestamp` is NOT current wall clock
   - Call `GET /api/quotes/batch?symbols=AAPL,MSFT` and verify timestamps differ per symbol
   - Find an illiquid ticker and verify midpoint fallback logs appear

---

## Summary of Files Changed

| File | Type | Lines Changed |
|------|------|---------------|
| `polygon_adapter.py` | MODIFY | ~30 lines added/modified (helper + 3 timestamp fixes + midpoint logic) |
| `protocol.py` | MODIFY | 2 lines added (new optional fields) |
| `unified.py` | MODIFY | ~8 lines modified (single-source warning + age check) |
| `test_polygon_quote_freshness.py` | NEW | ~120 lines (8 test cases) |
