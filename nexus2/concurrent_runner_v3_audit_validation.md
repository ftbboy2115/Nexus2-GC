# Audit Validation Report: Concurrent Batch Runner v3 (Round 3)

> **Validator:** Audit Validator (Claude)  
> **Date:** 2026-02-10  
> **Auditor's Report:** [concurrent_runner_v3_audit_report.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/concurrent_runner_v3_audit_report.md)  
> **Mode:** READ-ONLY validation — no code modified

---

## Adversarial Findings Re-verified (A1-A8)

| # | Auditor Finding | Validator Result | Evidence |
|---|----------------|:------:|----------|
| A1 | WarriorEngine has 5 mutable dicts + disk file | ✅ **CONFIRMED** | Independently viewed [warrior_engine.py:L61-122](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine.py#L61-L122). Verified: `_watchlist` (L89), `_blacklist` (L92), `_pending_entries` (L95), `_symbol_fails` (L102), `_pending_entries_file` (L96). Also confirmed `stats._seen_candidates` at L418-419. The `get_warrior_engine()` at L730-748 is a singleton — no per-context creation. |
| A2 | `check_entry_triggers` internal deps — safe | ✅ **CONFIRMED** | `grep_search` for `get_historical_bar_loader` in `warrior_engine_entry.py` — zero results. Same in `warrior_engine.py` — zero results. The `_watch_loop` (L536-594) does import `get_historical_bar_loader` at L563, but batch runner bypasses `_watch_loop`. Matches auditor conclusion. |
| A3 | ContextVar lifecycle — safe with `asyncio.gather` | ✅ **CONFIRMED (no dispute)** | Python docs confirm: `asyncio.create_task()` copies the current context at task creation. `return_exceptions=True` means one exception doesn't cancel others. Auditor's analysis is correct. |
| A4 | SQLAlchemy sessions — new per call | ✅ **CONFIRMED** | `warrior_db.py:L33`: `WarriorSessionLocal = sessionmaker(...)`. `get_warrior_session()` at L186-192 calls `WarriorSessionLocal()` — new session each time. `grep_search` for `scoped_session` in `db/` — zero results. No thread-local sessions. |
| A5 | SimContext teardown — no resource leaks | ✅ **CONFIRMED** | `MockBroker.__init__` (L103-118) only creates in-memory dicts. `SimulationClock.__init__` (L31-47) only sets `_current_time`, `_speed`, `_running`. `HistoricalBarLoader.__init__` (L269-278) only sets path + dict. No file handles, no background tasks. |
| A6 | Scanner `_cache` contamination risk | ✅ **CONFIRMED** | `warrior_scanner_service.py:L506`: `self._cache: Dict[str, Tuple[Any, datetime]] = {}`. Used at L694 (ETF set, 24h TTL), L853 (country, 30d TTL), L961 (former runner, 6h TTL), L1202 (float, 24h TTL), L1620 (EMA200, 6h TTL). If scanner is shared, cached results contaminate across cases. Auditor correct that per-context engine creation fixes this. |
| A7 | `automation_simulation.py` — not in batch path | ✅ **CONFIRMED** | These are HTTP endpoint handlers (FastAPI routes). Batch runner calls `step_clock_ctx` directly, not these endpoints. Auditor's line count appears slightly inflated (they claim 10+ but list 14+ lines), but the core finding is correct. |
| A8 | Log interleaving — low severity | ✅ **CONFIRMED** | Python `logging` is thread-safe. `asyncio.gather` runs on single thread (no lock contention). But 18 concurrent cases would produce interleaved log lines without `[case_id]` prefix. Low severity — debugging nuisance only. |

---

## Validator's Own Adversarial Findings

| # | Area Investigated | Finding | Severity |
|---|-------------------|---------|:--------:|
| V1 | **Import side effects in batch path** | `adapters/simulation/__init__.py` imports all singleton getters (`get_simulation_clock`, `get_historical_bar_loader`, etc.) at module level. However, these are **lazy singletons** — the `__init__.py` only imports the *functions*, it doesn't call them. First call creates the instance. **No side-effect risk.** | ✅ None |
| V2 | **Decimal vs float consistency** | `MockBroker` uses `float` internally for all prices (`_current_prices`, `_cash`, `_realized_pnl`, `MockPosition` fields). It only converts to `Decimal` at the `BrokerOrder` return boundary (L260, L386). Live Alpaca returns `Decimal` natively. This means sim-mode P&L has float rounding that live mode doesn't. **Not a concurrency issue, but a sim-vs-live fidelity gap.** | ℹ️ INFO |
| V3 | **Environment variable dependencies (os.environ)** | `grep_search` for `os.environ` in `domain/automation/` found 3 results: `trade_analysis_service.py:L189`, `ai_catalyst_validator.py:L363`, `ai_catalyst_validator.py:L584`. All are `GOOGLE_API_KEY` for AI features — **not in the batch entry/exit path.** Zero results in `adapters/simulation/`. **No concurrency risk.** | ✅ None |

---

## Standard Re-verification (S1-S5)

| # | Claim | Result | Evidence |
|---|-------|:------:|----------|
| S1 | Monitor has zero `get_engine()` calls | ✅ **PASS** | `grep_search` for `get_engine` in `warrior_monitor.py`, `warrior_monitor_exit.py`, `warrior_monitor_scale.py`, `warrior_monitor_sync.py` — all returned zero results |
| S2 | Clock calls are runtime function-level imports | ✅ **PASS** | `warrior_entry_patterns.py`: L312 (`from nexus2.adapters.simulation import get_simulation_clock` — inside function body), L547 (same), L979 (same). `warrior_vwap_utils.py`: L63 (`from nexus2.adapters.simulation.sim_clock import get_simulation_clock`), L100 (same). All inside function scope, not module-level. |
| S3 | `get_simulation_clock()` has exactly 1 definition | ✅ **PASS** | `grep_search` for `def get_simulation_clock` — 1 result at `sim_clock.py:L308` |
| S4 | No `batch_run_id` in warrior_db | ✅ **PASS** | `grep_search` for `batch_run_id` in `warrior_db.py` — zero results |
| S5 | No WAL mode configured | ✅ **PASS** | `grep_search` for `journal_mode` in `db/` — zero results. `warrior_db.py:L26-30` only has `check_same_thread=False`. |

---

## Convergence Assessment

| Metric | Value |
|--------|-------|
| Auditor's new critical issues | **0** |
| Auditor's new medium issues | **2** (A1: engine state, A6: scanner cache) |
| Auditor's new low issues | **2** (A5: trivial teardown, A8: log interleaving) |
| Validator's new issues | **0** (V2 is informational only, not a concurrency risk) |
| Combined new discovery rate | **Declining** — issues are smaller and more nuanced each round |
| All auditor claims verified | **YES** — 8/8 adversarial + 5/5 standard |

### Progress Across Rounds

| Round | Critical | Medium | Low | Validator Found New? |
|:-----:|:--------:|:------:|:---:|:---:|
| R1 | 3 | 1 | 2 | — |
| R2 | 0 | 2 | 0 | — |
| R3 | 0 | 2 | 2 | No (0 new issues) |

---

## Final Verdict

### **CONVERGED** — Architecture doc is ready for implementation with one mandatory update

The Round 3 audit found **no new critical issues**. The 2 medium issues (engine state isolation, scanner cache) are both resolved by the same fix: create a new `WarriorEngine()` per `SimContext`. This is a **doc addendum**, not a fundamental design change.

Key evidence for convergence:
1. **Diminishing returns** — R1 found 3 critical, R2 found 0, R3 found 0
2. **Validator agreement** — All 8 adversarial findings independently confirmed
3. **No validator-discovered issues** — 3 independent investigations yielded no new concurrency risks
4. **Single-fix resolution** — Both medium issues (A1 + A6) are resolved by adding engine to `SimContext.create()`

### Recommendation

**Proceed to implementation** with one mandatory pre-requisite:
- ✏️ Update architecture doc's `SimContext.create()` to include `WarriorEngine` instantiation (with own `WarriorScannerService()`)
- ✏️ Set `engine._pending_entries_file = None` in batch context (disable disk persistence)

### Overall Confidence

**HIGH** — Three rounds of audit + validation have thoroughly mapped the dependency graph. The concurrent architecture is sound; remaining issues are well-understood and have straightforward fixes.
