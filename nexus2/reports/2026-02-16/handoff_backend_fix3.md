# Handoff: Backend Specialist — Implement Fix 3: Structural Profit Levels

**Date:** 2026-02-16  
**From:** Coordinator  
**To:** Backend Specialist (`@agent-backend-specialist.md`)

---

## Your Task

Implement **Fix 3: Structural Profit Levels** per the Backend Planner's spec:  
`nexus2/reports/2026-02-16/spec_structural_levels.md`

**Read that spec thoroughly.** It contains:
- Structural level analysis for all test cases
- All 5 change points with exact code
- `_compute_structural_target()` helper implementation
- Wiring checklist and risk assessment

---

## Quick Summary

**What:** Replace flat +18¢ fallback target with next structural price level ($0.50 increments). Entry at $4.65 → target $5.00. Entry at $5.00 → target $5.50.

**Files to modify:**
1. `warrior_types.py` — Add 3 config fields (`enable_structural_levels`, `structural_level_increment`, `structural_level_min_distance_cents`)
2. `warrior_monitor_exit.py` — Add `_compute_structural_target()` helper + replace flat fallback calculation + update trigger descriptions
3. `warrior_monitor_settings.py` — Persistence for 3 new fields

**A/B Toggle:** `enable_structural_levels = False` reverts to flat +18¢.

---

## After Implementation

```powershell
# Import check
python -c "from nexus2.domain.automation.warrior_monitor_exit import _compute_structural_target; from decimal import Decimal; print(_compute_structural_target(Decimal('4.65'))); print(_compute_structural_target(Decimal('5.00'))); print(_compute_structural_target(Decimal('4.97')))"
# Expected: 5.00, 5.50, 5.50 (4.97→5.00 is 3¢ < 10¢ min, skip to 5.50)

# Config check
python -c "from nexus2.domain.automation.warrior_types import WarriorMonitorSettings; s = WarriorMonitorSettings(); print(f'structural={s.enable_structural_levels}, inc={s.structural_level_increment}, min={s.structural_level_min_distance_cents}')"

# Persistence check
python -c "from nexus2.db.warrior_monitor_settings import get_monitor_settings_dict; from nexus2.domain.automation.warrior_types import WarriorMonitorSettings; d = get_monitor_settings_dict(WarriorMonitorSettings()); print('enable_structural_levels' in str(d), 'structural_level_increment' in str(d))"

# Unit tests
python -m pytest nexus2/tests/unit/automation/test_warrior_monitor.py -v --tb=short
```

---

## Deliverable

1. All changes per the spec's wiring checklist
2. Write status report to: `nexus2/reports/2026-02-16/status_fix3_structural_levels.md`
