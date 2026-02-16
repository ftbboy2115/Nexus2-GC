# Handoff: Backend Specialist — Implement Fix 1: Partial-Then-Ride

**Date:** 2026-02-16  
**From:** Coordinator  
**To:** Backend Specialist (`@agent-backend-specialist.md`)

---

## Your Task

Implement **Fix 1: Partial-Then-Ride** exactly per the Backend Planner's technical spec:  
`nexus2/reports/2026-02-16/spec_partial_then_ride.md`

**Read that spec thoroughly.** It contains:
- Template code to follow (`_check_home_run_exit` L852-891)
- All 7 change points with exact file paths and line numbers
- A wiring checklist
- Risk assessment and edge cases

---

## Quick Summary (read the spec for details)

**What:** When base_hit trail/target fires, sell 50% and switch remainder to home_run trailing.

**Files to modify:**
1. `warrior_types.py` — Add `enable_partial_then_ride: bool = True`
2. `warrior_monitor_exit.py` — Modify 2 exit points in `_check_base_hit_target`
3. `warrior_monitor_settings.py` — Add persistence for the new flag

**Toggle:** `enable_partial_then_ride` on `WarriorMonitorSettings` (for A/B testing)

---

## Strategy Context

- Read `.agent/strategies/warrior.md` for Ross Cameron methodology
- Ross always takes partials, never full exits on winners
- The bot currently exits 100% of shares at +15¢ trail / +18¢ flat

---

## After Implementation

Run these verification commands:
```powershell
# Import check
python -c "from nexus2.domain.automation.warrior_monitor_exit import _check_base_hit_target; print('OK')"

# Config flag check
python -c "from nexus2.domain.automation.warrior_types import WarriorMonitorSettings; s = WarriorMonitorSettings(); print(f'enable_partial_then_ride={s.enable_partial_then_ride}')"

# Settings persistence check
python -c "from nexus2.db.warrior_monitor_settings import get_monitor_settings_dict; from nexus2.domain.automation.warrior_types import WarriorMonitorSettings; d = get_monitor_settings_dict(WarriorMonitorSettings()); print('partial_then_ride' in str(d))"

# Unit tests
python -m pytest nexus2/tests/unit/automation/test_warrior_monitor.py -v --tb=short
```

---

## Deliverable

1. All 7 changes implemented per the spec's wiring checklist
2. Write status report to: `nexus2/reports/2026-02-16/status_fix1_partial_then_ride.md`
