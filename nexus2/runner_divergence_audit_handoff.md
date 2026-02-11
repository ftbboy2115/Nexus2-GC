# Code Audit: Sequential vs Concurrent Runner P&L Divergence

## Problem Statement

The **sequential batch runner** (GUI) and **concurrent batch runner** produce **different P&L results** for the same test cases. The GUI results are **consistent across repeated runs**, ruling out contamination as the cause.

## Observed Data

### Cases that MATCH exactly (6/21):
| Case | P&L |
|------|-----|
| ross_gri_20260128 | $201.41 |
| ross_npt_20260203 | $1,732.62 |
| ross_pavm_20260121 | $554.49 |
| ross_gwav_20260116 | $630.63 |
| ross_lcfy_20260116 | -$482.56 |
| ross_rdib_20260206 | $27.76 |

### Cases that DIFFER (11/21):
| Case | GUI (Sequential) | Batch (Concurrent) | Delta |
|------|------------------|--------------------|-------|
| ross_rolr_20260114 | $1,538.73 | $1,622.73 | +$84.00 |
| ross_vero_20260116 | $137.13 | -$302.65 | -$439.78 |
| ross_tnmg_20260116 | -$12.36 | -$376.05 | -$363.69 |
| ross_bnkk_20260115 | $176.70 | $36.98 | -$139.72 |
| ross_bnai_20260205 | $185.26 | $66.70 | -$118.56 |
| ross_dcx_20260129 | $326.99 | $118.26 | -$208.73 |
| ross_uoka_20260209 | $279.50 | $244.94 | -$34.56 |
| ross_mnts_20260209 | -$316.71 | -$248.40 | +$68.31 |
| ross_flye_20260206 | -$267.67 | $0.00 | +$267.67 |
| ross_rvsn_20260205 | $105.05 | $0.00 | -$105.05 |
| ross_hind_20260127 | $0.00 | $0.00 | $0.00 |

**Key observation**: FLYE and RVSN produce flat ($0) in batch but actual trades in GUI. VERO and TNMG produce dramatically different results.

## Files to Audit

### Sequential Path (warrior_sim_routes.py)
- `load_historical_test_case()` — L690-1088 (setup + callback wiring)
- `step_clock()` — L1091-1284 (stepping logic)  
- `run_batch_tests()` — L1296-1562 (batch loop)

### Concurrent Path (sim_context.py)
- `load_case_into_context()` — L140-437 (setup + callback wiring)
- `step_clock_ctx()` — L65-137 (stepping logic)
- `_run_single_case_async()` — L470-558 (per-case flow)

### Shared Code (used by both)
- `nexus2/domain/automation/warrior_engine_entry.py` — `check_entry_triggers()`
- `nexus2/domain/automation/warrior_monitor.py` — `_check_all_positions()`
- `nexus2/domain/automation/warrior_engine.py` — `WarriorEngine`, `WatchedCandidate`
- `nexus2/adapters/simulation/mock_broker.py` — `MockBroker`

## Audit Claims to Investigate

### C1: Engine Initialization Difference
- **Sequential**: uses `get_engine()` global singleton from `warrior_routes.py`
- **Concurrent**: creates fresh `WarriorEngine()` via `SimContext.create()`
- **Question**: Does `get_engine()` carry configuration (settings, state) that `SimContext.create()` doesn't? Check `warrior_routes.py`'s engine init vs `SimContext.create()`.
- **Verification**: `Select-String -Path "nexus2\api\routes\warrior_routes.py" -Pattern "get_engine|WarriorEngine\("`

### C2: MockMarketData Initialization
- **Sequential** (L743-746): uses `get_mock_market_data()` singleton + `reset()`
- **Concurrent** (L196-198): creates fresh `MockMarketData()` instance
- **Question**: Does `get_mock_market_data()` carry state that `MockMarketData()` doesn't?
- **Verification**: `Select-String -Path "nexus2\adapters\simulation\__init__.py" -Pattern "get_mock_market_data"`

### C3: ContextVar Initialization
- **Sequential**: Does NOT set `sim_mode_ctx` ContextVar (relies on global state)
- **Concurrent** (L484-486): Sets `set_simulation_clock_ctx()` and `set_sim_mode_ctx(True)`
- **Question**: Does `trade_event_service.py` behave differently without `set_sim_mode_ctx`?
- **Verification**: `Select-String -Path "nexus2\domain\automation\trade_event_service.py" -Pattern "is_sim_mode|sim_mode_ctx"`

### C4: Callback Closure Differences
- **Sequential** callbacks use `get_warrior_sim_broker()` at runtime (closure over global)
- **Concurrent** callbacks capture `ctx.broker` via default args
- **Question**: Could `get_warrior_sim_broker()` return a different broker instance mid-execution?
- **Verification**: Trace `get_warrior_sim_broker` through the sequential path

### C5: Clock Initialization
- **Sequential** (L730): `reset_simulation_clock(start_time=start_time)` — resets global clock
- **Concurrent**: `SimContext.create()` creates a fresh `SimulationClock()`
- **Question**: Does `reset_simulation_clock` preserve any state that a fresh clock doesn't?
- **Verification**: Check `reset_simulation_clock` in `nexus2/adapters/simulation/__init__.py`

### C6: 60s Technicals Throttle
- Both paths call `check_entry_triggers(engine)` which includes the 60s throttle
- **Question**: Does the throttle use `time.time()` (wall clock) or sim clock? If wall clock, timing differences between sequential/concurrent could produce different throttle behavior.
- **Verification**: `Select-String -Path "nexus2\domain\automation\warrior_engine_entry.py" -Pattern "last_update|throttle|60|time.time"`

### C7: Engine State After `apply_settings_to_config`
- Phase 2 added a `sim_only` guard in `WarriorEngine.__init__`
- **Question**: Does `get_engine()` apply settings that change entry/exit behavior?
- **Verification**: Check if `apply_settings_to_config` affects sim mode behavior

## Expected Output

Write findings to `nexus2/runner_divergence_audit_report.md` with:

1. **File Inventory** — Lines, functions, imports for both paths
2. **Dependency Graph** — Import chains for each runner
3. **Duplication Analysis** — Side-by-side comparison of duplicated logic
4. **Divergence Findings** — For each claim (C1-C7):
   - Verified/Refuted with evidence
   - **Which runner is correct** if divergence found
   - Grep commands used for verification
5. **Root Cause Assessment** — Which divergence(s) most likely explain the P&L differences
6. **Refactoring Recommendations** — How to unify into one code path

## Priority Focus

**FLYE and RVSN** are the most revealing cases — they produce $0 in batch but actual trades (-$267.67 and $105.05) in GUI. This means the concurrent runner is **not even entering** trades that the sequential runner enters. Focus on what input difference would cause `check_entry_triggers` to skip entry on these symbols.
