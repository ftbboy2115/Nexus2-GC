# Planner Investigation: Missing Scale Events in Trade Events Tab

**Date:** 2026-02-17
**Handoff:** `nexus2/reports/2026-02-17/handoff_planner_scale_event_logging.md`

---

## Root Cause Summary

**The `execute_scale_in()` function in `warrior_monitor_scale.py` never calls `trade_event_service.log_warrior_scale_in()`.** It imports `trade_event_service` (line 179) but only uses it for stop-to-breakeven logging (line 297). The SCALE_IN event type, logging method, and frontend rendering all exist — only the call from the monitor-loop scale path is missing.

**Secondary bug:** `execute_scale_in()` does NOT compute a weighted-average entry price after scaling, unlike `_consolidate_existing_position()` which does.

---

## A. Runtime Evidence

### ATOM Trade Events (Live VPS)

**Verified with:** `ssh root@100.113.178.7 "curl -s 'http://localhost:8000/data/trade-events?symbol=ATOM&limit=20' | python3 -m json.tool"`

Position `8d5ee1c3` (the scaled trade):

| ID | Event Type | Details |
|----|-----------|---------|
| 22966 | ENTRY | 10 shares @ $5.31 (bull_flag) |
| 22967 | FILL_CONFIRMED | 10 shares filled @ $5.30 |
| 22968 | BREAKEVEN_SET | Stop to $5.30 |
| 22969 | PARTIAL_EXIT | 10 shares @ $5.41 |
| 22970 | EXIT_FILL_CONFIRMED | 10 shares fill @ $5.41 |
| 22971 | TOPPING_TAIL_EXIT | exit @ $5.60 |
| 22972 | EXIT_FILL_CONFIRMED | 10 shares fill @ $5.60 |

**Gap confirmed:** Zero SCALE_IN events between IDs 22967 and 22968 despite Alpaca showing BUY 5 @ $5.32 and BUY 5 @ $5.35 during that window.

Position `2942f552` (earlier ATOM trade):
- ENTRY logged with 10 shares, but EXIT_FILL_CONFIRMED shows **20 shares** — proving scaling happened but wasn't logged.

### Monitor Settings (Live VPS)

**Verified with:** `ssh root@100.113.178.7 "curl -s 'http://localhost:8000/warrior/monitor/settings' | python3 -m json.tool"`

```json
{
    "enable_scaling": true,
    "max_scale_count": 2,
    "scale_size_pct": 50,
    "move_stop_to_breakeven_after_scale": false
}
```

Key: `move_stop_to_breakeven_after_scale: false` means the conditional at line 289 (`if monitor.settings.move_stop_to_breakeven_after_scale`) is False, so `log_warrior_stop_update()` at line 297 is NEVER called during scales either. No trade events of any kind are logged during scaling.

---

## B. Existing Pattern Analysis

| Pattern | Function | File | Lines | Key Call |
|---------|----------|------|-------|----------|
| **Scale via entry-time consolidation** ✅ | `_consolidate_existing_position` | `warrior_monitor.py` | 302–370 | `trade_event_service.log_warrior_scale_in()` at L354, weighted avg at L328, `complete_scaling(new_avg_price=...)` at L364 |
| **Scale via monitor-loop** ❌ | `execute_scale_in` | `warrior_monitor_scale.py` | 163–333 | NO `log_warrior_scale_in()`, NO weighted avg, `complete_scaling()` at L286 **without** `new_avg_price` |
| **Scale via micro-pullback entry** ❌ | `scale_into_existing_position` | `warrior_entry_execution.py` | 294–401 | Delegates to `execute_scale_in()` at L387 — inherits both gaps |

---

## C. Change Surface Enumeration

| # | File | Change | Location | Template |
|---|------|--------|----------|----------|
| 1 | `warrior_monitor_scale.py` | Add weighted-avg entry price calculation | After L282 (`position.shares += add_shares`) | `warrior_monitor.py` L325–332 |
| 2 | `warrior_monitor_scale.py` | Recalculate risk_per_share and profit_target | After weighted avg calc | `warrior_monitor.py` L340–346 |
| 3 | `warrior_monitor_scale.py` | Pass `new_avg_price` to `complete_scaling()` | L286 | `warrior_monitor.py` L364–368 |
| 4 | `warrior_monitor_scale.py` | Add `log_warrior_scale_in()` call | After `complete_scaling()`, before L288 | `warrior_monitor.py` L354–359 |

---

## D. Detailed Change Specifications

### Change Point #1 + #2 + #3: Weighted avg entry price, risk/target recalc, and DB update

**What:** Calculate weighted-average entry price after scaling, recalculate risk and profit target, pass new avg to DB
**File:** `nexus2/domain/automation/warrior_monitor_scale.py`
**Location:** Lines 278–286 (inside `execute_scale_in`)

