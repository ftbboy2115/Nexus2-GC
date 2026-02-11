# Phase 8 Trade Contamination Investigation Report

**Date:** 2026-02-10  
**Scope:** Round 1 Audit — Trade state leakage across batch runs  
**Auditor:** Code Auditor Agent  

---

## Executive Summary

The trade contamination investigation reveals **7 critical contamination vectors** in the batch runner infrastructure. The `batch_run_id` parameter was added to `warrior_db.py` during the concurrent runner development but was **never wired** — no caller passes it, no query filters by it, and its designated purge function has zero production callers. The result is that all batch cases write to and read from the same unscoped trade pool in `warrior.db`, guaranteeing data bleed-over between cases (especially in the concurrent runner where cases execute in parallel).

> [!CAUTION]
> The concurrent batch runner (`ProcessPoolExecutor`) is fundamentally broken for trade isolation. Multiple processes write unscoped trades to a shared SQLite file, and EOD close lookups return trades from other cases.

---

## I1: `log_warrior_entry()` Call Sites

### Finding: `batch_run_id` is NEVER Passed

The `batch_run_id` parameter exists in `log_warrior_entry()` (L282 of `warrior_db.py`) but **0 out of 9 callers** pass it.

| # | Caller | File:Line | Passes `batch_run_id`? | Passes `is_sim`? | Path |
|---|--------|-----------|:---------------------:|:----------------:|------|
| 1 | `enter_position()` | `warrior_engine_entry.py:1201` | ❌ | ✅ via `engine.config.sim_only` | SIM+LIVE |
| 2 | `complete_entry()` | `warrior_entry_execution.py:462` | ❌ | ✅ via `engine.config.sim_only` | SIM+LIVE |
| 3 | `_recover_position()` | `warrior_monitor_sync.py:403` | ❌ | ✅ `is_sim=False` (hardcoded) | LIVE only |
| 4 | `submit_warrior_sim_order()` | `warrior_sim_routes.py:413` | ❌ | ❌ (not passed at all) | SIM only |
| 5 | `backfill_warrior_trades()` | `warrior_broker_routes.py:472` | ❌ | ❌ (not passed) | LIVE only |
| 6-9 | Test files | Various | ❌ | Varies | TEST |

> [!IMPORTANT]
> **Risk:** Every trade logged by the concurrent batch runner has `batch_run_id=NULL`, making `purge_batch_trades()` useless — it filters on `batch_run_id` which is always NULL.

### Evidence

`warrior_engine_entry.py` L1201:
```python
log_warrior_entry(
    trade_id=order_id,
    symbol=symbol,
    entry_price=float(entry_price),
    ...
    is_sim=engine.config.sim_only,
    # batch_run_id is NOT passed
)
```

`sim_context.py` L467 creates `SimContext.create(case_id)` which generates `batch_id`, but this ID is **never forwarded** to the engine or any DB call.

---

## I2: Trade Query Functions — No Filtering

### Finding: ALL Query Functions Return Unscoped Results

Every query function in `warrior_db.py` that reads `warrior_trades` lacks `batch_run_id` and `is_sim` filtering:

| # | Function | File:Line | Filters by `batch_run_id`? | Filters by `is_sim`? | Impact |
|---|----------|-----------|:--------------------------:|:--------------------:|--------|
| 1 | `get_open_warrior_trades()` | L410 | ❌ | ❌ | Returns open trades from ALL runs |
| 2 | `get_warrior_trade_by_symbol()` | L428 | ❌ | ❌ | Returns first match from ANY run |
| 3 | `get_warrior_trade_for_recovery()` | L459 | ❌ | ❌ | Recovery picks up wrong trade |
| 4 | `get_all_warrior_trades()` | L882 | ❌ | Client filters post-query | Summary stats include all runs |
| 5 | `get_recent_closed_trades()` | L930 | ❌ | ❌ | R&D Lab analysis polluted |
| 6 | `get_warrior_trade_by_order_id()` | L574 | ❌ | ❌ | Could match wrong run |
| 7 | `get_warrior_trades_by_status()` | L738 | ❌ | ❌ | Returns all statuses globally |
| 8 | `check_scaling_positions()` | L722 | ❌ | ❌ | Scaling sync unscoped |

### Evidence

