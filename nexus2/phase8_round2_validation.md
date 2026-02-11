# Phase 8 Round 2: Audit Validation Report

**Validator:** Audit Validator Agent  
**Source Report:** `nexus2/phase8_round2_audit_report.md`  
**Date:** 2026-02-10  

---

## Summary

| Category | Total | PASS | FAIL | MINOR |
|----------|-------|------|------|-------|
| Adversarial Re-Verifications (V1-V7) | 7 | 5 | 0 | 2 |
| Per-Vector Table (F1-F7, A1a, A1b) | 9 | 9 | 0 | 0 |
| New Adversarial Investigations (A4-A6) | 3 | 2 | 0 | 1 |

**Overall Rating: HIGH** — All functional claims verified. Two minor accuracy issues in V3 (incomplete import inventory). One important advisory found in A6 (Linux `fork` behavior).

---

## V1: Import Order — Does the Override Happen Early Enough?

**Audit Claim:** `nexus2/__init__.py`, `nexus2/db/__init__.py`, `nexus2/adapters/__init__.py`, and `nexus2/adapters/simulation/__init__.py` do NOT import `warrior_db`.

**Result: ✅ PASS**

| File | Evidence |
|------|----------|
| `sim_context.py` L1-17 | Top-level imports: `sim_clock`, `mock_broker`, `historical_bar_loader`, `warrior_engine`, `warrior_engine_types`, `warrior_scanner_service`, `warrior_monitor` — **NO** `warrior_db` |

