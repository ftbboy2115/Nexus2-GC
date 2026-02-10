# Wave 2 Code Auditor Handoff: Verify Phases 3-4

> **Run AFTER:** Backend specialist completes Phases 3-4
> **Architecture Doc:** [concurrent_batch_runner_architecture.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/docs/concurrent_batch_runner_architecture.md)
> **Mode:** READ-ONLY verification. Do NOT modify any code.

> [!WARNING]
> **Grep may fail due to CRLF encoding.** If `grep_search` returns 0 results for a pattern you know exists, fall back to `view_file_outline` or `view_file` to verify.

---

## Claims to Verify (10 total)

### C1: SimContext dataclass exists
- **File:** `nexus2/adapters/simulation/sim_context.py` (NEW file)
- **Check:** `@dataclass` class `SimContext` with fields: `broker`, `clock`, `loader`, `engine`, `monitor`, `batch_id`, `case_id`
- **Check:** `create()` classmethod exists

### C2: SimContext.create() isolates all state
- **File:** `nexus2/adapters/simulation/sim_context.py`
- **Check against Hidden State Catalog** (architecture doc L55-68):
  - Creates new `SimulationClock()`
  - Creates `MockBroker(clock=clock)` (injected clock)
  - Creates new `WarriorMonitor()` with `sim_mode=True`, `_recently_exited_file=None`, `_recently_exited={}`, `_recently_exited_sim_time={}`
  - Creates `WarriorEngine(config=WarriorEngineConfig(sim_only=True), scanner=WarriorScannerService(), monitor=monitor)`
  - Sets `engine._pending_entries_file = None`
  - Creates new `HistoricalBarLoader()`
- **Red flag:** Missing any of the 10 catalog items from architecture doc

### C3: step_clock_ctx function exists
- **File:** `nexus2/adapters/simulation/sim_context.py`
- **Check:** `async def step_clock_ctx(ctx: SimContext, minutes: int)` signature
- **Check:** Uses `ctx.clock`, `ctx.broker`, `ctx.loader`, `ctx.engine`, `ctx.monitor` — NOT any global singletons

### C4: step_clock_ctx handles 10s stepping
- **File:** `nexus2/adapters/simulation/sim_context.py`
- **Check:** Contains `has_10s_bars` check logic mirroring `warrior_sim_routes.py` L1119-1134
- **Check:** Both `step_forward(minutes=0, seconds=10)` and `step_forward(minutes=1)` paths exist

### C5: step_clock_ctx entry + monitor checks
- **Check:** Calls `check_entry_triggers(ctx.engine)` (not global engine)
- **Check:** Calls `ctx.monitor._check_all_positions()` 
- **Check:** Sets up `sim_get_prices_batch` callback using `ctx.broker`
- **Critical:** The closure default arg `_broker=ctx.broker` prevents closure variable capture bug

### C6: SimContext exported from simulation package
- **File:** `nexus2/adapters/simulation/__init__.py`
- **Check:** `SimContext` and `step_clock_ctx` in imports and `__all__`

### C7: WAL mode enabled
- **File:** `nexus2/db/warrior_db.py`
- **Check:** SQLAlchemy event listener on `"connect"` that runs `PRAGMA journal_mode=WAL`
- **Check:** Listener is attached to `warrior_engine` (the SQLAlchemy engine, not WarriorEngine)

### C8: batch_run_id column exists
- **File:** `nexus2/db/warrior_db.py`
- **Check:** `batch_run_id = Column(String(36), ...)` in `WarriorTradeModel`
- **Check:** Migration in `init_warrior_db()` that ALTERs table to add column
- **Check:** `log_warrior_entry()` accepts `batch_run_id` parameter

### C9: purge_batch_trades function exists
- **File:** `nexus2/db/warrior_db.py`
- **Check:** `def purge_batch_trades(batch_run_id: str)` exists
- **Check:** Filters by `batch_run_id` (not `is_sim`)
- **Check:** Does NOT modify existing `purge_sim_trades()`

### C10: No unintended changes
- **Run:** `git diff --stat`
- **Expected modified/new files:**
  - `adapters/simulation/sim_context.py` (NEW)
  - `adapters/simulation/__init__.py`
  - `db/warrior_db.py`
- **Red flag:** Changes to `warrior_sim_routes.py`, `warrior_engine.py`, `warrior_monitor.py`, `sim_clock.py`, `mock_broker.py`

---

## Output Format

Write report to: `nexus2/wave2_audit_report.md`

```markdown
# Wave 2 Audit Report: Phases 3-4

| # | Claim | Result | Evidence |
|---|-------|:------:|----------|
| C1-C10 | ... | PASS/FAIL | [details] |

## Verdict
- ALL PASS: Ready for testing specialist
- ANY FAIL: Return to backend specialist with specific failures
```