`get_warrior_trade_by_symbol()` L452:
```python
trade = db.query(WarriorTradeModel).filter(
    WarriorTradeModel.symbol == symbol,
    WarriorTradeModel.status.in_(active_statuses)
).first()  # Returns ANY active trade for symbol — from ANY batch run
```

---

## I3: Purge Logic — Critical Gaps

### Findings

#### `purge_sim_trades()` — Sequential Only
- **Definition:** `warrior_db.py:750`
- **Callers:** 1 production call at `warrior_sim_routes.py:1381` (sequential batch runner only)
- **Mechanism:** Deletes all rows with `is_sim=True`
- **Problem in concurrent context:** Would **delete trades from all concurrent processes**, not just the current one

#### `purge_batch_trades()` — Zero Production Callers
- **Definition:** `warrior_db.py:794`
- **Callers:** 0 production calls. Only exists in `test_concurrent_isolation.py:295` (signature check)
- **Mechanism:** Deletes rows matching `batch_run_id`
- **Problem:** Since `batch_run_id` is never set (see I1), this function is dead code

### Sequential vs Concurrent Purge Comparison

| Behavior | Sequential | Concurrent |
|----------|:---------:|:----------:|
| Purge before each case | ✅ `purge_sim_trades()` L1381 | ❌ No purge at all |
| Scope of purge | Global (all `is_sim` trades) | N/A |
| Safe for parallel? | ❌ (but runs sequentially) | ❌ (purge would kill other cases) |

> [!WARNING]
> Calling `purge_sim_trades()` in the concurrent runner would be **catastrophic** — it would delete trades from ALL concurrent processes mid-execution. `purge_batch_trades()` was designed for this purpose but was never connected.

---

## I4: SQLite Connection Isolation

### Finding: WAL Mode Enabled but Insufficient for Isolation

**Connection Setup** (`warrior_db.py:26-38`):
```python
warrior_engine = create_engine(
    WARRIOR_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

@event.listens_for(warrior_engine, "connect")
def set_sqlite_wal(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()
```

**Architecture:**
- `ProcessPoolExecutor` spawns separate OS processes → each gets its own Python interpreter + its own SQLAlchemy engine instance
- WAL mode enables concurrent reads during writes
- All processes share the same `warrior.db` file on disk

**Risk Assessment:**
| Aspect | Status | Note |
|--------|--------|------|
| WAL mode | ✅ Enabled | Prevents write-lock errors |
| `check_same_thread=False` | ✅ Set | Required for multi-threaded SQLAlchemy |
| Process-level isolation | ✅ | Each process has own connection pool |
| **Data-level isolation** | ❌ MISSING | All processes write to same table with no scoping |
| Concurrent DELETE risk | ⚠️ MEDIUM | If purge_sim_trades() were called, it would delete across processes |

**Conclusion:** SQLite connection handling is technically correct for concurrent access, but the **logical isolation** (scoping by `batch_run_id`) is completely absent, making the concurrent writes functionally contaminated.

---

## I5: Hidden State Leakage

### 5a. `EntryValidationLogModel` Table

**Location:** `warrior_db.py:142`  
**Risk:** This table has `is_sim` column but **no `batch_run_id` column**. Validation logs from all batch cases accumulate in the same table without scoping.

### 5b. `TradeEventService` — File-Based State

**Location:** `trade_event_service.py:79-84`
```python
self._warrior_log_path = Path(...) / "data" / "warrior_trade.log"
```

**Risk:** In `ProcessPoolExecutor` mode, multiple processes append to the same `warrior_trade.log` file simultaneously. While file writes are typically atomic at the OS level for small buffers, there's no locking and log lines may interleave.

### 5c. `MockBroker` State

**Status:** ✅ Properly isolated  
The concurrent runner creates a new `MockBroker` per `SimContext` (L37 of `sim_context.py`). Each process gets its own instance — no shared state.

### 5d. `WarriorEngine` / `WarriorMonitor` State

**Status:** ✅ Properly isolated  
Each `SimContext.create()` creates fresh instances (L40-51 of `sim_context.py`). Watchlists, positions, and pending entries are all per-context.

### 5e. `HistoricalBarLoader` State

**Status:** ✅ Properly isolated  
Each `SimContext` creates a new `HistoricalBarLoader()` (L57 of `sim_context.py`).

### 5f. `SimulationClock` State

