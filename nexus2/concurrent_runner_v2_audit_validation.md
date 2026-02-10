# Audit Validation Report: Concurrent Batch Runner v2 (Round 2)

**Validator:** Claude 4.5 Opus (Audit Validator Agent)  
**Date:** 2026-02-10  
**Auditor Report:** `concurrent_runner_v2_audit_report.md`  
**Mode:** READ-ONLY — no code modified  
**Verdict:** 19/20 claims CONFIRMED, 1 DISPUTED (non-critical count discrepancy)

---

## Claims Re-verified (20 total)

### Singleton Claims (1-4)

| # | Claim | Auditor Result | Validator Result | Evidence |
|---|-------|---------------|-----------------|----------|
| 1 | `get_warrior_sim_broker()` singleton with `threading.Lock()` | ✅ PASS | ✅ CONFIRMED | `warrior_sim_routes.py:L31-32`: `_warrior_sim_broker = None`, `_warrior_sim_broker_lock = threading.Lock()`. L35-38: `get_warrior_sim_broker()` uses `with _warrior_sim_broker_lock:` |
| 2 | `get_simulation_clock()` lazy-initialized singleton | ✅ PASS | ✅ CONFIRMED | `sim_clock.py:L305`: `_simulation_clock: Optional[SimulationClock] = None`. L308-313: `get_simulation_clock()` with `global _simulation_clock`, lazy init. Auditor line numbers exact match. |
| 3 | `get_historical_bar_loader()` lazy-initialized singleton | ✅ PASS | ✅ CONFIRMED | `historical_bar_loader.py:L465`: `_historical_bar_loader: Optional[HistoricalBarLoader] = None`. L468-473: lazy init pattern identical to sim_clock. |
| 4 | `get_engine()` delegates to `get_warrior_engine()` | ✅ PASS | ✅ CONFIRMED | `warrior_routes.py:L124-125`: `def get_engine() -> WarriorEngine: return get_warrior_engine()`. Two-line function, exact delegation. `get_warrior_engine()` at `warrior_engine.py:L730-748` is a lazy singleton. |

### Component Isolation Claims (5-10)

| # | Claim | Auditor Result | Validator Result | Evidence |
|---|-------|---------------|-----------------|----------|
| 5 | `MockBroker.__init__` uses only instance-level state | ✅ PASS | ✅ CONFIRMED | `mock_broker.py:L103-118`: Only `self._initial_cash`, `self._cash`, `self._orders`, `self._positions`, `self._current_prices`, `self._realized_pnl`, `self._max_capital_deployed`, `self._max_shares_held`. Zero global imports. |
| 6 | `MockBroker.sell_position()` calls `get_simulation_clock()` | ✅ PASS | ✅ CONFIRMED | `mock_broker.py:L441-443` (inside `sell_position`, L412-473): `from nexus2.adapters.simulation import get_simulation_clock`, runtime import inside function body. Used for timestamping sell orders. |
| 7 | `MockBroker` has no other `get_simulation_clock()` calls | ✅ PASS | ✅ CONFIRMED | Full code view of MockBroker class shows only one occurrence in `sell_position()`. No other methods reference it. |
| 8 | `WarriorMonitor.__init__` uses only instance state | ✅ PASS | ✅ CONFIRMED | `warrior_monitor.py:L53-107`: All assignments are `self._*` instance vars. Only non-instance reference is `Path(__file__)` for `_recently_exited_file` (file system path, not global state dependency). |
| 9 | `WarriorMonitor.set_callbacks()` uses only instance state | ✅ PASS | ✅ CONFIRMED | `warrior_monitor.py:L203-243`: 11 conditional `self._*` assignments, each guarded by `if xxx is not None:`. Zero global access. |
| 10 | `WarriorMonitor` has zero `get_engine()` calls | ✅ PASS | ✅ CONFIRMED | Grep for `get_engine` across all 4 monitor files (`warrior_monitor.py`, `warrior_monitor_exit.py`, `warrior_monitor_scale.py`, `warrior_monitor_sync.py`) — zero results. |

### Callback Verification (11)

