# Wave 2 Testing Specialist Handoff: Phases 3-4 Tests

> **Run AFTER:** Code auditor confirms all 10 claims PASS
> **Architecture Doc:** [concurrent_batch_runner_architecture.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/docs/concurrent_batch_runner_architecture.md)
> **Audit Report:** `nexus2/wave2_audit_report.md`

> [!WARNING]
> **Grep may fail due to CRLF encoding.** If `grep_search` returns 0 results for a pattern you know exists, fall back to `view_file_outline` or `view_file` to verify.

---

## What Was Changed (Phase 3-4 Summary)

1. **[NEW]** `sim_context.py` — `SimContext` dataclass + `step_clock_ctx()` function
2. `warrior_db.py` — WAL mode, `batch_run_id` column + migration, `purge_batch_trades()`, `log_warrior_entry()` param
3. `simulation/__init__.py` — new exports

---

## Tests to Write

Add to `nexus2/tests/test_concurrent_isolation.py` (created in Wave 1).

### T7: SimContext.create() produces isolated components

```python
def test_sim_context_creates_isolated_components():
    """SimContext.create() should produce fully isolated components."""
    from nexus2.adapters.simulation.sim_context import SimContext
    
    ctx1 = SimContext.create("case_1")
    ctx2 = SimContext.create("case_2")
    
    # Different instances
    assert ctx1.clock is not ctx2.clock
    assert ctx1.broker is not ctx2.broker
    assert ctx1.loader is not ctx2.loader
    assert ctx1.engine is not ctx2.engine
    assert ctx1.monitor is not ctx2.monitor
    
    # Correct wiring
    assert ctx1.broker._clock is ctx1.clock
    assert ctx1.engine.monitor is ctx1.monitor
    assert ctx1.monitor.sim_mode is True
    assert ctx1.engine._pending_entries_file is None
    assert ctx1.monitor._recently_exited == {}
    assert ctx1.monitor._recently_exited_file is None
```

### T8: SimContext clock mutation doesn't leak

```python
def test_sim_context_clock_isolation():
    """Clock mutations in one context shouldn't affect another."""
    from nexus2.adapters.simulation.sim_context import SimContext
    from datetime import datetime
    import pytz
    ET = pytz.timezone("US/Eastern")
    
    ctx1 = SimContext.create("case_1")
    ctx2 = SimContext.create("case_2")
    
    ctx1.clock.set_time(datetime(2026, 1, 15, 9, 30, tzinfo=ET))
    ctx2.clock.set_time(datetime(2026, 2, 10, 10, 0, tzinfo=ET))
    
    assert ctx1.clock.get_time_string() == "09:30"
    assert ctx2.clock.get_time_string() == "10:00"
    
    # Advance ctx1, ctx2 should remain unchanged
    ctx1.clock.step_forward(minutes=5)
    assert ctx1.clock.get_time_string() == "09:35"
    assert ctx2.clock.get_time_string() == "10:00"
```

### T9: step_clock_ctx advances clock correctly

```python
def test_step_clock_ctx_advances():
    """step_clock_ctx should advance the context's clock."""
    import asyncio
    from nexus2.adapters.simulation.sim_context import SimContext, step_clock_ctx
    from datetime import datetime
    import pytz
    ET = pytz.timezone("US/Eastern")
    
    ctx = SimContext.create("test_advance")
    ctx.clock.set_time(datetime(2026, 1, 15, 9, 30, tzinfo=ET))
    
    asyncio.run(step_clock_ctx(ctx, minutes=5))
    
    assert ctx.clock.get_time_string() == "09:35"
```

### T10: WAL mode is enabled

```python
def test_warrior_db_wal_mode():
    """warrior_db should use WAL journal mode for concurrent access."""
    from nexus2.db.warrior_db import warrior_engine
    
    with warrior_engine.connect() as conn:
        from sqlalchemy import text
        result = conn.execute(text("PRAGMA journal_mode")).fetchone()
        assert result[0].lower() == "wal", f"Expected WAL mode, got {result[0]}"
```

### T11: batch_run_id column exists

```python
def test_batch_run_id_column_exists():
    """WarriorTradeModel should have batch_run_id column."""
    from nexus2.db.warrior_db import WarriorTradeModel
    assert hasattr(WarriorTradeModel, 'batch_run_id')
```

### T12: log_warrior_entry accepts batch_run_id

```python
def test_log_warrior_entry_batch_run_id():
    """log_warrior_entry should accept batch_run_id parameter."""
    import inspect
    from nexus2.db.warrior_db import log_warrior_entry
    sig = inspect.signature(log_warrior_entry)
    assert 'batch_run_id' in sig.parameters
```

### T13: purge_batch_trades function

```python
def test_purge_batch_trades_exists():
    """purge_batch_trades function should exist and filter by batch_run_id."""
    import inspect
    from nexus2.db.warrior_db import purge_batch_trades
    sig = inspect.signature(purge_batch_trades)
    assert 'batch_run_id' in sig.parameters
```

---

## Regression Tests

Run existing test suite + Wave 1 tests:

```powershell
cd nexus2
python -m pytest tests/test_concurrent_isolation.py -x -v --timeout=30
python -m pytest tests/ -x -v --timeout=30
```

---

## Output Format

Write report to: `nexus2/wave2_test_report.md`

```markdown
# Wave 2 Test Report: Phases 3-4

## New Tests
| # | Test | Result |
|---|------|:------:|
| T7 | SimContext isolated components | PASS/FAIL |
| T8 | SimContext clock isolation | PASS/FAIL |
| T9 | step_clock_ctx advances clock | PASS/FAIL |
| T10 | WAL mode enabled | PASS/FAIL |
| T11 | batch_run_id column exists | PASS/FAIL |
| T12 | log_warrior_entry accepts batch_run_id | PASS/FAIL |
| T13 | purge_batch_trades exists | PASS/FAIL |

## Wave 1 Tests (Regression)
| # | Test | Result |
|---|------|:------:|
| T1-T6 | All Wave 1 tests | PASS/FAIL |

## Verdict
- ALL PASS: Wave 2 complete, ready for Wave 3
- ANY FAIL: [describe failure and impact]
```
