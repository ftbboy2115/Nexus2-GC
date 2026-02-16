# Status: Fix 4 — Improved Home Run Trail

**Date:** 2026-02-16  
**Agent:** Backend Specialist  
**Spec:** `spec_homerun_trail_improvement.md`

---

## Summary

Implemented all 3 sub-fixes behind master toggle `enable_improved_home_run_trail = False`.

| Sub-fix | What | Status |
|---------|------|--------|
| **4a** | Replace breakeven stop with `trail_level` stop (both paths) | ✅ Done |
| **4b** | Skip topping tail for home_run positions | ✅ Done |
| **4c** | Replace 20%-from-high trail with candle-low trail (5-bar) | ✅ Done |

---

## Files Modified

### `warrior_types.py`
- Added 5 config fields after `enable_partial_then_ride`:
  - `enable_improved_home_run_trail: bool = False`
  - `home_run_stop_after_partial: str = "trail_level"`
  - `home_run_skip_topping_tail: bool = True`
  - `home_run_candle_trail_enabled: bool = True`
  - `home_run_candle_trail_lookback: int = 5`

### `warrior_monitor_exit.py`
- **Fix 4a (Path A, candle trail hit ~line 815):** Breakeven logic now conditioned on toggle. `trail_level` saves `candle_trail_stop` before clearing, uses it as the new stop.
- **Fix 4a (Path B, flat fallback hit ~line 928):** Identical logic applied to the flat target path.
- **Fix 4b (~line 571):** Guard added after `enable_topping_tail` check — skips topping tail when position is in `home_run` mode.
- **Fix 4c (~line 1069):** Trailing stop logic branched: when Fix 4 enabled, uses candle-low trail (N-bar lookback) instead of 20% percentage trail. Falls back to percentage trail when disabled.

### `warrior_monitor_settings.py`
- `apply_monitor_settings`: Added persistence for all 5 new fields.
- `get_monitor_settings_dict`: Added serialization for all 5 new fields.

---

## Verification

```
Config check:
fix4=False, stop=trail_level, skip_tt=True, candle_trail=True, lookback=5  ✅

Persistence check:
True True  ✅

Unit tests:
36 passed in 4.23s  ✅
```

---

## Wiring Checklist

- [x] Config fields added to `WarriorMonitorSettings`
- [x] Fix 4a: Breakeven logic conditioned (BOTH paths)
- [x] Fix 4b: Topping tail guard for home_run positions
- [x] Fix 4c: Candle-low trail logic added to `_check_home_run_exit`
- [x] Fix 4c: Fallback to percentage trail when `home_run_candle_trail_enabled = False`
- [x] Settings persistence in `apply_monitor_settings`
- [x] Settings persistence in `get_monitor_settings_dict`
- [x] Master toggle `enable_improved_home_run_trail = False` ensures no regression