**Status:** ✅ Properly isolated  
Each `SimContext` creates a new `SimulationClock()` (L34 of `sim_context.py`).

### Summary

| State Source | Isolated? | Risk |
|-------------|:---------:|------|
| MockBroker | ✅ | None |
| Engine/Monitor | ✅ | None |
| HistoricalBarLoader | ✅ | None |
| SimulationClock | ✅ | None |
| **warrior_trades table** | ❌ | **CRITICAL** — shared, unscoped |
| **entry_validation_log table** | ❌ | **HIGH** — shared, unscoped |
| **warrior_trade.log file** | ⚠️ | MEDIUM — concurrent appends |

---

## I6: EOD Close Path — Cross-Case Contamination

### Finding: Wrong Trade Retrieved for EOD Close

**Concurrent Runner EOD** (`sim_context.py:501-515`):
```python
# EOD close: force-close any open positions
from nexus2.db.warrior_db import get_warrior_trade_by_symbol, log_warrior_exit
trade = get_warrior_trade_by_symbol(pos_symbol)  # ← NO batch_run_id filter
if trade:
    log_warrior_exit(
        trade_id=trade["id"],
        exit_price=float(eod_price),
        exit_reason="eod_close",
        quantity_exited=pos_qty,
    )
```

**Failure Scenario:**
1. Process A runs case `LCFY_2026-01-16` → enters LCFY at $5.20
2. Process B runs case `LCFY_2025-12-15` → enters LCFY at $3.80
3. Both LCFY trades are written to `warrior_trades` (both with `batch_run_id=NULL`)
4. Process A reaches EOD → calls `get_warrior_trade_by_symbol("LCFY")`
5. SQLite returns **either** trade (`.first()` — nondeterministic order)
6. Process A closes **Process B's trade** with Process A's exit price
7. Process B then tries to close its trade → **trade not found** (already closed)

**Sequential Runner EOD** (`warrior_sim_routes.py:1428-1440`):  
Has the same `get_warrior_trade_by_symbol()` pattern, but is **less dangerous** because `purge_sim_trades()` runs between cases. Still, if a case trades the same symbol as a non-sim trade in the DB, it could close the wrong trade.

---

## Risk Summary

| # | Finding | Severity | Impact |
|---|---------|:--------:|--------|
| F1 | `batch_run_id` never passed to `log_warrior_entry()` | 🔴 CRITICAL | All batch trades are unscoped |
| F2 | No query function filters by `batch_run_id` or `is_sim` | 🔴 CRITICAL | Every lookup can return wrong trade |
| F3 | `purge_batch_trades()` has zero production callers | 🔴 CRITICAL | Designed function is dead code |
| F4 | EOD close retrieves wrong trade in concurrent mode | 🔴 CRITICAL | P&L attributed to wrong case |
| F5 | `EntryValidationLogModel` lacks `batch_run_id` | 🟡 HIGH | Validation logs mix between cases |
| F6 | Concurrent file appends to `warrior_trade.log` | 🟠 MEDIUM | Log interleaving |
| F7 | Sequential runner post-query filter only (`is_sim`) | 🟡 HIGH | Stats can include wrong trades |

---

## Recommendations

### R1: Wire `batch_run_id` End-to-End (🔴 CRITICAL)
1. Thread `batch_run_id` from `SimContext` through `WarriorEngine` to all `log_warrior_entry()` call sites
2. Add `batch_run_id` filter to `get_warrior_trade_by_symbol()`, `get_open_warrior_trades()`, and all query functions
3. Call `purge_batch_trades(ctx.batch_id)` in `_run_single_case_async()` after collecting results

### R2: Add `batch_run_id` to `EntryValidationLogModel`
Add the column and ensure validation logs are scoped per batch run.

### R3: Consider In-Memory Trade Tracking for Batch
Instead of using the shared SQLite DB for batch runs, each `SimContext` could maintain an in-memory trade list. The DB is only needed for:
- Live trading restart recovery
- Trade history UI
- R&D Lab analysis

Batch runs don't need persistence — they need isolation.

### R4: Fix Sequential Runner Query Scoping
The sequential runner's post-query `is_sim` filter (L1471) is fragile. Add `is_sim=True` to the SQL query itself.

### R5: Add File Locking for Trade Log
Use `threading.Lock` or `filelock` for `warrior_trade.log` writes in concurrent mode, or use per-batch log files.
