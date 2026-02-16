# Handoff: Backend Specialist — Implement Fix 4: Improved Home Run Trail

**Date:** 2026-02-16  
**From:** Coordinator  
**To:** Backend Specialist (`@agent-backend-specialist.md`)

---

## Your Task

Implement **Fix 4: Improved Home Run Trail** per the Backend Planner's spec:  
`nexus2/reports/2026-02-16/spec_homerun_trail_improvement.md`

**Read that spec thoroughly.** It contains the full audit of `_check_home_run_exit`, all 5 root causes, and detailed change specs for 5 change points.

---

## Quick Summary

**The problem:** Fix 1 sends 50% of shares to home_run mode, but sets `current_stop = entry_price` (breakeven). Any dip to entry = full stop-out before the home_run trailing logic ever runs. Additionally, topping tail exits kill home_run positions prematurely.

**Three sub-fixes behind one toggle (`enable_improved_home_run_trail`):**

| Fix | What | Impact |
|-----|------|--------|
| **4a** | Replace breakeven stop with trail_level stop (keep the candle trail value that triggered the partial) | HIGH — #1 position killer |
| **4b** | Skip topping tail for home_run positions | MEDIUM — prevents premature reversal exits |
| **4c** | Replace 20%-from-high trail with candle-low trail (5-bar lookback) | HIGH — Ross-aligned trailing |

**Files to modify:**
1. `warrior_types.py` — 5 new config fields
2. `warrior_monitor_exit.py` — Changes in 3 functions (_check_base_hit_target breakeven logic × 2 paths, _check_topping_tail guard, _check_home_run_exit candle trail)
3. `warrior_monitor_settings.py` — Persistence for 5 new fields

**Master toggle:** `enable_improved_home_run_trail = False` ensures zero regression when disabled.

---

## Critical Implementation Notes

1. **Fix 4a has TWO identical paths** to modify in `_check_base_hit_target`:
   - Path A: Candle trail hit (lines ~815-827)
   - Path B: Flat fallback target hit (lines ~928-940)
   - Both set `current_stop = entry_price`. Both need the trail_level logic.
   - **IMPORTANT**: Save `position.candle_trail_stop` BEFORE clearing it (it's the value to use as the new stop)

2. **Fix 4c requires `monitor._get_intraday_candles`** — the home_run function doesn't currently fetch candles. Use the same pattern as `_check_base_hit_target` (lines 756-790).

3. **Fix 4b is the simplest** — single guard at the top of `_check_topping_tail`, same pattern as the CUC green-position guard.

---

## After Implementation

```powershell
# Config check
python -c "from nexus2.domain.automation.warrior_types import WarriorMonitorSettings; s = WarriorMonitorSettings(); print(f'fix4={s.enable_improved_home_run_trail}, stop={s.home_run_stop_after_partial}, skip_tt={s.home_run_skip_topping_tail}, candle_trail={s.home_run_candle_trail_enabled}, lookback={s.home_run_candle_trail_lookback}')"

# Persistence check
python -c "from nexus2.db.warrior_monitor_settings import get_monitor_settings_dict; from nexus2.domain.automation.warrior_types import WarriorMonitorSettings; d = get_monitor_settings_dict(WarriorMonitorSettings()); print('enable_improved_home_run_trail' in str(d), 'home_run_candle_trail_lookback' in str(d))"

# Unit tests
python -m pytest nexus2/tests/unit/automation/test_warrior_monitor.py -v --tb=short
```

---

## Deliverable

1. All changes per the spec's wiring checklist (Section F)
2. Write status report to: `nexus2/reports/2026-02-16/status_fix4_homerun_trail.md`
