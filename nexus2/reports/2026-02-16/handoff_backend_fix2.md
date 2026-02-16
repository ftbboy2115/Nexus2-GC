# Handoff: Backend Specialist — Implement Fix 2: Price-Proportional Trail

**Date:** 2026-02-16  
**From:** Coordinator  
**To:** Backend Specialist (`@agent-backend-specialist.md`)

---

## Your Task

Implement **Fix 2: Price-Proportional Trail Activation** per the Backend Planner's spec:  
`nexus2/reports/2026-02-16/spec_proportional_trail.md`

**Read that spec thoroughly.** It contains:
- Price analysis across 38 test cases
- All 6 change points with exact file paths and line numbers
- Wiring checklist and risk assessment

---

## Quick Summary

**What:** Replace fixed +15¢ trail activation with `max(15, entry_price * 3%)` and fixed +18¢ flat fallback with `max(18, entry_price * 3.5%)`.

**Files to modify:**
1. `warrior_types.py` — Add `trail_activation_pct: float = 3.0` and `base_hit_profit_pct: float = 3.5`
2. `warrior_monitor_exit.py` — Compute proportional values at 2 points in `_check_base_hit_target`
3. `warrior_monitor_settings.py` — Add persistence for both new fields

**A/B Toggle:** Setting `trail_activation_pct = 0.0` reverts to fixed behavior.

---

## After Implementation

```powershell
# Import check
python -c "from nexus2.domain.automation.warrior_monitor_exit import _check_base_hit_target; print('OK')"

# Config check
python -c "from nexus2.domain.automation.warrior_types import WarriorMonitorSettings; s = WarriorMonitorSettings(); print(f'trail_activation_pct={s.trail_activation_pct}, base_hit_profit_pct={s.base_hit_profit_pct}')"

# Persistence check
python -c "from nexus2.db.warrior_monitor_settings import get_monitor_settings_dict; from nexus2.domain.automation.warrior_types import WarriorMonitorSettings; d = get_monitor_settings_dict(WarriorMonitorSettings()); print('trail_activation_pct' in str(d), 'base_hit_profit_pct' in str(d))"

# Unit tests
python -m pytest nexus2/tests/unit/automation/test_warrior_monitor.py -v --tb=short
```

---

## Deliverable

1. All 6 changes implemented per the spec's wiring checklist
2. Write status report to: `nexus2/reports/2026-02-16/status_fix2_proportional_trail.md`
