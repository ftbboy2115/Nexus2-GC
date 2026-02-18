# Handoff: Backend Specialist — Remaining Exit Fixes

@agent-backend-specialist.md

## Context

You previously fixed 7 items in warrior_callbacks.py, trade_event_service.py, warrior_entry_execution.py, and warrior_engine_entry.py (see walkthrough_exit_fill_fixes.md). Two critical items remain.

## Verified Facts

### Fact 1: `order.id` doesn't exist on BrokerOrder — polling loop is SKIPPED

**File:** `warrior_callbacks.py:465`
**Current code:**
```python
order_id = str(order.id) if hasattr(order, 'id') else None
```

**Problem:** `BrokerOrder` dataclass has no `.id` field. Fields are: `client_order_id`, `broker_order_id`, `symbol`, etc. (see protocol.py:26-62). So `hasattr(order, 'id')` → `False` → `order_id = None` → the `if order_id:` block at L466 is **never entered** → all your method/attribute fixes at L470-471 never execute.

**Verified by Backend Planner:** spec_exit_fill_fix.md, Bug 1 section. The entry code at warrior_entry_execution.py:152-155 handles this correctly with a fallthrough pattern.

### Fact 2: Stale guard clips fresh quote to stale signal price

**File:** `warrior_callbacks.py:438-439`
**Current code:**
```python
elif current_price > signal_price * 1.05:
    current_price = signal_price
```

**Problem:** For LRHC, `signal.exit_price` was $1.78 (stale Polygon lastTrade). Fresh quote returned $2.17 (correct). Guard saw $2.17 > $1.87 → clipped to stale $1.78 → limit = $1.76.

**Root cause confirmed by Code Auditor:** audit_exit_quote_freshness.md, Section F. The signal price can be stale because it's set from the same Polygon snapshot during monitor evaluation, which could return an old `lastTrade.p` for illiquid tickers.

---

## Required Changes

### Change 1: Fix order ID extraction (L465)

```diff
-            order_id = str(order.id) if hasattr(order, 'id') else None
+            order_id = order.broker_order_id if hasattr(order, 'broker_order_id') else None
```

This is the one-liner that makes your previous L470-477 fixes actually execute.

### Change 2: Replace stale guard with warning log (L438-439)

Replace the guard that clips the price, with a warning that logs the discrepancy but uses the fresh quote:

```diff
-            elif current_price > signal_price * 1.05:
-                current_price = signal_price
+            elif current_price > signal_price * 1.05:
+                print(
+                    f"[Warrior] {symbol}: Fresh quote ${current_price:.2f} is "
+                    f"{((current_price / signal_price) - 1) * 100:.1f}% above "
+                    f"signal ${signal_price:.2f} — using fresh quote"
+                )
+                # Don't clip — limit sell is protective (won't fill below limit)
+            elif current_price < signal_price * 0.90:
+                print(
+                    f"[Warrior] {symbol}: Fresh quote ${current_price:.2f} is "
+                    f"{((signal_price - current_price) / signal_price) * 100:.1f}% below "
+                    f"signal ${signal_price:.2f} — using signal price (stale guard)"
+                )
+                current_price = signal_price
```

**Rationale:**
- **Upward divergence** (fresh > signal * 1.05): Log but use fresh quote. For a sell limit order, a higher limit is harmless — it fills at market if market is below the limit. Only risk: if the quote is anomalously high, the order might not fill, but that's detectable.
- **Downward divergence** (fresh < signal * 0.90): Use signal price. A sell limit set too LOW risks recording wrong P&L. This catches the LRHC case (23% below signal).

---

## Verification

After changes:
1. `cd nexus2; python -c "from api.routes.warrior_callbacks import create_execute_exit; print('Import OK')"`
2. `cd nexus2; python -m pytest tests/ -v --no-header`
3. Confirm L465 reads `order.broker_order_id`
4. Confirm L438-439 logs instead of clipping for upward divergence, clips for downward

## Reference Documents

- Planner spec: `nexus2/reports/2026-02-18/spec_exit_fill_fix.md`
- Auditor report: `nexus2/reports/2026-02-18/audit_exit_quote_freshness.md`