| # | Claim | Auditor Result | Validator Result | Evidence |
|---|-------|---------------|-----------------|----------|
| 11 | `set_callbacks()` takes 11 parameters | ✅ PASS | ✅ CONFIRMED | `warrior_monitor.py:L203-213`: `get_price`, `get_prices_batch`, `get_quote_with_spread`, `get_intraday_candles`, `execute_exit`, `update_stop`, `get_broker_positions`, `record_symbol_fail`, `submit_scale_order`, `get_order_status`, `on_profit_exit` = 11 params. Init declares matching `self._*` vars at L62-73. |

### Dependency Count Claims (12-15)

| # | Claim | Auditor Result | Validator Result | Evidence |
|---|-------|---------------|-----------------|----------|
| 12 | `get_warrior_sim_broker` importers | ✅ PASS | ✅ CONFIRMED | File-level grep found 7 production files: `trade_event_service.py`, `warrior_db.py`, `warrior_positions.py`, `warrior_callbacks.py`, `warrior_sim_routes.py`, `alpaca_adapter.py`, `unified.py`. Auditor listed 6, architecture doc says 8. My count is 7 — within range, PASS. |
| 13 | `get_simulation_clock` — "13+ unique production files" | ⚠️ INACCURATE | ⚠️ DISPUTED — Auditor's correction correct | File-level grep found 11 non-definition production files: `warrior_scanner_service.py`, `warrior_entry_patterns.py`, `warrior_monitor_exit.py`, `services.py`, `warrior_vwap_utils.py`, `scheduler.py`, `warrior_sim_routes.py`, `warrior_callbacks.py`, `scheduler_routes.py`, `mock_broker.py`, `automation_simulation.py`. Auditor said 12 (counting `sim_clock.py` `__init__` re-export). My independent count is **11-12** depending on counting method. Original "13+" claim is slightly high. Auditor's INACCURATE verdict is itself correct. |
| 14 | `get_historical_bar_loader` — "5+ unique files" | ✅ PASS | ✅ CONFIRMED | File-level grep: `warrior_engine.py`, `warrior_engine_entry.py`, `warrior_callbacks.py`, `warrior_sim_routes.py`, `alpaca_broker.py` = 5 files + `__init__.py` re-export + definition file= 6-7 total. Auditor said 6 — matches. The "5+" claim holds. |
| 15 | `get_warrior_sim_broker` dependency count | ✅ PASS | ✅ CONFIRMED | 7 production files confirmed (see Claim 12). Matches auditor's claim range. |

### Definition & Safety Claims (16-20)

| # | Claim | Auditor Result | Validator Result | Evidence |
|---|-------|---------------|-----------------|----------|
| 16 | `get_simulation_clock` defined in exactly 1 place | ✅ PASS | ✅ CONFIRMED | `sim_clock.py:L308`: Only definition. `__init__.py` re-exports but does not define it. |
| 17 | No code imports `_simulation_clock` (private var) directly | ✅ PASS | ✅ CONFIRMED | Per-line grep `_simulation_clock` across entire nexus2 — only hits in `sim_clock.py:L305,309-313` (definition and usage in getter/resetter). No external file accesses the private var. |
| 18 | `check_entry_triggers(engine)` takes engine as parameter | ✅ PASS | ✅ CONFIRMED | `warrior_engine_entry.py:L333`: `async def check_entry_triggers(engine: "WarriorEngine") -> None:`. Engine passed as explicit param, not fetched from global. |
| 19 | `warrior_db` does NOT use WAL mode | ✅ PASS | ✅ CONFIRMED | Grep for `PRAGMA journal` in `nexus2/db/` — zero results. Default SQLite journal mode (DELETE) is in effect. |
| 20 | `warrior_db` has no `batch_run_id` column | ✅ PASS | ✅ CONFIRMED | Grep for `batch_run_id` in `nexus2/db/` — zero results. Schema has no such column. |

---

## Discovery Task Validation

### D1: Module-Level Clock Caching

**Auditor Finding:** ALL `get_simulation_clock()` calls are runtime imports inside functions — no module-level caching.

**Validator Result:** ✅ CONFIRMED

Per-line grep for `get_simulation_clock` across all production files shows every call follows the pattern:
```python
# Inside a function body:
from nexus2.adapters.simulation import get_simulation_clock
clock = get_simulation_clock()
```

