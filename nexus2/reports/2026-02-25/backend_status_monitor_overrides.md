# Backend Status: Monitor Overrides for Batch Test Parameter Sweeps

**Agent:** Backend Specialist  
**Date:** 2026-02-25  
**Status:** ✅ Complete  
**Pytest:** 757 passed, 4 skipped, 3 deselected (107.60s)

---

## Problem

`config_overrides` only propagated engine config fields to sim engines during batch tests. Monitor settings (like `max_reentry_after_loss`, `enable_profit_check_guard`) were NOT overridden — sweeping them compared defaults against defaults.

## Changes Made

### 1. `nexus2/api/routes/warrior_sim_routes.py`

- **L1334**: Added `monitor_overrides: Optional[dict]` to `BatchTestRequest`
- **L1440-1445**: Sequential runner (`run_batch_tests`) applies monitor overrides to `engine.monitor.settings`
- **L1661**: Concurrent runner endpoint passes `monitor_overrides` to `run_batch_concurrent`

### 2. `nexus2/adapters/simulation/sim_context.py`

- **L33**: `SimContext.create()` accepts `monitor_overrides: Optional[dict]`
- **L82-87**: Applies monitor overrides to `engine.monitor.settings` after loading saved settings (takes precedence)
- **L561**: `_run_case_sync` unpacks 5-tuple `(case, yaml, skip_guards, config_overrides, monitor_overrides)`
- **L597**: `_run_single_case_async` accepts `monitor_overrides` kwarg, passes to `SimContext.create()`
- **L924**: `run_batch_concurrent` accepts `monitor_overrides`, includes in per-case tuple

### 3. `scripts/gc_param_sweep.py`

- **L100**: `run_batch()` accepts `monitor_overrides` kwarg, includes in request body
- **L190-196**: Sweep loop sends `monitor_overrides` (not `config_overrides`) for monitor-type settings

---

## Testable Claims

| # | Claim | File:Line | Verification |
|---|-------|-----------|-------------|
| 1 | `BatchTestRequest` has `monitor_overrides` field | `warrior_sim_routes.py:1334` | `Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "monitor_overrides"` |
| 2 | `SimContext.create()` accepts `monitor_overrides` param | `sim_context.py:33` | `Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "monitor_overrides"` |
| 3 | Monitor overrides applied to `engine.monitor.settings` in `SimContext.create` | `sim_context.py:82-87` | `Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "monitor.settings"` |
| 4 | `_run_case_sync` unpacks 5-tuple with `monitor_overrides` | `sim_context.py:573` | `Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "len(case_tuple) == 5"` |
| 5 | `_run_single_case_async` passes `monitor_overrides` to `SimContext.create` | `sim_context.py:621` | `Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "monitor_overrides=monitor_overrides"` |
| 6 | `run_batch_concurrent` includes `monitor_overrides` in per-case tuple | `sim_context.py:938` | `Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "config_overrides, monitor_overrides"` |
| 7 | `gc_param_sweep.py` sends `monitor_overrides` for monitor-type settings | `gc_param_sweep.py:195` | `Select-String -Path "scripts\gc_param_sweep.py" -Pattern "monitor_overrides"` |
| 8 | Sequential runner applies monitor overrides | `warrior_sim_routes.py:1440` | `Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "monitor.settings"` |
| 9 | Pytest 757 passed | N/A | `.\.venv\Scripts\python.exe -m pytest nexus2/tests/ -x -q --tb=short` |

---

## Usage

After this fix, sweeping monitor settings works end-to-end:

```bash
# This now actually varies the setting per batch run (was broken before)
python scripts/gc_param_sweep.py max_reentry_after_loss 1 3 5
python scripts/gc_param_sweep.py enable_profit_check_guard true false
python scripts/gc_param_sweep.py base_hit_profit_cents 15 18 25
```
