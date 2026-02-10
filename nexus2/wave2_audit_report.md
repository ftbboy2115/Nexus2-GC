# Wave 2 Audit Report: Phases 3-4

**Date:** 2026-02-10
**Auditor:** Code Auditor (Claude)
**Scope:** Verify 10 claims from `wave2_handoff_auditor.md`
**Reference:** `concurrent_batch_runner_architecture.md` (v4)

---

## Results Summary

| # | Claim | Result | Evidence |
|---|-------|:------:|----------|
| C1 | SimContext dataclass exists | **PASS** | `sim_context.py` L17-27: `@dataclass class SimContext` with all 7 fields (`broker`, `clock`, `loader`, `engine`, `monitor`, `batch_id`, `case_id`). `create()` classmethod at L28-58 |
| C2 | SimContext.create() isolates all state | **PASS** | All 10 Hidden State Catalog items covered — see detailed check below |
| C3 | step_clock_ctx function exists | **PASS** | `sim_context.py` L61: `async def step_clock_ctx(ctx: SimContext, minutes: int)`. Uses only `ctx.*` members, no global singletons |
| C4 | step_clock_ctx handles 10s stepping | **PASS** | L73-75: `has_10s_bars` check. L87: `step_forward(minutes=0, seconds=10)`. L90: `step_forward(minutes=1)` |
| C5 | step_clock_ctx entry + monitor checks | **PASS** | L113: `check_entry_triggers(ctx.engine)`. L131: `ctx.monitor._check_all_positions()`. L122: `_broker=ctx.broker` default arg prevents closure capture bug |
| C6 | SimContext exported from simulation package | **PASS** | `__init__.py` L32: `from nexus2.adapters.simulation.sim_context import SimContext, step_clock_ctx`. L50-51: both in `__all__` |
| C7 | WAL mode enabled | **PASS** | `warrior_db.py` L33-38: `@event.listens_for(warrior_engine, "connect")` runs `PRAGMA journal_mode=WAL` |
| C8 | batch_run_id column exists | **PASS** | Model L101: `batch_run_id = Column(String(36), nullable=True, index=True)`. Migration L248-253: ALTER TABLE. `log_warrior_entry()` L282: accepts `batch_run_id` param, L309: passes to model |
| C9 | purge_batch_trades function exists | **PASS** | `warrior_db.py` L794: `def purge_batch_trades(batch_run_id: str) -> int`. L811-812: filters by `batch_run_id`. `purge_sim_trades()` unmodified at L750-791 |
| C10 | No unintended changes | **PASS** | `git diff --stat HEAD~1` shows only 4 files: `sim_context.py` (NEW), `__init__.py`, `warrior_db.py`, `wave1_audit_report.md` (cosmetic). No red-flag files touched |

---

## C2 Detailed: Hidden State Catalog Cross-Reference

Each of the 10 items from the architecture doc (L55-68) checked against `SimContext.create()` (L29-58):

| # | State Item | Owner | Code Location | Status |
|---|-----------|-------|---------------|:------:|
| 1 | `_recently_exited` dict | Monitor | L39: `monitor._recently_exited = {}` | ✅ |
| 2 | `_recently_exited_sim_time` dict | Monitor | L40: `monitor._recently_exited_sim_time = {}` | ✅ |
| 3 | `recently_exited.json` file | Monitor | L38: `monitor._recently_exited_file = None` | ✅ |
| 4 | `_watchlist` dict | Engine | L43-47: new `WarriorEngine()` (clean init) | ✅ |
| 5 | `_blacklist` set | Engine | L43-47: new `WarriorEngine()` (clean init) | ✅ |
| 6 | `_pending_entries` dict | Engine | L43-47: new `WarriorEngine()` (clean init) | ✅ |
| 7 | `_symbol_fails` dict | Engine | L43-47: new `WarriorEngine()` (clean init) | ✅ |
| 8 | `stats._seen_candidates` set | Engine | L43-47: new `WarriorEngine()` (clean init) | ✅ |
| 9 | `pending_entries.json` file | Engine | L48: `engine._pending_entries_file = None` | ✅ |
| 10 | `_cache` dict | Scanner | L45: `scanner=WarriorScannerService()` (new instance) | ✅ |

---

## C5 Detailed: Closure Safety

The closure default arg at L122 is critical:

```python
async def sim_get_prices_batch(symbols, _broker=ctx.broker):
```

This captures `ctx.broker` at function definition time via default argument, which prevents the classic Python closure variable capture bug where a late-binding closure would reference the last value of `ctx.broker` if multiple closures were created. **Correctly implemented.**

---

## C10 Detailed: Git Diff Analysis

```
 nexus2/adapters/simulation/__init__.py    |   4 +
 nexus2/adapters/simulation/sim_context.py | 133 +++++++++++++
 nexus2/db/warrior_db.py                   |  49 ++++-
 nexus2/wave1_audit_report.md              | 311 +++++++++++++-----------------
 4 files changed, 317 insertions(+), 180 deletions(-)
```

- `sim_context.py` — NEW file (expected)
- `__init__.py` — 4 lines added (expected: import + `__all__` entries)
- `warrior_db.py` — 49 lines added (expected: WAL listener, column, migration, purge function)
- `wave1_audit_report.md` — Cosmetic reformatting only, not a code file. **No concern.**

**No red-flag files touched:** `warrior_sim_routes.py`, `warrior_engine.py`, `warrior_monitor.py`, `sim_clock.py`, `mock_broker.py` are all untouched.

---

## Minor Notes (Non-Blocking)

1. **`create()` signature difference from architecture doc:** Implementation adds `batch_id: Optional[str] = None` parameter (arch doc has no param). This is a minor enhancement — allows caller to specify a batch ID rather than always auto-generating. **Not a defect.**

2. **`step_clock_ctx` is more detailed than arch doc spec:** The implementation includes engine state checking (L104-111), error handling (L114-115, L132-133), and conditional monitor callback setup (L121-129). The arch doc's Phase 3 pseudo-code was a simplified sketch. **The implementation is a superset, not a deviation.**

---

## Verdict

**ALL 10 CLAIMS PASS.** Ready for testing specialist.