Files verified via per-line grep output:
- `scheduler.py` — 4 inline imports (L97, L126, L218, L356)
- `warrior_entry_patterns.py` — 3 inline imports (L312, L547, L979)
- `warrior_vwap_utils.py` — 2 inline imports (L63, L100)
- `warrior_monitor_exit.py` — 1 inline import (L177)
- `services.py` — 1 inline import (L170)
- `warrior_scanner_service.py` — 1 inline import (L351)
- `automation_simulation.py` — multiple inline imports (L166, L248, L329, L438, L482, L540, L601, L711, L786, L834)

**No module-level `clock = get_simulation_clock()` found anywhere.** This is ContextVar-safe — each function call gets the current singleton/contextvar at call time.

---

### D2: Thread Usage

**Auditor Finding:** ZERO `threading.Thread` usage in sim routes or monitor files.

**Validator Result:** ✅ CONFIRMED

Grep for `threading.Thread` across entire nexus2:
- `quote_audit_service.py:L64,L74` — writer thread (audit domain, not batch path)
- `lab_routes.py:L552` — background thread (lab domain, not batch path)

**Zero `threading.Thread` in:** `warrior_sim_routes.py`, `warrior_monitor.py`, `warrior_monitor_exit.py`, `warrior_monitor_scale.py`, `warrior_monitor_sync.py`.

Only threading usage in batch path is `threading.Lock()` for broker singleton guard (`warrior_sim_routes.py:L32`).

---

### D3: `_recently_exited` — Hidden State

**Auditor Finding:** `_recently_exited` persisted to disk, not cleaned between batch test cases.

**Validator Result:** ✅ CONFIRMED

Directly observed in `WarriorMonitor.__init__` (L53-107):
- `L96`: `self._recently_exited: Dict[str, datetime] = {}`
- `L98`: `self._recently_exited_file = Path(__file__).parent.parent.parent.parent / "data" / "recently_exited.json"`
- `L99`: `self._load_recently_exited()` — loads from disk on init
- `L103`: `self._recently_exited_sim_time: Dict[str, datetime] = {}` — secondary dict, in-memory only

Batch runner (`warrior_sim_routes.py:L1378-1383`) only calls `purge_sim_trades()` (DB purge), does NOT clear `_recently_exited` dict or delete `recently_exited.json`.

**Concurrency risk CONFIRMED** — state bleed between test cases is real.

---

### D4: Batch Runner Callback Save/Restore

**Auditor Finding:** 9 callbacks saved (NOT the full 11). Missing `_record_symbol_fail` and `_on_profit_exit`.

**Validator Result:** ✅ CONFIRMED

Directly viewed `warrior_sim_routes.py:L1354-1364`:
```python
saved_callbacks = {
    '_get_price',
    '_get_prices_batch',
    '_get_intraday_candles',
    '_get_quote_with_spread',
    '_execute_exit',
    '_update_stop',
    '_get_broker_positions',
    '_submit_scale_order',
    '_get_order_status',
}
```

**Counted 9 callbacks.** `set_callbacks()` declares 11. Missing:
1. `_record_symbol_fail`
2. `_on_profit_exit`

Restore logic at L1531-1538 correctly iterates `saved_callbacks` and uses `setattr()`, so if the dict had all 11, the restore would work. The gap is in the save dict, not the restore logic.

---

## ContextVar Deep Validation

### `asyncio.gather()` and Context Propagation

> [!IMPORTANT]
> This is the **most critical** architectural question. The v2 plan relies on ContextVar-per-task isolation via `asyncio.gather()`.

**Analysis:**

Python's `asyncio.gather()` has two modes:
1. **Bare coroutines passed to gather:** `asyncio.gather(coro1(), coro2())` — gather wraps each coroutine in a `Task` internally via `ensure_future()`, which calls `asyncio.create_task()`.
2. **Pre-wrapped tasks:** `asyncio.gather(task1, task2)` — tasks already exist.

