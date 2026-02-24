# Backend Status: Guard Effectiveness Analysis

**Date:** 2026-02-23
**Agent:** Coordinator (acting as Backend)

## Summary

Implemented guard effectiveness analysis in two phases:
- **Phase 1**: `skip_guards` parameter for A/B batch comparison testing
- **Phase 2**: Counterfactual guard analysis with MFE/MAE and per-guard accuracy

## Files Modified

### Phase 1: A/B Batch Runs

| File | Change |
|------|--------|
| `warrior_sim_routes.py` | Added `skip_guards: bool = False` to `BatchTestRequest` |
| `warrior_sim_routes.py` | Passed `skip_guards` to `run_batch_concurrent()` |
| `sim_context.py` | Threaded `skip_guards` through `_run_case_sync` → `_run_single_case_async` |
| `sim_context.py` | Sets `engine.skip_guards = True` with sim-mode assertion |
| `warrior_entry_guards.py` | Added early return in `check_entry_guards()` when `skip_guards=True` |
| `warrior_entry_guards.py` | Added early return in `validate_technicals()` when `skip_guards=True` |

### Phase 2: Counterfactual Guard Analysis

| File | Change |
|------|--------|
| `trade_event_service.py` | Added `blocked_time` param + `blocked_price` field to `log_warrior_guard_block()` |
| `warrior_entry_guards.py` | Derives `_btime` from `engine._get_eastern_time()`, passes to all 11 call sites |
| `sim_context.py` | Extracts `blocked_price`/`blocked_time` from guard block metadata |
| `sim_context.py` | New `analyze_guard_outcomes()` function: per-block +5/15/30min price, MFE/MAE |
| `sim_context.py` | Added `guard_analysis` + `skip_guards` to case result dict |
| `gc_batch_diagnose.py` | Guard Effectiveness Analysis section in report output |

## Key Design Decisions

1. **`skip_guards` is SIM-only** — both `check_entry_guards` and `validate_technicals` assert `engine.monitor.sim_mode`
2. **Backward compatible** — `_run_case_sync` supports both 2-tuple and 3-tuple input
3. **Classification heuristic** — A block is "correct" if `price_15m < blocked_price` (would have lost money)
4. **Guard analysis is additive** — no existing behavior changes; analysis appended to results

## Usage

### Run baseline batch:
```
POST /warrior/sim/run_batch_concurrent
{"include_trades": true}
```

### Run A/B with guards disabled:
```
POST /warrior/sim/run_batch_concurrent
{"include_trades": true, "skip_guards": true}
```

### Compare results:
The `guard_analysis` field in each case result contains:
- `guard_accuracy`: fraction of blocks that were "correct"
- `net_guard_impact`: hypothetical P&L if guards hadn't blocked
- `by_guard_type`: per-guard breakdown (macd, sim_cooldown, etc.)
- `details`: per-block analysis with price at +5/15/30 min, MFE, MAE

## Verification Needed

- [ ] Restart server and confirm no import errors
- [ ] Run baseline batch (`skip_guards: false`)
- [ ] Run A/B batch (`skip_guards: true`)
- [ ] Verify `guard_analysis` appears in case results
