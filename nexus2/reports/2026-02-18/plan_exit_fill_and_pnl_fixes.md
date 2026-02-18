# Implementation Plan: Exit Fill Recording & P&L Accuracy Fixes

## Problem Statement

Today's trades revealed two bugs and one critical data issue:

1. **BUG (P0): Exit fill poll calls non-existent method** — `warrior_callbacks.py:470` calls `alpaca.get_order(order_id)` but `AlpacaBroker` only has `get_order_status()`. This throws `AttributeError`, caught silently, causing ALL exit fills to fall back to the limit price instead of the actual Alpaca fill.

2. **BUG (P0): Exit quote data fundamentally wrong** — LRHC sell at limit $1.76 filled at $2.17 (**41¢ / 23% gap**). The bot computed `current_price ≈ $1.78` when actual was $2.17. Earlier exits (BENF/UGRO/AUUD) showed 1-3¢ gaps which could be the offset, but LRHC proves the quote path can return wildly incorrect data.

3. **BUG (P2): Slippage labels inverted for exits** — The `log_warrior_exit_fill_confirmed` function labels slippage direction incorrectly for sells.

### LRHC Trade Evidence (2026-02-18)

| Order | Limit | Fill | Gap | Source |
|-------|-------|------|-----|--------|
| BUY 10 | $2.08 | $2.06 | 2¢ | bot |
| SELL 5 | $2.23 | $2.232 | ~0¢ | bot |
| SELL 5 | $1.76 | $2.17 | **41¢** | - |

> [!CAUTION]
> **Evidence base for all findings below was verified via `view_file` on actual code.** No claims are assumed.

---

## Root Cause Analysis (Code Evidence)

### Bug 1: `get_order` doesn't exist