Per Python docs ([contextvars — Context Variables](https://docs.python.org/3/library/contextvars.html)):
> *"A copy of the current context is created when a `Task` is created."*

And from [asyncio.create_task](https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task):
> *"The task inherits the current context and will run in that context."*

**Key insight:** When `asyncio.gather()` internally wraps bare coroutines into Tasks, each Task gets a **copy** of the current context at task-creation time. This means:

```python
async def run_single_case(case):
    _sim_clock_var.set(ctx.clock)  # Set in THIS task's context
    # ... rest of execution uses this clock
    
# This works IF each coroutine is gathered from a context where
# _sim_clock_var.set() has already been called INSIDE the coroutine
results = await asyncio.gather(*[run_single_case(c) for c in cases])
```

**The v2 architecture is CORRECT** because:
1. Each `run_single_case()` coroutine sets its own ContextVar INSIDE the coroutine body
2. `asyncio.gather()` wraps each coroutine in its own Task (context copy)
3. Since `_sim_clock_var.set()` is called INSIDE each task, it modifies only that task's context copy
4. Other tasks don't see the mutation because they have their own copies

**However, there is a subtle risk:** If `_sim_clock_var.set()` is called BEFORE `asyncio.gather()` (in the parent context), ALL gathered tasks would start with the SAME parent context value. The v2 code correctly sets vars INSIDE each coroutine, so this is safe.

**Verdict: ContextVar approach is SOUND for `asyncio.gather()` with the v2 pattern.**

---

### Module-Level Caching

**Result: NONE FOUND** — All 11 production files use runtime imports inside function bodies. See D1 above for complete file list.

### Thread Usage in Batch Path

**Result: ZERO** — See D2 above. No background threads that could escape ContextVar scoping.

---

## Completeness Cross-Check

| Item | Auditor Count | Validator Count | Match? |
|------|---------------|-----------------|--------|
| `get_warrior_sim_broker` importers | 6 (Claim 12 files listed) | 7 unique production files | ⚠️ Close — auditor may not have counted `unified.py` |
| `get_simulation_clock` production files | 12 (corrected from 13+) | 11 (excl `__init__.py` re-export) | ⚠️ Off by 1 — depends on counting `__init__.py` |
| `get_historical_bar_loader` files | 6 | 5 (+ `__init__.py` = 6) | ✅ Match |

> [!NOTE]
> Count discrepancies are minor (±1) and depend on whether `__init__.py` re-exports and definition files are counted. The architecture plan's dependency surface estimates remain valid.

---

## Spot-Check Results (3 Unchecked Architecture Items)

| # | Architecture Claim (NOT in 20 claims) | Result | Evidence |
|---|--------------------------------------|--------|----------|
| S1 | `trade_event_service.py` uses `get_warrior_sim_broker()` as sim mode detection flag ("5 call sites") | ✅ CONFIRMED | File-level grep confirms `trade_event_service.py` imports `get_warrior_sim_broker`. Architecture doc Phase 2C addresses this with ContextVar `_is_sim_mode_var`. |
| S2 | `_recently_exited_file` is set to `Path(__file__).parent.parent.parent.parent / "data" / "recently_exited.json"` (shared path conflict in concurrent mode) | ✅ CONFIRMED | `warrior_monitor.py:L98`: exact path construction verified. All concurrent monitor instances would write to the same file. Architecture doc mitigates via `monitor._recently_exited_file = None` in `SimContext.create()`. |
| S3 | Monitor does NOT run background loop in batch mode — batch calls `_check_all_positions()` directly | ✅ CONFIRMED | Batch runner `step_clock` function at `warrior_sim_routes.py:L1093` (headless path) calls `monitor._check_all_positions()` directly. Monitor's background `asyncio.Task` loop is NOT started during batch runs. Architecture doc Phase 3 preserves this pattern in `step_clock_ctx`. |

---

## Overall Confidence

> **HIGH**

### Justification:
- **19/20 claims independently confirmed** — only Claim 13's original count is slightly off, but the auditor already caught and flagged this
- **All 4 discovery tasks confirmed** with independent evidence
- **ContextVar approach validated** — `asyncio.gather` + per-task `set()` is architecturally sound
- **No missed items found** — the auditor was thorough
- **Spot-checks all passed** — architecture doc claims not in the 20 claims were also accurate
- **One minor count discrepancy** in dependency numbers (±1 file depending on counting method) with no impact on architecture approach

### Summary of Auditor Work Quality:
The Code Auditor's Round 2 report was **high quality**:
- Correctly identified the "13+" overcounting and marked it INACCURATE
- Discovery tasks found real risks (D3/D4) with actionable mitigations
- Evidence was accurate and reproducible
- No false positives or fabricated claims detected
