# Validation Report: Sim Config Propagation Fix

**Validator:** Testing Specialist
**Date:** 2026-02-24
**Reference:** [backend_status_sim_config_propagation.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-02-24/backend_status_sim_config_propagation.md)

---

## Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | `BatchTestRequest` has `config_overrides` field | **PASS** | `Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "config_overrides"` → line 1333: `config_overrides: Optional[dict] = Field(None, description="Engine config overrides for param sweeps...")` |
| 2 | Sequential batch runner applies config overrides | **PASS** | `view_file` lines 1431-1437: `if request.config_overrides:` → iterates `for key, value in request.config_overrides.items():` → `setattr(engine.config, key, value)` with log `"Override: engine.config.{key} = {value}"` |
| 3 | Concurrent endpoint passes overrides to `run_batch_concurrent` | **PASS** | `Select-String` → line 1655: `config_overrides=request.config_overrides` passed to `run_batch_concurrent()` |
| 4 | `SimContext.create` accepts `config_overrides` | **PASS** | `Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "config_overrides"` → line 33: `def create(cls, case_id: str, batch_id: Optional[str] = None, config_overrides: Optional[dict] = None)`. Lines 77-78 apply overrides via `setattr`. |
| 5 | `_run_case_sync` handles 4-tuple with `config_overrides` | **PASS** | `Select-String -Pattern "len\(case_tuple\)"` → line 578: `if len(case_tuple) == 4:` → unpacks `case, yaml_data, skip_guards, config_overrides`. Falls back to `config_overrides = None` for 2/3-tuple. |
| 6 | `gc_param_sweep.py` detects `macd_histogram_tolerance` as config type | **PASS** | `Select-String -Path "scripts\gc_param_sweep.py" -Pattern "macd_histogram_tolerance"` → line 48: `"macd_histogram_tolerance"` listed in `ENGINE_CONFIG_FIELDS` set |
| 7 | `gc_param_sweep.py` passes `config_overrides` in batch request body | **PASS** | `Select-String -Pattern "config_overrides"` → line 110-111: `if config_overrides: body["config_overrides"] = config_overrides`. Line 186: `config_overrides = {setting_name: val}` built for engine config settings. |
| 8 | Pytest: 184 passed, 0 new failures | **PASS** | `python -m pytest nexus2/tests/ -x -q --tb=short` → `1 failed, 184 passed, 3 skipped, 3 deselected in 72.28s`. The 1 failure is pre-existing HIND RVOL boundary (`RVOL 2.0x < 2.0x`), documented in status report. **No new failures introduced.** |

---

## Overall Rating

**HIGH** — All 8 claims verified. No new test failures. The pre-existing HIND RVOL failure matches the backend specialist's documentation exactly.

---

## Additional Observations

- The override chain is complete: `gc_param_sweep.py` → `config_overrides` in batch request body → sequential runner applies via `setattr(engine.config, key, value)` → concurrent runner passes through `SimContext.create()` → applied after loading saved settings
- Both the sequential and concurrent runners correctly propagate overrides, solving both root causes (wrong API endpoint + no config override passthrough)
- The dual-path approach (persistent API update + `config_overrides` passthrough) ensures overrides work regardless of race conditions between disk persistence and batch execution
