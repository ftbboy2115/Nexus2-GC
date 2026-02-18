# Handoff: Backend Specialist — Exit Fill Recording Fix

@.agent/rules/agent-backend-specialist.md

## Verified Facts

### Fact 1: Exit fill poll calls non-existent method
**File:** `nexus2/api/routes/warrior_callbacks.py:470`
**Code:**
```python
filled_order = alpaca.get_order(order_id)
```
**Problem:** `AlpacaBroker` has NO `get_order()` method. It only has `get_order_status()`.
**Verified at:** `nexus2/adapters/broker/alpaca_broker.py:409` → `def get_order_status(self, broker_order_id: str) -> BrokerOrder:`

This causes `AttributeError` on every call, caught by the `except Exception as poll_err` at L475, which immediately `break`s — aborting the poll loop after 0 retries.

### Fact 2: Wrong attribute name on BrokerOrder
**File:** `nexus2/api/routes/warrior_callbacks.py:471`
**Code:**
```python
if hasattr(filled_order, 'filled_avg_price') and filled_order.filled_avg_price:
```
**Problem:** `BrokerOrder` dataclass uses `avg_fill_price`, NOT `filled_avg_price`.
**Verified at:** `nexus2/adapters/broker/protocol.py:40` → `avg_fill_price: Optional[Decimal] = None`

Even if `get_order` existed, this `hasattr` check would return `False` on the `BrokerOrder` object.

### Fact 3: Poll break on error
**File:** `nexus2/api/routes/warrior_callbacks.py:475-477`  
```python
except Exception as poll_err:
    print(f"[Warrior] Poll error: {poll_err}")
    break  # ← Gives up after first error
```

### Fact 4: Fallback to limit price
**File:** `nexus2/api/routes/warrior_callbacks.py:479`
```python
exit_price = actual_fill_price if actual_fill_price else float(limit_price)
```
Since poll always fails (Fact 1+2), `actual_fill_price` is always `None`, so every exit uses the limit price.

### Fact 5: Entry polling WORKS correctly (reference pattern)
**File:** `nexus2/domain/automation/warrior_entry_execution.py:200-231`
```python
order_detail = await engine._get_order_status(broker_order_id)  # ← CORRECT method
if status_str.lower() in ("filled", "partially_filled"):
    fill_price = getattr(order_detail, 'filled_avg_price', None)  # ← BUT also wrong attr name!
```
NOTE: Entry also uses `filled_avg_price` attribute name (incorrect), but entry polling goes through `engine._get_order_status()` which returns a different object than `BrokerOrder` — investigate whether the entry path actually works correctly too, or if it also falls back.

### Fact 6: Slippage labels might be wrong
**File:** `nexus2/domain/automation/trade_event_service.py:659-676`
The `log_warrior_exit_fill_confirmed` computes `slippage_cents = float((actual_price - intended_price) * 100)`. For sells, positive slippage (actual > intended) means a BETTER fill. But the label logic says:
```python
if slippage_cents > 0:
    slip_str = f"{slippage_cents:.1f}¢ worse"  # WRONG for sells
```

---

## Required Changes

### Change 1: Fix method name and attribute name (warrior_callbacks.py:470-472)

```diff
-                        filled_order = alpaca.get_order(order_id)
-                        if hasattr(filled_order, 'filled_avg_price') and filled_order.filled_avg_price:
-                            actual_fill_price = float(filled_order.filled_avg_price)
+                        filled_order = alpaca.get_order_status(order_id)
+                        if filled_order.avg_fill_price and float(filled_order.avg_fill_price) > 0:
+                            actual_fill_price = float(filled_order.avg_fill_price)
```

### Change 2: Increase retries and don't break on errors (warrior_callbacks.py:467-477)

```diff
-                for _ in range(4):
+                for attempt in range(8):  # 8 × 0.5s = 4 seconds max
                     await asyncio.sleep(0.5)
                     try:
-                        filled_order = alpaca.get_order(order_id)
-                        if hasattr(filled_order, 'filled_avg_price') and filled_order.filled_avg_price:
-                            actual_fill_price = float(filled_order.filled_avg_price)
+                        filled_order = alpaca.get_order_status(order_id)
+                        if filled_order.avg_fill_price and float(filled_order.avg_fill_price) > 0:
+                            actual_fill_price = float(filled_order.avg_fill_price)
                             print(f"[Warrior] {symbol} filled @ ${actual_fill_price:.2f}")
                             break
                     except Exception as poll_err:
-                        print(f"[Warrior] Poll error: {poll_err}")
-                        break
+                        print(f"[Warrior] Poll attempt {attempt+1}/8 error: {poll_err}")
+                        continue  # Retry, don't give up
```

### Change 3: Add warning when falling back (after warrior_callbacks.py:479)

```python
exit_price = actual_fill_price if actual_fill_price else float(limit_price)
if not actual_fill_price:
    print(f"[Warrior] ⚠️ {symbol}: Fill poll failed after 8 attempts, using limit ${limit_price:.2f} as exit price")
```

### Change 4: Fix slippage labels in log_warrior_exit_fill_confirmed (trade_event_service.py)

Investigate the existing label logic at L659-676. For EXIT (sell) events:
- `actual > intended` → positive slippage → **better** for sells (got more money)
- `actual < intended` → negative slippage → **worse** for sells (got less money)

Determine the correct fix — either swap labels for exits, or add a `side` parameter.

### Change 5 (investigate): Entry fill attribute name
Check `warrior_entry_execution.py:212`:
```python
fill_price = getattr(order_detail, 'filled_avg_price', None)
```
`order_detail` is the result of `engine._get_order_status()` — is this a `BrokerOrder` (which uses `avg_fill_price`)? If so, entry fill polling may ALSO be broken (different fallback behavior though). Check if entries actually get the correct fill price.

---

## Constraints

- **DO NOT add new dependencies** — use existing `AlpacaBroker` and `BrokerOrder` types
- **DO NOT change BrokerOrder or BrokerProtocol** — they are the shared protocol
- **Test with**: `cd nexus2; python -m pytest tests/ -v --no-header`
- **After changes, verify import**: `cd nexus2; python -c "from api.routes.warrior_callbacks import create_execute_exit; print('OK')"`

---

## Implementation Plan Reference

See: `nexus2/reports/2026-02-18/plan_exit_fill_and_pnl_fixes.md`
