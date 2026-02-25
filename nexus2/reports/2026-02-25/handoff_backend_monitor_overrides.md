# Handoff: Extend config_overrides to Monitor Settings

**Agent:** Backend Specialist
**Priority:** P1 — parameter sweeps for monitor settings are broken
**Date:** 2026-02-25

---

## Problem

The `config_overrides` fix from yesterday only covers engine config fields. Monitor settings (like `max_reentry_after_loss`, `enable_profit_check_guard`) are NOT propagated to sim engines during batch tests. Same class of bug.

## Verified Facts

**1. Monitor settings are read from `engine.monitor.settings`:**
- File: `nexus2/domain/automation/warrior_entry_guards.py:154`
- Code: `max_attempts = engine.monitor.settings.max_reentry_after_loss`
- Verified with: `Select-String -Path "nexus2\domain\automation\warrior_entry_guards.py" -Pattern "max_reentry" -Context 1,2`

**2. config_overrides only applies to engine.config, not monitor.settings:**
- File: `nexus2/adapters/simulation/sim_context.py:77-78`
- The `config_overrides` loop only sets attributes on `engine.config`
- Monitor settings are a separate object on `engine.monitor.settings`

**3. Sweep correctly classifies monitor settings but can't propagate them:**
- `gc_param_sweep.py` detects `max_reentry_after_loss` as `type: monitor`
- Only `type: config` settings send `config_overrides` in the batch payload
- Result: sweeping monitor settings compares defaults against defaults

## Task

Extend the batch test pipeline to accept AND apply `monitor_overrides` alongside `config_overrides`:

1. Add `monitor_overrides: Optional[dict]` to `BatchTestRequest` in `warrior_sim_routes.py`
2. Thread `monitor_overrides` through `SimContext.create()` → `_run_case_sync()` → `_run_single_case_async()` → `run_batch_concurrent()` (same pattern as config_overrides)
3. In `SimContext.create()`, apply monitor overrides to `engine.monitor.settings` after engine creation
4. Update `gc_param_sweep.py` to send `monitor_overrides` for monitor-type settings (parallel to the `config_overrides` logic at line 184-186)

## Output

- Write status to: `nexus2/reports/2026-02-25/backend_status_monitor_overrides.md`
- Include testable claims
- Run pytest after changes
