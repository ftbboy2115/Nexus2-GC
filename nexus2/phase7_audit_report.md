# Phase 7 Audit Report — Performance Optimizations & ProcessPoolExecutor

**Auditor**: Code Auditor Specialist  
**Date**: 2026-02-10  
**Scope**: Phase 7 changes — phantom check skip, technical throttle, engine-scoped clock, ProcessPoolExecutor migration  

---

## A. File Inventory

| File | Lines | Key Functions | Imports |
|------|-------|---------------|---------|
| `warrior_engine_entry.py` | 1439 | `check_entry_triggers`, `check_orb_setup`, `check_micro_pullback_entry`, `enter_position` + 5 quality filters | 10 import groups |
| `warrior_entry_helpers.py` | 374 | `check_volume_confirmed`, `check_volume_expansion`, `check_high_volume_red_candle`, `check_active_market`, `check_falling_knife`, `update_candidate_technicals` | 5 imports |
| `sim_context.py` | 592 | `SimContext.create`, `step_clock_ctx`, `load_case_into_context`, `_run_case_sync`, `_run_single_case_async`, `run_batch_concurrent` | 7 imports |
| `warrior_sim_routes.py` | 1794 | `run_batch_tests`, `run_batch_concurrent_endpoint`, `step_clock`, `load_historical_test_case` | 14 imports |

---

## B. Dependency Graph (Phase 7 Scope)

```
warrior_engine_entry.py
  └── imports: warrior_entry_helpers.py (update_candidate_technicals, volume/market helpers)
  └── imports: warrior_entry_patterns.py, warrior_entry_guards.py, warrior_entry_sizing.py, etc.

warrior_entry_helpers.py
  └── imports: (typing, decimal, datetime, logging — no project deps)
  └── imported by: warrior_engine_entry.py, sim_context.py (indirectly via engine)

sim_context.py
  └── imports: sim_clock.py, mock_broker.py, historical_bar_loader.py, warrior_engine.py, warrior_scanner_service.py, warrior_monitor.py
  └── imported by: warrior_sim_routes.py (run_batch_concurrent)

warrior_sim_routes.py
  └── imports: sim_context.py (run_batch_concurrent), warrior_engine_entry.py (check_entry_triggers)
```

---

## C. Claims Verification

### C1: Phantom quote check skipped ONLY in sim mode ✅ PASS

**File**: `warrior_engine_entry.py` L357-388  
**Evidence**:

```python
# L360-363: Sim guard
is_sim = getattr(engine.config, 'sim_only', False)
if not is_sim:
    # L364-388: Full phantom check runs ONLY when not sim
    skip_phantom_check = False
    try:
        from nexus2.adapters.simulation.historical_bar_loader import get_historical_bar_loader
        loader = get_historical_bar_loader()
        if loader.has_10s_bars(symbol):
            skip_phantom_check = True
    except Exception:
        pass
    
    if engine._get_intraday_bars and not skip_phantom_check:
        # ... sanity check logic ...
```

**Verification**:
- L362: `is_sim = getattr(engine.config, 'sim_only', False)` — reads `sim_only` from engine config
- L363: `if not is_sim:` — entire phantom check block is wrapped in this guard
- **Sim mode**: `sim_only=True` → `is_sim=True` → `not is_sim = False` → phantom check SKIPPED ✅
- **Live mode**: `sim_only=False` → `is_sim=False` → `not is_sim = True` → phantom check RUNS ✅

**Verification command**: `Select-String -Path "nexus2\domain\automation\warrior_engine_entry.py" -Pattern "is_sim|sim_only|not is_sim" | Select-Object LineNumber, Line`

---

### C2: Technical throttle uses correct interval ✅ PASS

**File**: `warrior_engine_entry.py` L394-401  
**Evidence**:

```python
# L394-401
# UPDATE VWAP/EMA TRACKING for dynamic_score (TOP_PICK_ONLY uses this)
# Throttled to 60s intervals: with 10s stepping, technicals recompute 6x/min.
# MACD/EMA/VWAP don't meaningfully change in 10 seconds.
import time as _time
_last = getattr(watched, '_last_tech_update_ts', 0)
if _time.time() - _last >= 60:
    await update_candidate_technicals(engine, watched, current_price)
    watched._last_tech_update_ts = _time.time()
```

**Sub-checks**:
1. `_last_tech_update_ts` attribute checked: L398 uses `getattr(watched, '_last_tech_update_ts', 0)` ✅
2. First call always runs: default is `0`, so `_time.time() - 0 >= 60` is always `True` on first call ✅
3. Subsequent calls only after 60s: L399 checks `_time.time() - _last >= 60` ✅
4. Timestamp updated after call: L401 `watched._last_tech_update_ts = _time.time()` ✅

