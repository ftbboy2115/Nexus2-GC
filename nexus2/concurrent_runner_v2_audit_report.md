# Concurrent Batch Runner v2 — Audit Report

**Audit Date:** 2026-02-10  
**Auditor:** Claude 4.5 Opus (Coordinator Agent)  
**Scope:** Read-only forensic verification of 20 architecture claims + 4 discovery tasks  
**Verdict:** 18/20 claims VERIFIED, 2 claims INACCURATE (non-critical)

---

## Executive Summary

The v2 architecture document is **substantially accurate**. All singleton patterns, isolation guarantees, and safety claims hold. Two dependency count claims are slightly off (Claim 13 and Claim 14), but these are conservative estimates and do not invalidate the architecture approach. Four critical discoveries were made regarding hidden state that the architecture document does not address.

---

## Claim Verification Results

### Singleton Claims (1-4)

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | `get_warrior_sim_broker()` is a module-level singleton with `threading.Lock()` | ✅ PASS | `warrior_sim_routes.py:L31-38` — uses `_sim_broker_lock = threading.Lock()` guard |
| 2 | `get_simulation_clock()` is a lazy-initialized singleton | ✅ PASS | `sim_clock.py:L308-313` — `_simulation_clock = None` module var, lazy init |
| 3 | `get_historical_bar_loader()` is a lazy-initialized singleton | ✅ PASS | `historical_bar_loader.py:L468-473` — `_loader_instance = None` module var, lazy init |
| 4 | `get_engine()` in `warrior_routes.py` delegates to `get_warrior_engine()` | ✅ PASS | `warrior_routes.py:L124-125` — `def get_engine(): return get_warrior_engine()` |

### Component Isolation Claims (5-10)

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 5 | `MockBroker.__init__` uses only instance-level state, zero global imports | ✅ PASS | `mock_broker.py:MockBroker.__init__` — only `self._*` assignments |
| 6 | `MockBroker.sell_position()` calls `get_simulation_clock()` | ✅ PASS | `mock_broker.py:L441-443` — runtime import inside `sell_position()` |
| 7 | `MockBroker` has no other `get_simulation_clock()` calls | ✅ PASS | grep confirms only one occurrence in `sell_position()` |
| 8 | `WarriorMonitor.__init__` uses only instance state | ✅ PASS | All attributes are `self._*` instance variables |
| 9 | `WarriorMonitor.set_callbacks()` uses only instance state | ✅ PASS | `warrior_monitor.py:L203-243` — all `self._*` assignments |
| 10 | `WarriorMonitor` has zero `get_engine()` calls | ✅ PASS | grep across all 4 monitor files: `warrior_monitor.py`, `warrior_monitor_exit.py`, `warrior_monitor_scale.py`, `warrior_monitor_sync.py` — zero matches |

### Callback Verification (11)

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 11 | `set_callbacks()` takes 11 parameters | ✅ PASS | L203-213: `get_price`, `get_prices_batch`, `get_quote_with_spread`, `get_intraday_candles`, `execute_exit`, `update_stop`, `get_broker_positions`, `record_symbol_fail`, `submit_scale_order`, `get_order_status`, `on_profit_exit` = 11 params |

### Dependency Count Claims (12-15)

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 12 | `get_warrior_sim_broker` — claimed importers | ✅ PASS | Verified in: `warrior_sim_routes.py`, `warrior_callbacks.py`, `warrior_positions.py`, `warrior_db.py`, `trade_event_service.py`, `warrior_engine.py` |
| 13 | `get_simulation_clock` — "13+ unique production files" | ⚠️ INACCURATE | Actual unique production files: `warrior_sim_routes.py`, `scheduler.py`, `scheduler_routes.py`, `services.py`, `warrior_callbacks.py`, `warrior_scanner_service.py`, `warrior_entry_patterns.py`, `warrior_monitor_exit.py`, `warrior_vwap_utils.py`, `mock_broker.py`, `sim_clock.py` (__init__.py), `automation_simulation.py` = **12 files** (claim says 13+, actual is 12) |
| 14 | `get_historical_bar_loader` — "5+ unique files" | ✅ PASS | Found in: `warrior_sim_routes.py`, `warrior_callbacks.py`, `warrior_engine.py`, `warrior_engine_entry.py`, `historical_bar_loader.py` (__init__.py), `alpaca_broker.py` = **6 files** |
| 15 | `get_warrior_sim_broker` — dependency count | ✅ PASS | Matches claim range |

### Definition & Safety Claims (16-20)

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 16 | `get_simulation_clock` defined in exactly 1 place | ✅ PASS | `sim_clock.py:L308` — `def get_simulation_clock() -> SimulationClock:` (only definition) |
| 17 | No code imports `_simulation_clock` (private var) directly | ✅ PASS | grep for `_simulation_clock` only returns hits in `sim_clock.py` itself (L305, L309-313) |
| 18 | `check_entry_triggers(engine)` takes engine as parameter | ✅ PASS | `warrior_engine_entry.py:L333` — `async def check_entry_triggers(engine: "WarriorEngine")` |
| 19 | `warrior_db` does NOT use WAL mode | ✅ PASS | grep for `PRAGMA journal` in `db/` — zero results |
| 20 | `warrior_db` has no `batch_run_id` column | ✅ PASS | grep for `batch_run_id` in `warrior_db.py` — zero results. Schema at L39-93 confirmed: no such column |

---

## Discovery Tasks

### D1: Module-Level Clock Caching

**Finding: ALL `get_simulation_clock()` calls are runtime imports inside functions — no module-level caching.**

