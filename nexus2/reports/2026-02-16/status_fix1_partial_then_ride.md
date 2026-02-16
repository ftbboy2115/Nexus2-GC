# Status: Fix 1 — Partial-Then-Ride

**Date:** 2026-02-16  
**Agent:** Backend Specialist  
**Status:** ✅ COMPLETE

---

## Changes Made

### 1. Config Flag — `warrior_types.py`
- Added `enable_partial_then_ride: bool = True` to `WarriorMonitorSettings` (after L134)
- A/B testable: set to `False` to restore legacy 100%-exit behavior

### 2-3. Partial Exit Logic — `warrior_monitor_exit.py`
Modified `_check_base_hit_target` at two exit points:

**Candle trail stop hit (L748-816):**
- When `enable_partial_then_ride=True` and `partial_taken=False`:
  - Sells 50% via `partial_exit_fraction`
  - Sets `position.partial_taken = True`
  - Decrements `position.shares`
  - Sets `position.exit_mode_override = "home_run"` (mode switch)
  - Clears `position.candle_trail_stop = None`
  - Moves stop to breakeven (`position.current_stop = position.entry_price`)
  - Logs breakeven event via `trade_event_service`
  - Returns `PARTIAL_EXIT` signal (not `PROFIT_TARGET`)
- When disabled or partial already taken: full exit (original behavior preserved)

**Flat +18¢ fallback (L835-899):**
- Same partial-then-ride conditional as above

### 4-5. Mode Switch + Trail Clear (inline in #2 and #3)
- `position.exit_mode_override = "home_run"` routes next eval to `_check_home_run_exit`
- `position.candle_trail_stop = None` prevents stale trail interference

### 6-7. Settings Persistence — `warrior_monitor_settings.py`
- Added `enable_partial_then_ride` to `get_monitor_settings_dict` (serialization)
- Added `enable_partial_then_ride` to `apply_monitor_settings` (deserialization)

---

## Verification Results

| Check | Result |
|-------|--------|
| Import `_check_base_hit_target` | ✅ OK |
| Config flag defaults to `True` | ✅ `enable_partial_then_ride=True` |
| Settings persistence includes key | ✅ `True` |
| Unit tests (36 total) | ✅ 36 passed in 4.56s |

---

## Wiring Checklist

- [x] Config flag `enable_partial_then_ride: bool = True` added to `WarriorMonitorSettings`
- [x] `_check_base_hit_target` candle trail hit path converted to partial when flag is ON
- [x] `_check_base_hit_target` flat fallback path converted to partial when flag is ON
- [x] After partial: `position.partial_taken = True`
- [x] After partial: `position.shares -= shares_to_exit`
- [x] After partial: `position.exit_mode_override = "home_run"` (mode switch)
- [x] After partial: `position.candle_trail_stop = None` (clear stale trail)
- [x] After partial: `position.current_stop = position.entry_price` (breakeven stop)
- [x] After partial: `trade_event_service.log_warrior_breakeven(...)` called
- [x] After partial: `monitor.partials_triggered += 1`
- [x] Signal uses `WarriorExitReason.PARTIAL_EXIT` (not `PROFIT_TARGET`)
- [x] Persistence: `enable_partial_then_ride` in `get_monitor_settings_dict`
- [x] Persistence: `enable_partial_then_ride` in `apply_monitor_settings`
- [x] Full exit path preserved as fallback when `enable_partial_then_ride=False` or `partial_taken=True`

---

## Next Steps

- Run full 29-case batch test with `enable_partial_then_ride=True` vs `False` to measure P&L impact
- Deploy to VPS after batch validation
