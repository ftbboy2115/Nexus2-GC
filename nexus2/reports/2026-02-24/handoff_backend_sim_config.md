# Handoff: Fix Sim Config Propagation for Batch Tests

**Agent:** Backend Specialist
**Priority:** P1 — parameter sweeps are broken without this
**Date:** 2026-02-24

---

## Problem

Parameter sweeps via `gc_param_sweep.py` update the LIVE engine's config but batch tests create fresh sim engines with DEFAULT config values. This means sweeps compare defaults against defaults — producing identical results regardless of the tested value.

**Evidence:** Three sweeps of `macd_histogram_tolerance` (-0.02, -0.10, -1.0) all produced $161,129.87.

## Verified Facts

**1. The param sweep updates live engine config correctly:**
- File: `nexus2/api/routes/warrior_routes.py:527-528`
- Code: `engine.config.macd_histogram_tolerance = request.macd_histogram_tolerance`
- Verified with: `Select-String -Path "nexus2\api\routes\warrior_routes.py" -Pattern "macd_histogram_tolerance"`

**2. The sim route does NOT propagate the tolerance:**
- File: `nexus2/api/routes/warrior_sim_routes.py`
- Only config it sets: `engine.config.sim_only = True` (lines 153, 377, 825)
- `macd_histogram_tolerance` appears ZERO times in this file
- Verified with: `Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "macd_histogram_tolerance"` (empty result)

**3. The MACD gate reads from engine.config:**
- File: `nexus2/domain/automation/warrior_entry_guards.py:214`
- Code: `tolerance = engine.config.macd_histogram_tolerance  # default -0.02`

## Task

Propagate ALL tunable config fields from the live engine to sim engines created for batch tests. This should include at minimum:
- `macd_histogram_tolerance`
- `max_reentry_after_loss` (likely same bug)
- `enable_profit_check_guard`
- Any other fields exposed via `PUT /warrior/monitor/settings`

### Approach Options

1. **Copy from live engine:** Before running a sim case, copy the live engine's config values to the sim engine
2. **Accept config in batch request:** Pass config overrides in the `BatchTestRequest` payload
3. **Shared config source:** Both live and sim engines read from the same persisted config

Option 1 is simplest and preserves the "sweep sets live, batch uses live settings" workflow.

## Output

- Write status to: `nexus2/reports/2026-02-24/backend_status_sim_config_propagation.md`
- Include testable claims
- Run pytest after changes