**Current Code:**
```python
        # Update position state
        old_shares = position.shares
        old_entry = position.entry_price
        position.scale_count += 1
        position.shares += add_shares
        new_total_shares = position.shares
        
        # Complete scaling in DB (SCALING → OPEN with updated shares)
        complete_scaling(position.position_id, new_total_shares)
```
**Verified with:** `view_file` at lines 278–286

**Template:** `warrior_monitor.py` lines 320–368 (`_consolidate_existing_position`):
```python
        # Calculate weighted average entry price
        old_cost = old_entry * old_shares
        new_cost = entry_price * shares
        new_avg_entry = (old_cost + new_cost) / new_total_shares
        
        # Update existing position
        existing_position.shares = new_total_shares
        existing_position.entry_price = new_avg_entry
        existing_position.scale_count += 1
        
        # Recalculate risk and target based on new average entry
        risk_per_share = new_avg_entry - existing_position.current_stop
        existing_position.risk_per_share = risk_per_share
        
        if s.profit_target_cents > 0:
            existing_position.profit_target = new_avg_entry + s.profit_target_cents / 100
        else:
            existing_position.profit_target = new_avg_entry + (risk_per_share * Decimal(str(s.profit_target_r)))
        
        # ... later ...
        complete_scaling(
            trade_id=existing_position.position_id,
            new_quantity=new_total_shares,
            new_avg_price=float(new_avg_entry),
        )
```
**Verified with:** `view_file` at lines 320–368

**Approach:** After `position.shares += add_shares` (L282), add weighted avg calculation using `old_entry * old_shares` + `price * add_shares`. Use `price` (the Decimal scale price already available at L176). Recalculate `risk_per_share` and `profit_target`. Then pass `new_avg_price=float(new_avg_entry)` to the existing `complete_scaling()` call.

**Note:** `price` is already a `Decimal` (L176: `price = scale_signal["price"]` → but actually set as `Decimal(str(scale_signal["price"]))` at L175–176). Need to verify it's Decimal before multiplying with `old_entry`.

---

### Change Point #4: Add SCALE_IN event logging

**What:** Call `trade_event_service.log_warrior_scale_in()` after scaling
**File:** `nexus2/domain/automation/warrior_monitor_scale.py`
**Location:** After L286 (`complete_scaling()`), before L288 (breakeven check)

**Current Code:** (nothing — there's a blank line then the breakeven block)
```python
        # Complete scaling in DB (SCALING → OPEN with updated shares)
        complete_scaling(position.position_id, new_total_shares)
        
        # Move stop to breakeven (original entry price)
```
**Verified with:** `view_file` at lines 285–288

**Template:** `warrior_monitor.py` lines 353–359:
```python
        # Log as scale event (TML)
        trade_event_service.log_warrior_scale_in(
            position_id=existing_position.position_id,
            symbol=symbol,
            add_price=entry_price,
            shares_added=shares,
        )
```
**Verified with:** `view_file` at lines 353–359

**Approach:** After `complete_scaling()`, call `trade_event_service.log_warrior_scale_in()` using variables already in scope: `position.position_id`, `symbol`, `price` (Decimal), `add_shares` (int). `trade_event_service` is already imported at L179.

---

## E. Wiring Checklist

- [ ] Add weighted-average entry price calculation after `position.shares += add_shares` (CP#1)
- [ ] Update `position.entry_price` with new weighted average (CP#1)
- [ ] Recalculate `position.risk_per_share` from new avg (CP#2)
- [ ] Recalculate `position.profit_target` from new avg (CP#2)
- [ ] Pass `new_avg_price=float(new_avg_entry)` to `complete_scaling()` (CP#3)
- [ ] Add `trade_event_service.log_warrior_scale_in()` call (CP#4)

---

## F. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Weighted avg Decimal arithmetic error | Medium | Use exact same formula as `_consolidate_existing_position()` L325–328 |
| `profit_target` recalc changes exit behavior | Medium | Follow same `profit_target_cents` vs `profit_target_r` branching as L343–346 |
| `price` variable might not be Decimal | Low | Verify L175–176; wrap in `Decimal(str())` if needed |
| Scale event logging adds latency | Low | Same DB write used by entries — negligible |
| Breaking sim batch tests | Low | Change is additive — logging doesn't alter scaling behavior |

---

## G. Verification Plan

1. **Unit test:** Existing `test_trade_events.py` tests (confirm no regressions)
2. **Sim batch for ATOM:** Run test case, then query `/data/trade-events?symbol=ATOM` — verify SCALE_IN events appear
3. **Frontend check:** Trade Events tab should show ➕ icon for scale events (rendering exists at `warrior-performance.tsx:124`)
4. **Share count check:** After scaling, query `/warrior/positions` — verify `shares` reflects post-scale total
5. **Weighted avg check:** Verify `entry_price` in position data reflects weighted average, not original entry
