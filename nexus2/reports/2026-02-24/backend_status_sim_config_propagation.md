# Backend Status: Sim Config Propagation Fix

**Agent:** Backend Specialist
**Date:** 2026-02-24
**Priority:** P1

---

## Problem

Parameter sweeps via `gc_param_sweep.py` produced identical P&L regardless of the tested value ($161,129.87 for all three `macd_histogram_tolerance` values). **Two root causes** were identified:

### Root Cause 1: Wrong API Endpoint
`gc_param_sweep.py` always routed settings to `PUT /warrior/monitor/settings` (line 50). Engine config fields like `macd_histogram_tolerance` belong to `PUT /warrior/config` — the monitor endpoint silently ignored unknown fields, so the setting never changed.

### Root Cause 2: No Config Override Passthrough
Even when settings are persisted to disk, the concurrent batch runner spawns separate processes. There was no mechanism to pass sweep-specific config overrides directly to sim engines, creating a race condition between persistence and batch execution.

---

## Changes Made

### 1. `BatchTestRequest` — config_overrides field
**File:** `nexus2/api/routes/warrior_sim_routes.py:1331`
- Added `config_overrides: Optional[dict]` field to `BatchTestRequest`
- Sequential runner (`run_batch_tests`) applies overrides to engine config after loading each test case
- Concurrent runner (`run_batch_concurrent_endpoint`) passes overrides through to `run_batch_concurrent()`

### 2. `SimContext` — config override propagation
**File:** `nexus2/adapters/simulation/sim_context.py`
- `SimContext.create()` accepts `config_overrides` parameter, applies after loading saved settings
- `_run_case_sync()` unpacks 4-tuple `(case, yaml_data, skip_guards, config_overrides)`
- `_run_single_case_async()` passes overrides to `SimContext.create()`
- `run_batch_concurrent()` accepts and forwards `config_overrides`

### 3. `gc_param_sweep.py` — auto-routing + config_overrides
**File:** `scripts/gc_param_sweep.py`
- Added `ENGINE_CONFIG_FIELDS` set for auto-detection of setting type
- `detect_setting_type()` determines whether setting goes to `/config` or `/monitor/settings`
- `run_batch()` now accepts `config_overrides` and passes them in the batch request body
- Engine config settings are passed as both a persistent update AND as `config_overrides`
- Supports `--type config|monitor` flag to force routing

---

## Testable Claims

| # | Claim | File:Line | Verification |
|---|-------|-----------|--------------|
| 1 | `BatchTestRequest` has `config_overrides` field | `warrior_sim_routes.py:1331` | `Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "config_overrides"` |
| 2 | Sequential batch runner applies config overrides | `warrior_sim_routes.py:1432-1437` | grep `"Override: engine.config"` in batch runner block |
| 3 | Concurrent endpoint passes overrides to `run_batch_concurrent` | `warrior_sim_routes.py:1645` | `Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "config_overrides=request.config_overrides"` |
| 4 | `SimContext.create` accepts `config_overrides` | `sim_context.py:33` | `Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "config_overrides"` |
| 5 | `_run_case_sync` handles 4-tuple with config_overrides | `sim_context.py:571` | `Select-String` for `len(case_tuple) == 4` |
| 6 | `gc_param_sweep.py` detects `macd_histogram_tolerance` as config type | `scripts/gc_param_sweep.py:48` | `Select-String -Pattern "macd_histogram_tolerance"` in ENGINE_CONFIG_FIELDS |
| 7 | `gc_param_sweep.py` passes config_overrides in batch request body | `scripts/gc_param_sweep.py:106` | grep `config_overrides` in run_batch function |
| 8 | Pytest: 184 passed, 0 new failures | — | 1 pre-existing HIND scanner RVOL boundary failure (unrelated) |

---

## Pre-existing Test Failure (NOT caused by this change)

```
FAILED test_scanner_validation.py::TestScannerPicksUpValidTickers::test_known_winners_pass[ross_hind_20260127]
Reason: RVOL 2.0x < 2.0x (floating point boundary comparison)
```

This is a scanner min_rvol boundary issue. HIND has exactly 2.0x RVOL but fails the `>= 2.0` check due to floating point comparison. **Existed before this PR.**