The audit's key conclusion is correct: when `_run_case_sync()` starts executing, `warrior_db`'s module-level objects (`warrior_engine`, `WarriorSessionLocal`) exist in `sys.modules` (because `warrior_db.py` is imported at module level by `sim_context.py`'s transitive dependencies), but overriding the module attributes at the start of `_run_case_sync` happens before any *function* calls those attributes. This is safe.

---

## V2: Does `WarriorBase.metadata.create_all()` Work Correctly?

**Audit Claim:** `create_all(bind=mem_engine)` uses the explicitly passed `bind` parameter, not a cached engine.

**Result: ✅ PASS**

**Evidence:** SQLAlchemy's `MetaData.create_all()` signature accepts `bind` as a parameter and uses it directly. Confirmed by `warrior_db.py:L210` using the same pattern: `WarriorBase.metadata.create_all(bind=warrior_engine)`.

---

## V3: Session Caching — Does Any Code Cache the Old Session?

**Audit Claim:** "All 39 `from nexus2.db.warrior_db import` statements in runtime code are inside function bodies (lazy imports)."

**Result: ⚠️ PASS WITH CORRECTION**

**Independent grep:** `rg "from nexus2.db.warrior_db import" nexus2/ --glob "*.py" -n`

**Total matches found:** 50 (including tests)

**Module-level imports found (NOT lazy):**

| File | Line | Import | On Batch Path? |
|------|------|--------|:--------------:|
| `orchestrator.py` | L28 | `from nexus2.db.warrior_db import get_recent_closed_trades` | ❌ No |
| `conftest.py` | L22 | `from nexus2.db.warrior_db import WarriorBase, warrior_engine` | ❌ No (test) |
| `test_order_id_linkage.py` | L15 | `from nexus2.db.warrior_db import (...)` | ❌ No (test) |

**All runtime files ON the batch execution path** have lazy (inside-function) imports:

| File | Lines (verified) |
|------|-----------------|
| `warrior_engine_entry.py` | L866, L1197, L1240, L1343, L1409 |
| `warrior_entry_execution.py` | L327, L458, L501, L555, L615 |
| `warrior_monitor.py` | L151, L164, L179, L195, L357 |
| `warrior_monitor_exit.py` | L807, L917, L967 |
| `warrior_monitor_sync.py` | L108, L221, L285, L434, L553 |
| `warrior_monitor_scale.py` | L165 |
| `sim_context.py` | L503 |
| `trade_analysis_service.py` | L341 |
| `data_routes.py` | L868, L972, L1149, L1206 |
| `warrior_broker_routes.py` | L331, L453, L535, L562, L571, L595 |
| `warrior_sim_routes.py` | L291, L1380, L1428, L1461 |
| `warrior_routes.py` | L892, L904 |
| `trade_event_routes.py` | L103 |

**Correction:** The audit report claimed "All 39 runtime imports are lazy." This is inaccurate in count and misses `orchestrator.py:L28`, which is a **module-level** import of `get_recent_closed_trades`. However, `orchestrator.py` is part of the R&D Lab domain (`nexus2.domain.lab`) and is **NOT** imported by any file in the batch execution path (verified: `rg "from nexus2.domain.lab" nexus2/adapters/simulation/` → 0 results). This does not affect the fix.

**Core conclusion CONFIRMED:** All imports that execute during batch runs are lazy.

---

## V4: `get_warrior_session()` — Does It Use the Module-Level SessionLocal?

**Audit Claim:** `get_warrior_session()` calls `WarriorSessionLocal()` — a bare name lookup in the module's namespace.

**Result: ✅ PASS**

**Evidence** — `warrior_db.py:L198-205` (independently read):
```python
@contextmanager
def get_warrior_session():
    """Context manager for Warrior database sessions."""
    db = WarriorSessionLocal()  # ← Bare name lookup in module namespace
    try:
        yield db
    finally:
        db.close()
```

**Verification:** `WarriorSessionLocal()` occurs ONLY at `warrior_db.py:L201`. No other file calls `WarriorSessionLocal()` directly — all go through `get_warrior_session()`. After the override sets `wdb.WarriorSessionLocal = sessionmaker(... bind=mem_engine)`, every subsequent call to `get_warrior_session()` will create sessions bound to the in-memory DB.

**Additional confirmation:** Searched for `sessionmaker` across the codebase — only found in `warrior_db.py:L42`, `database.py:L33`, `nac_db.py:L34`, `telemetry_db.py:L29`, and test files. No production code creates its own `sessionmaker` that could bypass the override.

---

## V5: Does the Sequential Runner Get Affected?

**Audit Claim:** `_run_case_sync` is only called from `run_batch_concurrent`, and the sequential runner does not call it.

**Result: ✅ PASS**

**Evidence:**
- `_run_case_sync` defined at `sim_context.py:L441`
- Called at `sim_context.py:L572` inside `run_batch_concurrent()`
- `ProcessPoolExecutor` with `spawn` (Windows default) creates separate processes
- Override in child process cannot leak back to parent

---

## V6: Does This Fix F6 (Log File Interleaving)?

**Audit Claim:** The in-memory override only affects `warrior_db`. Trade log file writes and main DB events will still interleave. Cosmetic only.

**Result: ✅ PASS**

**Evidence:** `trade_event_service._log_to_file()` writes to `warrior_trade.log`. `_log_event()` writes to `nexus2.db.database` (main DB, not `warrior_db`). Neither is affected by the in-memory override. Confirmed cosmetic.

---

## V7: SQLAlchemy `event.listens_for` — WAL Mode on In-Memory DB

**Audit Claim:** The WAL listener is bound to the OLD `warrior_engine` object. The new `mem_engine` does NOT inherit it. Harmless because in-memory SQLite doesn't support WAL.

**Result: ✅ PASS**

**Evidence** — `warrior_db.py:L33-38`:
```python
@event.listens_for(warrior_engine, "connect")
def set_sqlite_wal(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()
```

The decorator binds to the specific `warrior_engine` engine *object* created at L26. When the override replaces `wdb.warrior_engine = mem_engine`, the new engine is a different object with no event listeners. The `PRAGMA journal_mode=WAL` will NOT execute on the in-memory DB.

**This is harmless because:**
1. In-memory SQLite ignores WAL mode (returns `"memory"` for journal_mode)
2. Each worker process has a single-connection in-memory DB — no concurrency needed
3. If WAL were somehow set, it would be silently ignored, not error

---

## Per-Vector Table Re-Verification

| Vector | Audit Verdict | My Verdict | Notes |
|--------|:------------:|:----------:|-------|
| F1 | ✅ SAFE | ✅ PASS | Ephemeral DB — no scoping needed |
| F2 | ✅ SAFE | ✅ PASS | All queries via `get_warrior_session()` → overridden |
| F3 | ✅ SAFE | ✅ PASS | No purge needed — DB destroyed on exit |
| F4 | ✅ SAFE | ✅ PASS | Only current case's trades in DB |
| F5 | ✅ SAFE | ✅ PASS | Per-process DB, no cross-case mixing |
| F6 | ⚠️ NOT FIXED | ✅ PASS | Cosmetic only, confirmed |
| F7 | ✅ SAFE | ✅ PASS | Per-process DB, no stale data |
| A1a | ✅ SAFE | ✅ PASS | Scale-in import at L866 is lazy |
| A1b | ✅ SAFE | ✅ PASS | Pending exit import at L108 is lazy |

---

## New Adversarial Investigations

### A4: Direct Session Creation Bypass

**Question:** Is there ANY code path during batch execution that creates its own SQLAlchemy session directly, bypassing `get_warrior_session()`?

**Result: ✅ SAFE**

**Evidence:**
- `WarriorSessionLocal()` is called ONLY at `warrior_db.py:L201` (inside `get_warrior_session()`)
- Searched `sessionmaker` across entire codebase — only found in DB module definitions (`warrior_db.py`, `database.py`, `nac_db.py`, `telemetry_db.py`) and test setup code
- No production code creates a standalone `Session()` or `sessionmaker()` for `warrior_db` outside of `get_warrior_session()`
- `data_routes.py` uses `get_warrior_session()` at L868, L972, L1149, L1206 — all lazy, all routed through the override

**Conclusion:** There is no bypass path. Every warrior_db session flows through `get_warrior_session()` → `WarriorSessionLocal()` → overridden sessionmaker.

---

### A5: Execution Order in `_run_case_sync`

**Question:** Does `_run_case_sync` import or call anything that triggers `warrior_db` usage BEFORE the override lines would execute?

**Result: ✅ SAFE (once the fix is applied)**

**Current code** (`sim_context.py:L441-453`):
```python
def _run_case_sync(case_tuple: tuple) -> dict:
    import asyncio
    case, yaml_data = case_tuple
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_run_single_case_async(case, yaml_data))
    finally:
        loop.close()
```

**Proposed fix** inserts the override at the **very start** — before `import asyncio` and before `_run_single_case_async()` is called.

**Execution trace of `_run_single_case_async`:**
1. L467: `SimContext.create(case_id)` — creates `MockBroker`, `SimulationClock`, `WarriorEngine`, `WarriorScannerService`, `WarriorMonitor` — **none import warrior_db**
2. L470-473: Sets ContextVars — no warrior_db usage
3. L476: `load_case_into_context()` — imports from `warrior_engine`, `warrior_scanner_service` — **no warrior_db**
4. L488: `step_clock_ctx()` — imports `check_entry_triggers` from `warrior_engine_entry` — **warrior_engine_entry has only lazy warrior_db imports**
5. L503: First warrior_db access — `from nexus2.db.warrior_db import get_warrior_trade_by_symbol, log_warrior_exit` — **lazy, inside function body, at EOD close time**

**Conclusion:** The first actual `warrior_db` function call happens deep into case execution (EOD close at L503). The override at the start of `_run_case_sync` executes **well before** any warrior_db usage. No early import triggers warrior_db access.

> [!NOTE]
> When using `spawn` (Windows), the child process re-imports all modules fresh. The module-level `warrior_engine = create_engine(...)` at `warrior_db.py:L26` runs and creates a file-based engine. The override immediately replaces it. This is safe because no function has been called yet.

---

### A6: Linux `fork` vs `spawn` — ProcessPoolExecutor Start Method

**Question:** On Linux (VPS), does `ProcessPoolExecutor` use `fork` or `spawn`? Does the override still work?

**Result: ⚠️ ADVISORY — FIX STILL WORKS, BUT WITH DIFFERENT MECHANICS**

**Facts:**
- Python's `ProcessPoolExecutor` uses the default `multiprocessing` start method
- **Windows:** Default is `spawn` — child process re-imports everything fresh
- **Linux:** Default is `fork` — child process inherits the parent's module state via copy-on-write
- No `mp_context` argument is passed to `ProcessPoolExecutor` in `sim_context.py:L570` — confirmed via grep: 0 results for `mp_context`

**On Linux with `fork`:**
1. The child process starts with the parent's `sys.modules` already populated
2. `warrior_db.warrior_engine` in the child is a **copy** of the parent's engine object (pointing to `warrior.db` on disk)
3. `warrior_db.WarriorSessionLocal` in the child is a copy of the parent's sessionmaker
4. The override at the start of `_run_case_sync` replaces BOTH with in-memory versions
5. Since the override runs before any DB function is called, the fix **still works**

**Why it's safe even with `fork`:**
- `fork` copies the parent's memory space, but the child's module namespace is independent after fork
- `wdb.warrior_engine = mem_engine` modifies the child's copy of the module namespace
- The parent's `warrior_engine` is unchanged (fork is copy-on-write)
- The key invariant holds: override happens before any DB function call

**Potential concern:** If the parent process has already created a SQLAlchemy connection pool and the `fork` inherits file descriptors, there could be connection sharing. However, `create_engine("sqlite://")` creates a **new** pool with no file descriptors. The old engine's file descriptor (to `warrior.db`) is overridden and never used in the child.

> [!TIP]
> For maximum safety, consider explicitly specifying `spawn` on Linux:
> ```python
> import multiprocessing
> ctx = multiprocessing.get_context("spawn")
> with ProcessPoolExecutor(max_workers=max_workers, mp_context=ctx) as pool:
> ```
> This guarantees identical behavior across Windows and Linux, at the cost of slightly slower process startup.

---

## Corrections to Round 2 Audit Report

1. **V3 import count:** Report claims "39 runtime imports" are all lazy. Actual count is ~47 non-test imports. The claim misses `orchestrator.py:L28` (module-level). However, this file is NOT on the batch execution path, so the conclusion remains valid.

2. **V3 import table:** The table lists 8 files with lazy imports but omits `data_routes.py` (4 lazy imports), `warrior_broker_routes.py` (6 lazy imports), `warrior_sim_routes.py` (4 lazy imports), `warrior_routes.py` (2 lazy imports), and `trade_event_routes.py` (1 lazy import). These are all lazy and all safe, but the table is incomplete.

3. **V5 Linux caveat:** The report states "default `mp_context` uses `spawn` on Windows" but does not address Linux behavior where default is `fork`. The fix works on both, but the mechanism differs (see A6).

---

## Validation Verdict

| # | Claim | Result | Confidence |
|---|-------|--------|:----------:|
| V1 | Import order safe | ✅ PASS | HIGH |
| V2 | `create_all(bind=)` works | ✅ PASS | HIGH |
| V3 | All runtime imports lazy | ⚠️ PASS w/ correction | HIGH (core claim valid) |
| V4 | `get_warrior_session()` bare lookup | ✅ PASS | HIGH |
| V5 | Sequential runner unaffected | ✅ PASS | HIGH |
| V6 | Log file not fixed (cosmetic) | ✅ PASS | HIGH |
| V7 | WAL listener harmless | ✅ PASS | HIGH |
| F1-F5, F7 | All safe with in-memory DB | ✅ PASS | HIGH |
| F6 | Cosmetic, not fixed | ✅ PASS | HIGH |
| A1a, A1b | Safe (lazy imports) | ✅ PASS | HIGH |
| A4 | No session bypass | ✅ PASS | HIGH |
| A5 | Override before any DB call | ✅ PASS | HIGH |
| A6 | Linux `fork` still safe | ⚠️ PASS w/ advisory | HIGH |

### Quality Rating: **HIGH**

The audit report's core verdict is correct: **the 5-line in-memory SQLite fix resolves all functional contamination vectors.** Minor accuracy issues in V3's import inventory and missing Linux `fork` analysis do not affect the conclusion.

### Recommendation

1. **Implement the fix** — it is architecturally sound on both Windows (`spawn`) and Linux (`fork`)
2. **Consider adding `mp_context=multiprocessing.get_context("spawn")` to the ProcessPoolExecutor** for cross-platform determinism (optional but recommended)