**File:** [warrior_callbacks.py:470](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/api/routes/warrior_callbacks.py#L470)

```python
filled_order = alpaca.get_order(order_id)  # ← DOES NOT EXIST
```

**File:** [alpaca_broker.py:409-423](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/broker/alpaca_broker.py#L409-L423)

```python
def get_order_status(self, broker_order_id: str) -> BrokerOrder:  # ← CORRECT METHOD
```

The exception handler at L475 catches `AttributeError` and **breaks** immediately — no retries, straight to limit price fallback at L479.

### Bug 2: Slippage semantics swapped

**File:** [trade_event_service.py:659-676](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/trade_event_service.py#L659-L676)

```python
slippage_cents = float((actual_price - intended_price) * 100)
# For exits: actual < intended → negative → labeled "better"
# But for SELLS, lower actual = WORSE
```

### Working reference: Entry fill poll

**File:** [warrior_entry_execution.py:200-231](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_entry_execution.py#L200-L231)

Entry polling uses `engine._get_order_status()` correctly (5 attempts × 0.5s), checks `filled_avg_price` via `BrokerOrder` attributes, and properly updates the fill price. This is the pattern the exit poll should mirror.

---

## Proposed Changes

### Component 1: Backend (Exit Fill Fix)

#### [MODIFY] [warrior_callbacks.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/api/routes/warrior_callbacks.py)

**Change 1 (L470):** Fix method call from `alpaca.get_order()` → `alpaca.get_order_status()`

```diff
-                        filled_order = alpaca.get_order(order_id)
-                        if hasattr(filled_order, 'filled_avg_price') and filled_order.filled_avg_price:
-                            actual_fill_price = float(filled_order.filled_avg_price)
+                        filled_order = alpaca.get_order_status(order_id)
+                        if filled_order.avg_fill_price and float(filled_order.avg_fill_price) > 0:
+                            actual_fill_price = float(filled_order.avg_fill_price)
```

Note: `BrokerOrder` dataclass uses `avg_fill_price` (Decimal), not `filled_avg_price`. Verify at [protocol.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/broker/protocol.py).

**Change 2 (L467):** Increase poll attempts from 4 to 8 (4 seconds total) and don't break on poll errors:

```diff
-                for _ in range(4):
+                for attempt in range(8):
                     await asyncio.sleep(0.5)
                     try:
                         filled_order = alpaca.get_order_status(order_id)
-                        if hasattr(filled_order, 'filled_avg_price') and filled_order.filled_avg_price:
-                            actual_fill_price = float(filled_order.filled_avg_price)
+                        if filled_order.avg_fill_price and float(filled_order.avg_fill_price) > 0:
+                            actual_fill_price = float(filled_order.avg_fill_price)
                             print(f"[Warrior] {symbol} filled @ ${actual_fill_price:.2f}")
                             break
                     except Exception as poll_err:
-                        print(f"[Warrior] Poll error: {poll_err}")
-                        break
+                        print(f"[Warrior] Poll attempt {attempt+1} error: {poll_err}")
+                        continue  # Retry, don't break
```

**Change 3 (L479):** Add warning when falling back to limit price:

```diff
 exit_price = actual_fill_price if actual_fill_price else float(limit_price)
+if not actual_fill_price:
+    print(f"[Warrior] ⚠️ {symbol}: Fill poll failed after 8 attempts, using limit ${limit_price:.2f} as exit price")
```

---

#### [MODIFY] [trade_event_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/trade_event_service.py)

**Change 4 (L659-676):** Fix slippage direction for exits.

For sells: `actual > intended` is BETTER (got more money), `actual < intended` is WORSE.
Current formula `(actual - intended)` says negative = better, which is incorrect for sells.

The semantics of `intended_price` and `actual_price` in `log_warrior_exit_fill_confirmed`:
- `intended_price` = `signal.exit_price` (price when exit triggered)
- `actual_price` = `actual_exit_price` (broker confirmed fill, or limit fallback)

For exits (sells), slippage should be: `intended - actual` (paid less = worse for seller).
But actually, since we SELL, higher actual = better. So:
- `actual > intended` → positive → "better" for sells
- `actual < intended` → negative → "worse" for sells

The current formula `(actual - intended)` is actually CORRECT in sign, but the labels are WRONG:
```python
if slippage_cents > 0:   # actual > intended = BETTER for sells
    slip_str = f"{slippage_cents:.1f}¢ worse"   # ← WRONG LABEL
elif slippage_cents < 0:  # actual < intended = WORSE for sells  
    slip_str = f"{abs(slippage_cents):.1f}¢ better"  # ← WRONG LABEL
```

Fix: Swap the labels for EXIT fill events.

---

### Component 2: Backend (Post-Trade Reconciliation)

#### [NEW] Add a reconciliation utility or scheduled check

After trading hours, compare all EXIT_FILL_CONFIRMED events for the day against Alpaca's `get_filled_orders()` and flag/correct discrepancies.

This is a safety net for when the exit fill poll times out. The backend agent should determine the best approach (scheduled job, API endpoint, or manual script).

---

### Component 3: Code Audit (Data Freshness — P0)

Investigate why the bot's quote data was $0.41 wrong for LRHC:

**Key questions:**
- What does `UnifiedMarketData.get_quote()` return? What sources, caching, TTL?
- Why did the bot see $1.78 for LRHC when actual was $2.17? (23% error)
- LRHC sell 2 was at 8:00:04 AM — race condition at market open? Premarket vs RTH price?
- The code at L436-439 guards UPWARD stale quotes (`current_price > signal_price * 1.05`) but has **NO guard for downward stale** (LRHC case)

**Starting points:**
- `warrior_callbacks.py:106-116` — `create_get_quote` using `UnifiedMarketData`
- `warrior_callbacks.py:434` — `current_price = await get_quote_fn(symbol)`
- `warrior_callbacks.py:436-439` — upward-only stale guard

See full investigation handoff: `handoff_auditor_exit_quote_freshness.md`

---

## Verification Plan

### Automated Tests

1. **Unit test: exit fill poll uses correct method**
   - Mock `AlpacaBroker.get_order_status()` to return a `BrokerOrder` with `avg_fill_price`
   - Verify `execute_exit` returns `actual_exit_price` matching the mock fill, not the limit
   - Command: `cd nexus2; python -m pytest tests/unit/broker/ -v -k "exit_fill" --no-header`

2. **Unit test: slippage label direction**  
   - Call `log_warrior_exit_fill_confirmed` with known intended/actual prices
   - Verify the reason string labels "better"/"worse" correctly for sells
   - Command: `cd nexus2; python -m pytest tests/unit/ -v -k "exit_slippage" --no-header`

3. **Regression test: entry fill still works**
   - Ensure the entry fill flow is not affected by changes
   - Command: `cd nexus2; python -m pytest tests/ -v -k "fill_confirmed" --no-header`

### Manual Verification

4. **Live observation**: After deploying, monitor the next trading day's exit events in Data Explorer:
   - Verify EXIT_FILL_CONFIRMED events show `actual_price` matching Alpaca's `Avg. Fill Price`
   - Verify the slippage labels ("better"/"worse") are semantically correct for sells
   - Verify the P&L values match `(actual_fill - entry_fill) × shares`

---

## Agent Assignments

| Agent | Scope | Files |
|-------|-------|-------|
| **Backend Specialist** | Fix exit fill poll method, increase retries, fix slippage labels | `warrior_callbacks.py`, `trade_event_service.py` |
| **Code Auditor** | Investigate data freshness: trace quote path, check UnifiedMarketData caching | `warrior_callbacks.py`, `unified.py`, adapters |
| **Testing Specialist** | Write unit tests for exit fill and slippage fixes | `tests/unit/broker/`, `tests/unit/` |

### Handoff Sequence
1. Backend Specialist + Code Auditor can run **in parallel** (different files)
2. Testing Specialist runs **after** Backend Specialist completes
3. Coordinator reviews all outputs