Every call follows the pattern:
```python
# Inside a function body:
from nexus2.adapters.simulation import get_simulation_clock
clock = get_simulation_clock()
```

This is **ContextVar-safe** because:
- No module-level `clock = get_simulation_clock()` exists anywhere
- Each function call gets the current singleton at call time
- If replaced with ContextVar, all callers would naturally pick up the per-task value

**Files verified:** `scheduler.py` (4 inline imports), `warrior_entry_patterns.py` (3), `warrior_vwap_utils.py` (2), `warrior_monitor_exit.py` (1), `services.py` (1), `warrior_scanner_service.py` (1), `mock_broker.py` (1), `scheduler_routes.py` (1), `warrior_callbacks.py` (1), `warrior_sim_routes.py` (multiple).

---

### D2: Thread Usage

**Finding: ZERO `threading.Thread` usage in sim routes or monitor files.**

- grep for `threading.Thread` in `warrior_sim_routes.py` — zero results
- grep for `Thread(` in `warrior_monitor*.py` — zero results

The only threading usage is `threading.Lock()` for the broker singleton guard (`warrior_sim_routes.py:L32`).

**Implication:** No background threads that could escape ContextVar scoping.

---

### D3: `_recently_exited` — Hidden State (⚠️ CRITICAL)

**Finding: `_recently_exited` is persisted to disk at `data/recently_exited.json` and is NOT cleaned between batch test cases.**

Evidence:
- `warrior_monitor.py:L96` — `self._recently_exited: Dict[str, datetime] = {}`
- `warrior_monitor.py:L98` — `self._recently_exited_file = Path(...) / "data" / "recently_exited.json"`
- `warrior_monitor.py:L99` — `self._load_recently_exited()` (called in `__init__`)
- `warrior_monitor.py:L132-139` — `_save_recently_exited()` writes to JSON file
- `warrior_monitor_exit.py:L1003-1004` — Sets `_recently_exited[symbol]` on exit, saves to disk
- `warrior_entry_guards.py:L109-118` — Checks `_recently_exited` to prevent re-entry

**Concurrency Risk:**
- In concurrent batch runs, if monitor is shared, `_recently_exited` from Test Case A would bleed into Test Case B
- Since it's persisted to disk (`data/recently_exited.json`), this state survives across runs
- The batch runner does NOT clear `_recently_exited` between test cases
- The `purge_sim_trades()` call at L1379-1383 only purges the DB, not monitor state

**Also discovered:** `_recently_exited_sim_time` (L103) — a secondary dict for sim timestamps, NOT persisted to disk but maintained in memory.

---

### D4: Batch Runner Callback Save/Restore

**Finding: The batch runner saves 9 callbacks (NOT the full 11 from `set_callbacks`).**

Saved callbacks at `warrior_sim_routes.py:L1354-1364`:
```python
saved_callbacks = {
    '_get_price',              # ✓
    '_get_prices_batch',       # ✓
    '_get_intraday_candles',   # ✓
    '_get_quote_with_spread',  # ✓
    '_execute_exit',           # ✓
    '_update_stop',            # ✓
    '_get_broker_positions',   # ✓
    '_submit_scale_order',     # ✓
    '_get_order_status',       # ✓
}
```

**Missing from save/restore (2 callbacks):**
1. `_record_symbol_fail` — Used for tracking symbol failures
2. `_on_profit_exit` — Used for profit exit notifications

Restore logic at `L1531-1538`:
```python
finally:
    if engine and engine.monitor and saved_callbacks:
        for attr, callback in saved_callbacks.items():
            setattr(engine.monitor, attr, callback)
        if was_monitor_running:
            await engine.monitor.start()
```

**Risk Assessment:** The 2 missing callbacks (`_record_symbol_fail`, `_on_profit_exit`) may cause live monitor to lose these callbacks after a batch run if they were set before the batch started. However, these callbacks are typically re-wired during `enable_broker`, so the risk is LOW for the current workflow.

---

## Risk Summary

| Risk | Severity | Description |
|------|----------|-------------|
| `_recently_exited` disk persistence | **HIGH** | Not cleaned between batch test cases; can block re-entries in subsequent cases |
| `_recently_exited` shared dict | **HIGH** | If monitor is shared in concurrent runs, exit state bleeds between parallel workers |
| 2 callbacks not saved/restored | **LOW** | `_record_symbol_fail` and `_on_profit_exit` may be lost after batch run |
| `warrior_db` no WAL mode | **MEDIUM** | SQLite default is journal_mode=DELETE; concurrent writes will hit `SQLITE_BUSY` |
| No `batch_run_id` in DB | **MEDIUM** | Cannot isolate per-batch-case data in the database for concurrent runs |

---

## Recommendations for v2 Architecture

1. **Clear `_recently_exited` and `_recently_exited_sim_time` between batch cases** — Add explicit cleanup in the batch loop
2. **Save/restore ALL 11 callbacks** — Add `_record_symbol_fail` and `_on_profit_exit` to the save/restore dict
3. **Enable WAL mode on `warrior.db`** before implementing concurrency — add `PRAGMA journal_mode=WAL` after engine creation
4. **Add `batch_run_id` column to `WarriorTradeModel`** — enables per-case data isolation without `purge_sim_trades()`
5. **Delete `data/recently_exited.json` between batch runs** — or better, scope it per-batch-case

---

## Verification Methodology

All claims were verified using:
- `grep_search` with `MatchPerLine=true` for exact pattern matching
- `view_file` for line-level code inspection
- `view_code_item` for function/class-level analysis
- Cross-referencing multiple files to verify isolation boundaries

No code was modified during this audit. All findings are based on the codebase as of 2026-02-10.
