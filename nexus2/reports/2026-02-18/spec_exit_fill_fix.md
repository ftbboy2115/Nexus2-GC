# Technical Spec: Exit Fill Recording Fix

**Date:** 2026-02-18
**Author:** Backend Planner
**For:** Backend Specialist
**Priority:** P0 — Affects every live exit; LRHC lost ~$2 per share in recorded P&L

---

## Problem Summary

Two compounding bugs cause every Warrior exit to record the **limit price** as the exit price instead of the actual Alpaca fill price. Additionally, stale quote data can cause the limit price to be wildly wrong (LRHC: limit $1.76 vs actual fill $2.17 — a 23% gap).

### LRHC Timeline (2026-02-18)

| Event | Price | Source |
|-------|-------|--------|
| BUY 10 @ limit $2.08 | filled $2.06 | Alpaca |
| SELL 5 @ limit $2.23 | filled $2.232 | Alpaca |
| SELL 5 @ limit **$1.76** | filled **$2.17** | Alpaca |

The second sell had a 23% gap between the bot's limit and the actual fill. Both bugs contributed.

---

## Bug 1: Fill Polling Always Skipped (P0)

### Root Cause

**File:** [warrior_callbacks.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_callbacks.py#L462-L479)

```python
# Line 465 — THE BUG
order_id = str(order.id) if hasattr(order, 'id') else None
```

`order` is a `BrokerOrder` dataclass. `BrokerOrder` has **no `.id` attribute** — the correct field is `.broker_order_id`.

**Evidence:** [protocol.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/broker/protocol.py#L26-L62)

```python
@dataclass
class BrokerOrder:
    client_order_id: UUID       # Our order ID
    broker_order_id: str        # Broker's ID  ← THIS IS THE CORRECT FIELD
    symbol: str
    # ... NO 'id' field exists
```

**Impact:** `hasattr(order, 'id')` → `False` → `order_id = None` → the entire `if order_id:` block (L466-477) is **skipped** → polling never executes → `actual_fill_price` is always `None` → **fallback to `limit_price` at L479**.

### Proof: Entry Code Handles This Correctly

**File:** [warrior_entry_execution.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_execution.py#L152-L157)

```python
# Lines 152-155 — THE CORRECT PATTERN
if hasattr(order_result, 'id'):
    broker_order_id = str(order_result.id)
elif hasattr(order_result, 'broker_order_id'):    # ← Fallthrough handles BrokerOrder
    broker_order_id = order_result.broker_order_id
```

The entry polling code handles the same pattern correctly. The exit polling was written with the wrong attribute name and no fallthrough.

### Fix

```diff
# warrior_callbacks.py, Line 465
-            order_id = str(order.id) if hasattr(order, 'id') else None
+            order_id = order.broker_order_id if hasattr(order, 'broker_order_id') else None
```

---

## Bug 2: Stale Quote → Wrong Limit Price (P1)

### Root Cause Chain

The exit limit price is constructed from a potentially stale quote, then offset downward. The full chain:

1. **Exit signal carries stale `exit_price`:** Monitor's `evaluate_position()` uses the `prefetched_price` (batch quote) as `current_price`. The exit signal's `exit_price` field is set to this `current_price` at signal creation time ([warrior_monitor_exit.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py) — all `WarriorExitSignal(exit_price=current_price, ...)` constructions).

2. **`create_execute_exit` re-fetches quote but has an upward-only stale guard:**

   **File:** [warrior_callbacks.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_callbacks.py#L433-L439)

   ```python
   # Lines 433-439
   current_price = await get_quote_fn(symbol)       # ← Fresh quote from Polygon/UMD
   signal_price = float(signal.exit_price)           # ← Stale price from signal
   if current_price is None:
       current_price = signal_price
   elif current_price > signal_price * 1.05:         # ← STALE GUARD: caps upward movement
       current_price = signal_price                   # ← Clips to stale price!
   ```

   **The problem:** If the stock is spiking UP (LRHC was at $2.17 per Alpaca), but the signal carried `exit_price=$1.78` from a stale quote, then:
   - Fresh quote returns `$2.17`
   - Guard checks: `$2.17 > $1.78 * 1.05 = $1.869` → **True** → clips back to stale `$1.78`

   This guard was designed to prevent selling at an artificially high price, but it also prevents selling at the REAL higher price when the original quote was stale.

3. **Offset applied to already-stale price:**

   ```python
   # Lines 444-449 — for mental_stop/technical_stop:
   offset = 0.99                # 1% below "current" price
   limit_price = round(current_price * offset, 2)    # $1.78 * 0.99 = $1.76
   ```

   This is how the $1.76 limit was computed: stale $1.78 × 0.99 = $1.76.

4. **Bug 1 prevents fix:** Even though Alpaca filled at $2.17, Bug 1 means the system can't poll for it and falls back to `$1.76`.

### The Cascade

```
Signal exit_price = $1.78 (stale batch quote from monitor)
    ↓
get_quote_fn returns $2.17 (fresh, correct)
    ↓
Stale guard: $2.17 > $1.78 * 1.05 = $1.87 → clips to $1.78  ← BUG
    ↓
Offset: $1.78 * 0.99 = $1.76  ← limit sent to Alpaca
    ↓
Alpaca fills at $2.17 (market was actually there)
    ↓
Bug 1: poll fails → recorded exit = $1.76 instead of $2.17  ← WRONG P&L
```

### Fix Recommendation

The stale guard at L438 needs to be rethought. Several options:

**Option A (Recommended): Trust the fresh quote, remove the guard entirely**
```diff
- elif current_price > signal_price * 1.05:
-     current_price = signal_price
```
Rationale: The fresh Polygon quote is real-time. The signal's `exit_price` is from seconds ago and may be stale. Trusting the live quote is strictly better. If the Polygon quote is wrong, the Alpaca limit order will simply not fill (protective by nature).

**Option B: Use a wider guard (e.g., 15%)**
```diff
- elif current_price > signal_price * 1.05:
+ elif current_price > signal_price * 1.15:
```
Less aggressive clipping — only clips truly anomalous quotes.

**Option C: Log the discrepancy but use the fresh quote**
```python
if current_price > signal_price * 1.05:
    logger.warning(
        f"[Warrior] {symbol}: Fresh quote ${current_price:.2f} is "
        f"{((current_price / signal_price) - 1) * 100:.1f}% above signal ${signal_price:.2f} — using fresh"
    )
# Don't clip — use fresh quote
```

> [!IMPORTANT]
> **Option A is recommended** because any stale guard that clips the price DOWN hurts us when the stock is moving up rapidly (which is exactly when we're most likely to be exiting a winner). The limit order itself is protective — if we set it too high, it just fills at market.

---

## Change Surface

| # | File | Change | Location | Template |
|---|------|--------|----------|----------|
| 1 | `warrior_callbacks.py` | Fix `order.id` → `order.broker_order_id` | L465 | Entry code at `warrior_entry_execution.py:152-155` |
| 2 | `warrior_callbacks.py` | Remove or widen stale guard | L438-439 | N/A |
| 3 | `warrior_callbacks.py` | Add warning log when poll fails | L480-481 | Already exists (L481 added recently) |

---

## Detailed Change Specifications

### Change #1: Fix Order ID Extraction (BUG FIX)

**File:** [warrior_callbacks.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_callbacks.py#L465)

**Current code (L465):**
```python
order_id = str(order.id) if hasattr(order, 'id') else None
```

**Replace with:**
```python
order_id = order.broker_order_id if hasattr(order, 'broker_order_id') else None
```

**Template:** Entry code at `warrior_entry_execution.py:152-155`.

### Change #2: Remove Upward Stale Guard (BUG FIX)

**File:** [warrior_callbacks.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_callbacks.py#L433-L439)

**Current code (L433-439):**
```python
else:
    current_price = await get_quote_fn(symbol)
    signal_price = float(signal.exit_price)
    if current_price is None:
        current_price = signal_price
    elif current_price > signal_price * 1.05:
        current_price = signal_price
```

**Replace with:**
```python
else:
    current_price = await get_quote_fn(symbol)
    signal_price = float(signal.exit_price)
    if current_price is None:
        current_price = signal_price
    elif current_price > signal_price * 1.05:
        logger.warning(
            f"[Warrior] {symbol}: Fresh quote ${current_price:.2f} is "
            f"{((current_price / signal_price) - 1) * 100:.1f}% above "
            f"signal ${signal_price:.2f} — using fresh quote (stale guard removed)"
        )
        # Use fresh quote — limit order is naturally protective
```

### Change #3: Strengthen Poll Failure Warning (ALREADY EXISTS)

**File:** [warrior_callbacks.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_callbacks.py#L480-L481)

The warning at L481 is already in place:
```python
if not actual_fill_price:
    print(f"[Warrior] ⚠️ {symbol}: Fill poll failed after 8 attempts, using limit ${limit_price:.2f} as exit price")
```

This is adequate once Bug 1 is fixed (polling will actually work).

---

## Existing Pattern Analysis

| Pattern | Function | File | Lines | Key Behavior |
|---------|----------|------|-------|--------------|
| Entry fill polling | `poll_for_fill` | `warrior_entry_execution.py` | 169-231 | Uses `engine._get_order_status(broker_order_id)` → checks `avg_fill_price` |
| Entry order ID extraction | `submit_entry_order` | `warrior_entry_execution.py` | 152-157 | Tries `.id`, falls through to `.broker_order_id` |
| Exit fill logging | `log_warrior_exit_fill_confirmed` | `trade_event_service.py` | 643-697 | Logs `intended_price` vs `actual_price` → slippage |
| Exit execution handler | `handle_exit` | `warrior_monitor_exit.py` | 1295-1478 | Gets `actual_exit_price` from `result["actual_exit_price"]` |

**Key observation:** The entry polling at `warrior_entry_execution.py:206` uses:
```python
order_detail = await engine._get_order_status(broker_order_id)
# then:
fill_price = getattr(order_detail, 'avg_fill_price', None)  # ← same field name as BrokerOrder
```

The exit polling at `warrior_callbacks.py:470-471` uses:
```python
filled_order = alpaca.get_order_status(order_id)
if filled_order.avg_fill_price and float(filled_order.avg_fill_price) > 0:
```

**Both use `avg_fill_price`** which is the correct field on `BrokerOrder`. The difference: entry passes a valid `broker_order_id`, while exit passes `None` (because of Bug 1).

---

## Downstream Impact

Once Bug 1 is fixed, the actual fill price flows correctly through the chain:

```
warrior_callbacks.py:execute_exit
    → returns {"order": order, "actual_exit_price": exit_price}

warrior_monitor_exit.py:handle_exit (L1320-1329)
    → actual_exit_price = result["actual_exit_price"]
    → actual_pnl = (actual_exit_price - entry_price) * shares

trade_event_service.py:log_warrior_exit_fill_confirmed (L1373)
    → intended_price = signal.exit_price (quote at signal time)
    → actual_price = actual_exit_price (from broker poll)
```

**No changes needed in `warrior_monitor_exit.py` or `trade_event_service.py`** — they already correctly propagate the `actual_exit_price` returned by `create_execute_exit`.

---

## Wiring Checklist

- [ ] Fix `order.id` → `order.broker_order_id` at `warrior_callbacks.py:465`
- [ ] Remove/replace stale guard at `warrior_callbacks.py:438-439`
- [ ] Verify `alpaca_broker.get_order_status()` returns `BrokerOrder` with `avg_fill_price` field (confirmed at L409-423, L186-210)
- [ ] Run existing unit tests (no exit callback tests exist — see Risk Assessment)
- [ ] Manual verification: deploy and confirm next exit shows polled fill price in logs

---

## Risk Assessment

### What could go wrong
1. **Polling adds 0.5-4s latency** to exit execution. This is acceptable — the entry code has the same pattern and the order is already submitted. Polling happens AFTER submission.
2. **Alpaca rate limits** from 8 polling requests per exit. Unlikely at this frequency (one exit per position). If it occurs, reduce attempts from 8 to 4.
3. **Removing stale guard** could theoretically set a very high limit on a sell order. However, limit sell orders are downward-protective (fills at market if market is above limit), so this is safe.

### What existing behavior might break
- None. The current behavior is **already broken** (always using limit price). Any change is an improvement.

### What to test after implementation
1. **Deploy to VPS** and execute a live exit
2. Verify logs show: `[Warrior] {symbol} filled @ ${actual_fill_price:.2f}`
3. Check that `trade_events` table shows `EXIT_FILL_CONFIRMED` with different `intended_price` and `actual_price`
4. Compare Nexus exit price with Alpaca dashboard to confirm match

### Existing Tests
No existing tests for exit callbacks (`test*callback*`, `test*exit*` — 0 results found). This is a gap but implementing new tests is deferred to the Testing Specialist.

---

## Summary for Implementer

**Two changes, one file:**

1. **Line 465:** Change `order.id` → `order.broker_order_id` (one-liner fix)
2. **Lines 438-439:** Replace stale guard with a warning log (keep fresh quote)

**Total estimated LOC changed:** ~5 lines

**Confidence:** Very high — Bug 1 is a clear attribute name error confirmed by the `BrokerOrder` dataclass definition and the working entry code pattern. Bug 2 stale guard is the documented cause of the LRHC $0.41 gap.