**Verification command**: `Select-String -Path "nexus2\domain\automation\warrior_engine_entry.py" -Pattern "_last_tech_update_ts|update_candidate_technicals" | Select-Object LineNumber, Line`

---

### C3: Global `get_sim_clock()` replaced with engine-scoped clock ✅ PASS

**File**: `warrior_entry_helpers.py` L295-304  
**Evidence** (inside `update_candidate_technicals`):

```python
# L295-304
# Use engine's per-context clock (concurrent sim), fall back to global (live)
clock = getattr(engine, '_sim_clock', None)
if clock is None:
    from nexus2.adapters.simulation.sim_clock import get_sim_clock
    clock = get_sim_clock()
if clock and clock.is_active():
    time_str = clock.get_time_string()  # "HH:MM"
    current_hour = int(time_str.split(':')[0])
```

**Sub-checks**:
1. `engine._sim_clock` checked first: L296 `clock = getattr(engine, '_sim_clock', None)` ✅
2. Falls back to global: L298-299 only imports `get_sim_clock` when `clock is None` ✅
3. Null-safe: L300 `if clock and clock.is_active():` — handles `clock = None` case safely ✅

**Verification command**: `Select-String -Path "nexus2\domain\automation\warrior_entry_helpers.py" -Pattern "_sim_clock|get_sim_clock|clock.is_active" | Select-Object LineNumber, Line`

---

### C4: `_sim_clock` wired in `load_case_into_context()` ✅ PASS

**File**: `sim_context.py` L432-434  
**Evidence**:

```python
# L432-434
# Attach per-context clock to engine for concurrent safety (Phase 7 Task 3)
# warrior_entry_helpers.update_candidate_technicals uses getattr(engine, '_sim_clock')
ctx.engine._sim_clock = ctx.clock
```

**Sub-checks**:
1. Set before function returns: L434, two lines before `return len(data.bars)` at L437 ✅
2. Uses `ctx.clock` (the per-context clock, not a global): ✅
3. Comment references the consumer (`warrior_entry_helpers.update_candidate_technicals`): ✅

**Verification command**: `Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "_sim_clock" | Select-Object LineNumber, Line`

---

### C5: `_run_case_sync` is a top-level function (picklable) ✅ PASS

**File**: `sim_context.py` L441-454  
**Evidence**:

```python
# L441 — Top-level function, NOT nested inside any class or function
def _run_case_sync(case_tuple: tuple) -> dict:
    """
    Run a single test case in a separate process.
    Must be a top-level function (picklable for ProcessPoolExecutor).
    Receives (case_dict, yaml_data_dict) as a tuple.
    """
    import asyncio
    case, yaml_data = case_tuple
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_run_single_case_async(case, yaml_data))
    finally:
        loop.close()
```

**Sub-checks**:
1. Not nested: `_run_case_sync` is at module scope (indentation = 0) ✅
2. Arguments are picklable: Receives `case_tuple: tuple` containing `(case: dict, yaml_data: dict)` — both plain Python dicts ✅
3. Return value is a plain dict: L452 returns result from `_run_single_case_async` which returns `dict` (verified at L524-535 and L538-545) ✅

**Verification command**: `Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "^def _run_case_sync|^async def _run_single_case_async" | Select-Object LineNumber, Line`

---

### C6: Result format matches sequential endpoint ⚠️ PARTIAL PASS

**Concurrent result dict** (`sim_context.py` L524-535):
```python
{
    "case_id", "symbol", "date", "bar_count",
    "trades",            # always []
    "realized_pnl",
    "unrealized_pnl",
    "total_pnl",
    "ross_pnl",
    "delta",
    "runtime_seconds",
}
```

**Sequential result dict** (`warrior_sim_routes.py` L1497-1511):
```python
{
    "case_id", "symbol", "date", "bar_count",
    "trades",            # populated from warrior_db
    "realized_pnl",
    "unrealized_pnl",
    "total_pnl",
    "ross_pnl",
    "delta",
    "max_capital_deployed",   # ← MISSING in concurrent
    "max_shares_held",        # ← MISSING in concurrent
    "runtime_seconds",
}
```

**Finding**: The concurrent result dict is **missing 2 keys** present in the sequential result:

