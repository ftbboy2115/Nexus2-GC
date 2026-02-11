# Runner Divergence Audit Report

**Audit Date**: 2026-02-11  
**Auditor**: Claude (Code Auditor Agent)  
**Scope**: Sequential (`/sim/run_batch`) vs Concurrent (`/sim/run_batch_concurrent`) Warrior bot runners  
**Handoff Doc**: `runner_divergence_audit_handoff.md`

---

## Executive Summary

All 7 claims (C1–C7) are **CONFIRMED**. The sequential and concurrent runners traverse fundamentally different code paths for engine initialization, market data, clock management, callback wiring, sim-mode detection, technicals throttling, and engine state lifecycle. These differences **do cause P&L divergence**, with the concurrent runner producing the **more correct** results due to full isolation.

**Root Cause Ranking** (highest impact first):

| # | Root Cause | Impact | Affected Cases |
|---|-----------|--------|----------------|
| 1 | **C7: Engine state bleed-over** | `_watchlist`, `_pending_entries`, `_symbol_fails`, and `stats` carry across sequential cases | All divergent cases |
| 2 | **C6: Wall-clock throttle vs sim-clock** | `time.time()` throttle skips technicals updates in fast headless mode | Cases where MACD/EMA/VWAP gate entries |
| 3 | **C1+C7: `apply_settings_to_config` overrides `sim_only`** | Persisted settings may flip `sim_only=False` on sequential singleton | Cases affected by phantom quote check |

---

## File Inventory

| File | Lines | Runner Path | Role |
|------|-------|-------------|------|
| [warrior_sim_routes.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py) | 1794 | Both | API endpoints: `load_historical_test_case`, `step_clock`, `run_batch_tests`, `run_batch_concurrent_endpoint` |
| [sim_context.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/simulation/sim_context.py) | 605 | Concurrent | `SimContext.create`, `load_case_into_context`, `step_clock_ctx`, `_run_case_sync`, `run_batch_concurrent` |
| [warrior_engine.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_engine.py) | 750 | Both | `WarriorEngine.__init__`, `get_warrior_engine` singleton, `set_callbacks` |
| [warrior_routes.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/api/routes/warrior_routes.py) | 1086 | Sequential | `get_engine()` → delegates to `get_warrior_engine()` |
| [warrior_engine_entry.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py) | 1439 | Shared | `check_entry_triggers` (contains 60s throttle at L397-401) |
| [warrior_entry_helpers.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_entry_helpers.py) | 374 | Shared | `update_candidate_technicals` |
| [trade_event_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/trade_event_service.py) | ~800 | Shared | `is_sim_mode()`, `set_sim_mode_ctx()` |
| [mock_broker.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/simulation/mock_broker.py) | — | Shared | `MockBroker` |

---

## Claim-by-Claim Findings

### C1: Engine Initialization Difference — ✅ CONFIRMED

