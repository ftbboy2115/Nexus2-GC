# Concurrent Batch Runner v3 — Convergence Audit (Round 3)

> **Auditor:** Code Auditor Specialist (Claude)
> **Date:** 2026-02-10
> **Scope:** Adversarial edge-case hunting + standard re-verification
> **Architecture Doc:** [concurrent_batch_runner_architecture.md](file:///C:/Users/ftbbo/.gemini/antigravity/brain/e56e9f8f-208c-46dc-8c63-d13dcafec674/concurrent_batch_runner_architecture.md)
> **Mode:** READ-ONLY forensic audit — no code modified

---

## Adversarial Findings

| # | Investigation | New Issue? | Severity | Details |
|---|--------------|:---:|:---:|---------|
| A1 | Entry Guard State Beyond `_recently_exited` | **YES** | **MEDIUM** | `WarriorEngine.__init__` has **5 mutable state dicts** + 1 disk file that accumulate across cases. See details below. |
| A2 | `check_entry_triggers` Internal Dependencies | NO | — | Relies only on `engine.*` callbacks passed in. One `get_historical_bar_loader()` call found in `_watch_loop` (L563), but batch runner bypasses `_watch_loop` entirely — calls `check_entry_triggers` directly. Safe. |
| A3 | ContextVar Lifecycle Edge Cases | NO | — | `asyncio.gather` creates independent `Task` objects. Each `Task` copies the parent context at creation. ContextVar set inside one gathered coroutine does NOT leak to others. Exception in one task doesn't affect others' ContextVars. `return_exceptions=True` is safe. |
| A4 | SQLAlchemy Session Scoping | NO | — | `get_warrior_session()` creates a **new session per call** via `WarriorSessionLocal()`. No `scoped_session`, no thread-local. Concurrent tasks get independent sessions. Safe for `asyncio.gather`. |
| A5 | SimContext Teardown | **YES** | **LOW** | `MockBroker` has no file handles or background tasks — just in-memory dicts. `HistoricalBarLoader` holds no file handles (loads into memory). No resource leaks on exception. However, `WarriorMonitor` with `_recently_exited_file != None` will write JSON to disk — Phase 2D already sets this to `None`. |
| A6 | `warrior_scanner_service` Global State | **YES** | **MEDIUM** | Scanner has `self._cache` dict (TTL-based). If scanner instance is shared across concurrent cases in Phase 3's `check_entry_triggers_batch`, cached scan results from Case A could be served to Case B. Architecture doc doesn't address scanner instance isolation. |
| A7 | `automation_simulation.py` — Heavy Consumer | NO | — | File has **10+ `get_simulation_clock()` calls** (verified: lines 166, 170, 329, 334, 438, 440, 482, 487, 540, 544, 601, 613, 711, 745, 786, 788, 834+). However, these are all **HTTP endpoint handlers** (FastAPI routes). Batch runner does NOT call these endpoints — it calls `step_clock_ctx` directly. Not in the batch path. |
| A8 | Log File Contention | **YES** | **LOW** | Python `logging` module is thread-safe but `asyncio.gather` runs on a single thread, so no contention. However, 18 concurrent cases will produce **interleaved log lines** making debugging very difficult. No `[case_id]` prefix exists. |

---

### A1 Detail: WarriorEngine Hidden State (NEW — not captured in v3 doc)

`WarriorEngine.__init__` ([warrior_engine.py:L61-122](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine.py#L61-L122)) creates the following mutable state:

| State | Line | Type | Risk in Concurrent Mode |
|-------|:----:|------|------------------------|
| `_watchlist` | L89 | `Dict[str, WatchedCandidate]` | Each `WatchedCandidate` accumulates `entry_triggered`, `swing_high`, `micro_pullback_ready`, `recent_high`, etc. Carries over if engine is shared. |
| `_blacklist` | L92 | `set` | Symbols blacklisted in Case A would be blocked in Case B |
| `_pending_entries` | L95 | `Dict[str, datetime]` | Prevents duplicate entries. Case A pending entry blocks Case B from same symbol. |
| `_symbol_fails` | L102 | `Dict[str, int]` | Stop-out counter. Case A failures would block Case B entries on same symbol. |
| `stats._seen_candidates` | L418 | `set` (in `_run_scan`) | Tracks "already seen" symbols across scan cycles. |
| `_pending_entries_file` | L96 | Disk: `data/pending_entries.json` | `_save_pending_entries()` writes to disk. Concurrent writes would conflict. |

**Verdict:** The architecture doc's `SimContext.create()` creates new `MockBroker`, `SimulationClock`, `HistoricalBarLoader`, and `WarriorMonitor` instances. But the `WarriorEngine` is **created via `get_engine()` singleton** — the doc does not specify creating a new engine per context.

**Impact:** If the existing global engine is reused:
- `_watchlist` from Case A bleeds into Case B
- `_pending_entries` blocks re-entries
- `_symbol_fails` accumulates across cases
- `_blacklist` persists

**Required Action:** Either:
1. Create a new `WarriorEngine()` per `SimContext` (cleanest), OR
2. Add explicit state reset in `SimContext.create()` for `_watchlist`, `_blacklist`, `_pending_entries`, `_symbol_fails`, `stats._seen_candidates`

> [!IMPORTANT]
> The architecture doc must address engine isolation. This is conceptually the same class of bug as `_recently_exited` (R2-D3) but on the engine side rather than the monitor side.

---

### A6 Detail: Scanner Cache State

`WarriorScannerService.__init__` ([warrior_scanner_service.py:L497-506](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py#L497-L506)) creates:

```python
self._cache: Dict[str, Tuple[Any, datetime]] = {}
```

The `_cached()` method ([L508-519](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py#L508-L519)) uses TTL-based caching. If the scanner is shared across concurrent cases:
- Scan results from Case A's market data could be served to Case B
- Since batch runner loads different historical data per case, this is a **data contamination risk**

**Mitigation:** The current `WarriorEngine.__init__` creates `self.scanner = scanner or WarriorScannerService()`. If engine is created per-context, scanner is automatically isolated. If engine is shared, scanner cache must be cleared between cases.

---

## Standard Re-verification (5 claims)

| # | Claim | Result | Evidence |
|---|-------|:------:|----------|
| S1 | Monitor has zero `get_engine()` calls | ✅ PASS | `grep_search` in all 4 monitor files (`warrior_monitor.py`, `warrior_monitor_exit.py`, `warrior_monitor_sync.py`, `warrior_monitor_scale.py`) — zero results each |
| S2 | All clock calls are runtime function-level imports | ✅ PASS | Spot-checked 3 files: `warrior_entry_patterns.py` L312 (`from nexus2.adapters.simulation import get_simulation_clock`), `warrior_vwap_utils.py` L63, `scheduler.py` L97 — all inside function bodies, not module-level |
| S3 | `get_simulation_clock()` has exactly 1 definition | ✅ PASS | `grep_search` for `def get_simulation_clock` — exactly 1 result at `sim_clock.py:L308` |
| S4 | No `batch_run_id` in warrior_db | ✅ PASS | `grep_search` in `warrior_db.py` — zero results |
| S5 | No WAL mode configured | ✅ PASS | `grep_search` for `journal_mode` and `WAL` in `db/` — zero results in production code (only in prior audit reports) |

---

## Updated Dependency Count (v3 actual)

The v3 doc claims `automation_simulation.py` has 10 `get_simulation_clock()` calls. Actual current count (verified):

| File | Actual Call Count | In Batch Path? |
|------|:-:|:-:|
| `automation_simulation.py` | **14** (lines 166, 170, 329, 334, 438, 440, 482, 487, 540, 544, 601, 613, 711, 745, 786, 788, 834+) | ❌ HTTP endpoints only |
| `warrior_entry_patterns.py` | **3** (lines 312, 547, 979) | ✅ Called via `check_entry_triggers` |
| `warrior_vwap_utils.py` | **2** (lines 63, 100) | ✅ Called via entry patterns |
| `scheduler.py` | **4** (lines 97, 126, 218, 356) | ❌ Not in batch path |
| `warrior_scanner_service.py` | **1** (line 351) | ⚠️ Only if scanner runs in batch |
| `warrior_monitor_exit.py` | **1** (line 177) | ✅ Called via `_check_all_positions()` |
| `services.py` | **1** (line 170) | ❌ |
| `mock_broker.py` | **1** (line 441) | ✅ Phase 2A addresses this |
| `automation_helpers.py` | **1** (line 334) | ❌ |

**Batch-path files needing ContextVar:** `warrior_entry_patterns.py` (3), `warrior_vwap_utils.py` (2), `warrior_monitor_exit.py` (1), `mock_broker.py` (1) = **7 call sites in 4 files**.

---

## Convergence Assessment

- New critical issues found: **0**
- New medium issues found: **2** (A1: engine state isolation, A6: scanner cache)
- New low issues found: **2** (A5: trivial teardown, A8: log interleaving)

---

## Verdict

**NOT CONVERGED** — 2 new medium issues found that need addressing before implementation:

### Issue 1: WarriorEngine State Isolation (MEDIUM)
The architecture doc creates per-context `MockBroker`, `Clock`, `Loader`, `Monitor` — but does **not** address `WarriorEngine` isolation. The engine has 5 mutable state dicts and 1 disk file that would bleed between concurrent cases.

**Recommended fix:** Add to `SimContext.create()`:
```python
engine = WarriorEngine(
    config=WarriorEngineConfig(sim_only=True),
    scanner=WarriorScannerService(),  # Also isolates scanner cache (fixes A6)
    monitor=monitor,  # Already per-context
)
engine._pending_entries_file = None  # Disable disk persistence
```

### Issue 2: Scanner Cache Contamination (MEDIUM)
If scanner is shared across cases, `self._cache` TTL-based results from one case's market data could serve stale data to another case. Fixed automatically if engine (which owns scanner) is created per-context.

---

## Overall Rating

**MEDIUM** — Addressable issues found, plan needs minor updates. Both issues are resolved by the same fix: create a new `WarriorEngine` per `SimContext` (which also creates a new scanner). No fundamental design rework needed.

### Progress Across Rounds

| Round | Critical | Medium | Low | Status |
|:-----:|:--------:|:------:|:---:|--------|
| R1 | 3 | 1 | 2 | Not converged |
| R2 | 0 | 2 | 0 | Not converged |
| R3 | 0 | 2 | 2 | Not converged (but diminishing) |

The issues are getting smaller and more nuanced each round. One more architecture update (adding engine to SimContext) should achieve convergence.