| Key | Sequential | Concurrent |
|-----|-----------|------------|
| `case_id` | ✅ | ✅ |
| `symbol` | ✅ | ✅ |
| `date` | ✅ | ✅ |
| `bar_count` | ✅ | ✅ |
| `trades` | ✅ (populated) | ✅ (empty `[]`) |
| `realized_pnl` | ✅ | ✅ |
| `unrealized_pnl` | ✅ | ✅ |
| `total_pnl` | ✅ | ✅ |
| `ross_pnl` | ✅ | ✅ |
| `delta` | ✅ | ✅ |
| `max_capital_deployed` | ✅ | ❌ MISSING |
| `max_shares_held` | ✅ | ❌ MISSING |
| `runtime_seconds` | ✅ | ✅ |

**Severity**: LOW — These are informational metrics, not P&L-critical. The summary-level response format (returned by the endpoint) is structurally identical between both endpoints.

**Additional note**: The `trades` field is always `[]` in the concurrent path (L528) because each process runs in isolation and the `warrior_db` trades are not being queried. The sequential endpoint populates this from `warrior_db`. This is a known limitation of process-based isolation.

**Verification command**: `Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "case_id|symbol|date|bar_count|trades|realized_pnl|unrealized_pnl|total_pnl|ross_pnl|delta|runtime_seconds|max_capital|max_shares" | Select-Object LineNumber, Line`

---

## D. Refactoring Recommendations

| # | Issue | Files Affected | Action | Effort |
|---|-------|---------------|--------|--------|
| 1 | **Missing result keys** (C6) | `sim_context.py` L524-535 | Add `max_capital_deployed` and `max_shares_held` from `ctx.broker.get_account()` | S |
| 2 | **Empty `trades` list** in concurrent results | `sim_context.py` L528 | Either query warrior_db per-process or capture trades from MockBroker directly | M |
| 3 | **`import time as _time` inside loop body** (C2) | `warrior_engine_entry.py` L397 | Move `import time as _time` to module top level to avoid per-iteration import overhead | S |
| 4 | **Stale docstring** in concurrent endpoint | `warrior_sim_routes.py` L1570 | Docstring says "asyncio.gather()" but now uses ProcessPoolExecutor — update | S |
| 5 | **Duplicate volume/market helper functions** | `warrior_engine_entry.py` L109-325, `warrior_entry_helpers.py` L29-250 | `warrior_engine_entry.py` has full copies of functions already in `warrior_entry_helpers.py` (re-imports them AND defines them locally). The local copies shadow the imports and should be removed. | M |

---

## E. Adversarial Investigation: Duplication in warrior_engine_entry.py

During the audit, a significant duplication was discovered:

**`warrior_engine_entry.py` L28-34** imports these from `warrior_entry_helpers.py`:
```python
from nexus2.domain.automation.warrior_entry_helpers import (
    check_volume_confirmed,
    check_active_market,
    check_volume_expansion,
    check_falling_knife,
    check_high_volume_red_candle,
)
```

But then **L109-325** redefines identical copies of ALL five functions locally:
- `check_volume_confirmed` (L109-139) — exact duplicate of helpers L29-59
- `check_active_market` (L142-207) — exact duplicate of helpers L148-213
- `check_volume_expansion` (L210-244) — exact duplicate of helpers L62-96
- `check_falling_knife` (L247-281) — exact duplicate of helpers L216-250
- `check_high_volume_red_candle` (L284-325) — exact duplicate of helpers L99-140

The local definitions **shadow** the imports, meaning the imported versions are never used. This is ~216 lines of dead code.

**Recommendation**: Remove L109-325 from `warrior_engine_entry.py`. The imports at L28-34 already bring in the correct functions.

**Verification command**: `Select-String -Path "nexus2\domain\automation\warrior_engine_entry.py" -Pattern "^def check_volume_confirmed|^def check_active_market|^def check_volume_expansion|^def check_falling_knife|^def check_high_volume_red_candle" | Select-Object LineNumber, Line`

---

## F. Summary

| Claim | Result | Notes |
|-------|--------|-------|
| C1: Phantom check sim guard | ✅ PASS | `is_sim` guard correctly wraps phantom check |
| C2: Technical throttle 60s | ✅ PASS | First call always runs, subsequent throttled |
| C3: Engine-scoped clock | ✅ PASS | Falls back to global safely |
| C4: `_sim_clock` wiring | ✅ PASS | Set before function return |
| C5: `_run_case_sync` picklable | ✅ PASS | Top-level, dict in/out |
| C6: Result format parity | ⚠️ PARTIAL | Missing `max_capital_deployed`, `max_shares_held`; `trades` always empty |

**Overall Rating**: **HIGH** — All critical claims verified. Two minor informational keys missing from concurrent results (non-blocking).