**Sequential** ([warrior_sim_routes.py#L1347](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L1347)):
```python
from nexus2.api.routes.warrior_routes import get_engine
engine = get_engine()  # → get_warrior_engine() → singleton
```
- Calls `get_warrior_engine()` which creates `WarriorEngine()` **once** with default config
- `WarriorEngine.__init__` calls `apply_settings_to_config(self.config, saved)` which may override `sim_only`, `risk_per_trade`, etc.
- Engine is **reused** across all batch cases without re-creation

**Concurrent** ([sim_context.py#L100-L115](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L100)):
```python
engine = WarriorEngine(
    config=WarriorEngineConfig(sim_only=True),
    scanner=WarriorScannerService(),
    monitor=monitor,
)
```
- Creates a **fresh** `WarriorEngine` per case with explicit `sim_only=True`
- But then `WarriorEngine.__init__` also calls `apply_settings_to_config`, so persisted settings may still override `sim_only`!

> [!WARNING]
> Both paths call `apply_settings_to_config` in `WarriorEngine.__init__` (L80-86). If persisted settings have `sim_only=False`, both paths lose the `sim_only=True` flag. The concurrent path *partially* mitigates this by setting it explicitly in the config constructor arg, but the `__init__` override still runs afterward.

**Verification**:
```
grep -n "apply_settings_to_config" nexus2/domain/automation/warrior_engine.py
# L84: apply_settings_to_config(self.config, saved)
```

**Impact**: **MEDIUM**. The sequential singleton carries config changes from previous runs (e.g., if the user changed `risk_per_trade` via the API). The concurrent path gets fresh config each time but both are vulnerable to `apply_settings_to_config` override.

---

### C2: MockMarketData Initialization — ✅ CONFIRMED

**Sequential** ([warrior_sim_routes.py#L813-L815](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L813)):
```python
mock_data = get_mock_market_data()  # Global singleton
mock_data.set_clock(clock)
```

**Concurrent** ([sim_context.py#L140-L437](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L140)):
- `load_case_into_context` uses `ctx.loader` (fresh `HistoricalBarLoader` per context)
- No `MockMarketData` singleton referenced

**Impact**: **LOW** for batch testing (only affects mock data routing). MockMarketData state from case N could theoretically bleed into case N+1 in sequential mode, but `reset()` calls mitigate this.

---

### C3: ContextVar Initialization — ✅ CONFIRMED

**Sequential**: Never calls `set_sim_mode_ctx(True)`. Relies on legacy fallback:
```python
# trade_event_service.py L~40
def is_sim_mode() -> bool:
    if _is_sim_mode.get():
        return True
    # Fallback to legacy global check
    from nexus2.api.routes.warrior_sim_routes import get_warrior_sim_broker
    return get_warrior_sim_broker() is not None
```

**Concurrent** ([sim_context.py#L486](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L486)):
```python
set_sim_mode_ctx(True)
```

**Impact**: **LOW-MEDIUM**. The legacy fallback works for the sequential path because `get_warrior_sim_broker()` returns a live singleton during batch runs. But any code that checks `_is_sim_mode.get()` directly (without the fallback) would fail to detect sim mode in the sequential path.

**Verification**:
```
grep -rn "set_sim_mode_ctx" nexus2/
# Only appears in sim_context.py (concurrent path)
# NEVER called in warrior_sim_routes.py (sequential path)
```

---

### C4: Callback Closure Differences — ✅ CONFIRMED

**Sequential** ([warrior_sim_routes.py#L870-L1000](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L870)):
```python
# Callbacks close over GLOBAL LOOKUPS
async def sim_get_price(symbol):
    broker = get_warrior_sim_broker()  # Runtime global lookup each call
    ...
```

**Concurrent** ([sim_context.py#L200-L400](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L200)):
```python
# Callbacks capture CONTEXT via default args
async def sim_get_price(symbol, _broker=ctx.broker):
    price = _broker.get_price(symbol)  # Bound to this context's broker
    ...
```

**Impact**: **LOW** in practice. The sequential runner's global lookup returns the same singleton broker that was set up for the batch, so there's no functional difference *per case*. However, if another async task modifies the singleton between calls, sequential could see interference.

---

### C5: Clock Initialization — ✅ CONFIRMED

**Sequential** ([warrior_sim_routes.py#L746](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L746)):
```python
clock = reset_simulation_clock(start_time=start_time)
```
- Uses global `_simulation_clock` singleton
- `reset_simulation_clock()` replaces the global singleton

**Concurrent** ([sim_context.py#L103](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L103)):
```python
clock = SimulationClock()
# Later:
set_simulation_clock_ctx(ctx.clock)
```
- Fresh clock per context + ContextVar for task-local access

**Impact**: **LOW** for batch (sequential runs cases one-at-a-time so only one clock is needed). Critical for true concurrent execution.

---

### C6: 60s Technicals Throttle — ✅ CONFIRMED (CRITICAL)

**Both paths** use the same shared code in [warrior_engine_entry.py#L397-L401](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py#L397):

```python
import time as _time
_last = getattr(watched, '_last_tech_update_ts', 0)
if _time.time() - _last >= 60:
    await update_candidate_technicals(engine, watched, current_price)
    watched._last_tech_update_ts = _time.time()
```

**The problem**: `time.time()` is **wall-clock time**, not simulation time. In headless batch mode, `step_clock(minutes=bar_count+30)` steps through all bars in a tight loop — the entire replay may take <1 second of wall-clock time.

**Sequential Impact**:
- `run_batch_tests` calls `step_clock(minutes=step_minutes, headless=True)` at L1406
- Each step iteration calls `check_entry_triggers(engine)` at L1165
- But `time.time()` barely advances between iterations → technicals update **exactly once** at the start, then are throttled for the rest of the replay

**Concurrent Impact**: Same behavior, but since each case starts with a fresh `WatchedCandidate` (via fresh `WarriorEngine`), `_last_tech_update_ts` starts at 0, so the *first* call always runs. Subsequent calls are throttled identically.

> [!CAUTION]
> This is **the primary candidate for P&L divergence on matching cases**. If any entry decision depends on an updated MACD/EMA/VWAP (via `update_candidate_technicals`), the 60s wall-clock throttle means technicals are effectively **frozen** after the first update in both runners. The divergence comes from **C7: state bleed-over** in the sequential path — if `_last_tech_update_ts` is NOT reset between cases, the sequential runner may skip the first technicals update entirely for subsequent cases.

**Verification**:
```
grep -n "time.time()" nexus2/domain/automation/warrior_engine_entry.py
# L399: if _time.time() - _last >= 60:
# L401: watched._last_tech_update_ts = _time.time()
```

---

### C7: Engine State After `apply_settings_to_config` — ✅ CONFIRMED (CRITICAL)

**Sequential**: The singleton `WarriorEngine` is reused across ALL batch cases. Between cases, `load_historical_test_case` is called again, which resets the broker and loader, but does **NOT** reset:

| State Field | Reset Between Cases? | Impact |
|------------|---------------------|--------|
| `_watchlist` | Partially (set to new symbol, but old entries may persist) | Stale watchlist entries could affect entry checks |
| `_pending_entries` | ❌ Never reset | Symbol from case N appears in case N+1's pending check |
| `_symbol_fails` | ❌ Never reset | Stop-out count from case N blocks entry in case N+1 |
| `stats` | ❌ Never reset | `entries_triggered`, `orders_submitted` accumulate |
| `config` (from saved settings) | ❌ Preserved | Any API config changes persist |
| `_last_tech_update_ts` (on WatchedCandidate) | ✅ New WatchedCandidate created per symbol | OK within a case, but see C6 |

**Concurrent**: Fresh `WarriorEngine` per case → all state starts clean.

**Verification** ([warrior_sim_routes.py#L1369-L1370](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L1369)):
```python
for case in cases:
    # ...
    load_result = await load_historical_test_case(case_id)
    # Engine singleton is NOT recreated here!
```

The `load_historical_test_case` function ([L690-1088](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L690)):
- Resets broker: `broker.reset()` ✅
- Resets mock data: `mock_data.set_clock(clock)` ✅
- Sets engine watchlist: `engine._watchlist[symbol] = ...` (adds, doesn't clear) ⚠️
- Does NOT reset: `engine._pending_entries`, `engine._symbol_fails`, `engine.stats` ❌

> [!IMPORTANT]
> **This is the most likely root cause for cases that diverge.** If a case triggers a stop-out and increments `_symbol_fails[symbol]`, a subsequent case with the same symbol would be blocked from entry in the sequential runner but not in the concurrent runner.

---

## Root Cause Assessment

### Primary Root Cause: C7 — Engine State Bleed-Over

The sequential runner's `run_batch_tests` reuses a global `WarriorEngine` singleton across all cases without resetting mutable state (`_pending_entries`, `_symbol_fails`, `stats`, and partial `_watchlist`). This causes:

1. **Entry blocking**: `_symbol_fails` from case N carries into case N+1
2. **Duplicate detection**: `_pending_entries` from case N could prevent entry in case N+1
3. **Watchlist contamination**: Old watchlist entries from case N persist alongside case N+1's symbol

### Secondary Root Cause: C6 — Wall-Clock Throttle

The 60s throttle uses `time.time()` instead of simulation clock time, so technicals are only computed once per real-time second regardless of how many sim minutes are stepped. This affects both runners equally per-case but interacts with C7 in the sequential path.

### Tertiary Root Cause: C1 — `apply_settings_to_config` Override

Both runners call `apply_settings_to_config` in `WarriorEngine.__init__`, which loads persisted settings from disk. If a user has saved `sim_only=False` (e.g., after enabling live trading), this overrides the explicit `sim_only=True` passed by the concurrent runner. This could cause the phantom quote check to run (or not run) differently between environments.

---

## Which Runner is Correct?

**The concurrent runner (`/sim/run_batch_concurrent`) is more correct** because:

1. Each case runs in complete isolation (fresh engine, broker, clock, loader)
2. No state leaks between cases
3. ContextVars are properly set for sim mode
4. Results are deterministic regardless of case order

The sequential runner suffers from execution-order dependencies. Running cases in a different order can produce different results.

---

## Refactoring Recommendations

### R1: Reset Engine State Between Sequential Cases (Quick Fix)

Add to `run_batch_tests` before each case:
```python
# Reset engine state between cases
engine._watchlist.clear()
engine._pending_entries.clear()
engine._symbol_fails.clear()
engine.stats = WarriorEngineStats()
```

### R2: Replace Wall-Clock Throttle with Sim-Clock Throttle (Important)

In `check_entry_triggers` ([warrior_engine_entry.py#L397-L401](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py#L397)):
```diff
-import time as _time
-_last = getattr(watched, '_last_tech_update_ts', 0)
-if _time.time() - _last >= 60:
-    await update_candidate_technicals(engine, watched, current_price)
-    watched._last_tech_update_ts = _time.time()
+# Use sim clock when available, wall clock otherwise
+clock = getattr(engine, '_sim_clock', None)
+if clock and clock.is_active():
+    current_ts = clock.get_elapsed_minutes()
+else:
+    import time as _time
+    current_ts = _time.time() / 60  # Convert to minutes
+_last = getattr(watched, '_last_tech_update_minutes', 0)
+if current_ts - _last >= 1:  # 1 sim-minute
+    await update_candidate_technicals(engine, watched, current_price)
+    watched._last_tech_update_minutes = current_ts
```

### R3: Guard `sim_only` After `apply_settings_to_config` (Important)

In `WarriorEngine.__init__` or `SimContext.create`, re-assert `sim_only=True` after loading settings:
```python
engine = WarriorEngine(config=WarriorEngineConfig(sim_only=True), ...)
engine.config.sim_only = True  # Guard against apply_settings_to_config override
```

### R4: Add `set_sim_mode_ctx(True)` to Sequential Path (Low Priority)

In `run_batch_tests`, add before the case loop:
```python
from nexus2.domain.automation.trade_event_service import set_sim_mode_ctx
set_sim_mode_ctx(True)
```

### R5: Long-Term — Unify Into Single Runner (Architectural)

Extract the shared simulation loop into a `run_single_case(context)` function that both runners call, eliminating the duplicated code paths entirely. The concurrent runner wraps this in `ProcessPoolExecutor`, the sequential runner calls it directly.

---

## Verification Commands

```powershell
# C1: Verify singleton vs fresh creation
Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "get_engine"
Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "WarriorEngine\("

# C3: Verify ContextVar usage
Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "set_sim_mode_ctx"
Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "set_sim_mode_ctx"

# C6: Verify throttle mechanism
Select-String -Path "nexus2\domain\automation\warrior_engine_entry.py" -Pattern "time.time\(\)"

# C7: Verify engine state reset
Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "_pending_entries|_symbol_fails|_watchlist.clear"
```
