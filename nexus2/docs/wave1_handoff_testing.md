# Wave 1 Testing Specialist Handoff: Phases 1-2 Tests

> **Run AFTER:** Code auditor confirms all 8 claims PASS
> **Architecture Doc:** [concurrent_batch_runner_architecture.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/docs/concurrent_batch_runner_architecture.md)
> **Audit Report:** `nexus2/wave1_audit_report.md`

> [!WARNING]
> **Grep may fail due to CRLF encoding.** If `grep_search` returns 0 results for a pattern you know exists, fall back to `view_file_outline` or `view_file` to verify. Do not assume code is missing just because grep didn't find it.

---

## What Was Changed (Phase 1-2 Summary)

1. `get_simulation_clock()` now checks a ContextVar before the global singleton
2. `MockBroker.__init__` accepts an optional `clock` parameter
3. `MockBroker.sell_position()` uses injected clock if available
4. `trade_event_service.py` has `is_sim_mode()` ContextVar replacing 5 `get_warrior_sim_broker()` checks
5. No changes to monitor, engine __init__, or entry logic

---

## Tests to Write

Create test file: `nexus2/tests/test_concurrent_isolation.py`

### T1: ContextVar Clock Isolation (CRITICAL)

Test that two concurrent asyncio tasks each get their own clock:

```python
import asyncio
from contextvars import copy_context
from nexus2.adapters.simulation.sim_clock import (
    SimulationClock, get_simulation_clock, set_simulation_clock_ctx
)

async def test_contextvar_clock_isolation():
    """Two gathered tasks should each get their own clock."""
    clock_a = SimulationClock()
    clock_a.set_time(datetime(2026, 1, 15, 9, 30, tzinfo=ET))
    
    clock_b = SimulationClock()
    clock_b.set_time(datetime(2026, 2, 10, 10, 0, tzinfo=ET))
    
    results = {}
    
    async def task_a():
        set_simulation_clock_ctx(clock_a)
        await asyncio.sleep(0.01)  # Yield to event loop
        got = get_simulation_clock()
        results['a_time'] = got.get_time_string()
    
    async def task_b():
        set_simulation_clock_ctx(clock_b)
        await asyncio.sleep(0.01)
        got = get_simulation_clock()
        results['b_time'] = got.get_time_string()
    
    await asyncio.gather(task_a(), task_b())
    
    assert results['a_time'] == "09:30", f"Task A got {results['a_time']}"
    assert results['b_time'] == "10:00", f"Task B got {results['b_time']}"
```

### T2: ContextVar Falls Back to Global

Test that when no ContextVar is set, `get_simulation_clock()` returns the global singleton:

```python
async def test_contextvar_fallback_to_global():
    """Without ContextVar set, should return global singleton."""
    from nexus2.adapters.simulation.sim_clock import _sim_clock_ctx
    assert _sim_clock_ctx.get() is None  # No context set
    clock = get_simulation_clock()
    assert clock is not None  # Should return global
```

### T3: MockBroker Clock Injection

Test that `sell_position()` uses the injected clock for sim_time:

```python
def test_mock_broker_clock_injection():
    """MockBroker with injected clock should use it for sell orders."""
    clock = SimulationClock()
    clock.set_time(datetime(2026, 2, 10, 10, 45, tzinfo=ET))
    
    broker = MockBroker(initial_cash=100_000, clock=clock)
    broker.set_price("TEST", 10.0)
    
    # Create a position manually
    broker._positions["TEST"] = MockPosition(
        symbol="TEST", qty=100, avg_entry_price=9.0, current_price=10.0
    )
    
    broker.sell_position("TEST")
    
    # Check that sell order has correct sim_time from injected clock
    sell_orders = [o for o in broker._orders.values() if o.side == "sell"]
    assert len(sell_orders) == 1
    assert sell_orders[0].sim_time == "10:45"
```

### T4: MockBroker Without Clock (Backward Compat)

```python
def test_mock_broker_no_clock_backward_compat():
    """MockBroker without clock param should still work."""
    broker = MockBroker(initial_cash=50_000)
    assert broker._clock is None
    assert broker._cash == 50_000
```

### T5: is_sim_mode() ContextVar

```python
async def test_is_sim_mode_contextvar():
    """is_sim_mode() should respect ContextVar when set."""
    from nexus2.domain.automation.trade_event_service import set_sim_mode_ctx, is_sim_mode
    
    # Default should be False (no sim broker set, no ContextVar)
    # Note: may be True if global sim broker exists — that's fine
    
    set_sim_mode_ctx(True)
    assert is_sim_mode() == True
    
    set_sim_mode_ctx(False)
    # Should fall back to global check
```

### T6: is_sim_mode() Concurrent Isolation

```python
async def test_is_sim_mode_concurrent_isolation():
    """Two tasks should have independent sim_mode state."""
    from nexus2.domain.automation.trade_event_service import set_sim_mode_ctx, is_sim_mode
    
    results = {}
    
    async def task_sim():
        set_sim_mode_ctx(True)
        await asyncio.sleep(0.01)
        results['sim'] = is_sim_mode()
    
    async def task_live():
        set_sim_mode_ctx(False)
        await asyncio.sleep(0.01)
        results['live'] = is_sim_mode()
    
    await asyncio.gather(task_sim(), task_live())
    
    assert results['sim'] == True
    # 'live' may be True if global sim broker exists — test logic accordingly
```

---

## Regression Tests

Run existing test suite to verify no breakage:

```powershell
cd nexus2
python -m pytest tests/ -x -v --timeout=30
```

If any existing tests fail, document in the report and check if it's related to the Phase 1-2 changes.

---

## Output Format

Write report to: `nexus2/wave1_test_report.md`

```markdown
# Wave 1 Test Report: Phases 1-2

## New Tests
| # | Test | Result |
|---|------|:------:|
| T1 | ContextVar clock isolation | PASS/FAIL |
| T2 | ContextVar fallback to global | PASS/FAIL |
| T3 | MockBroker clock injection | PASS/FAIL |
| T4 | MockBroker backward compat | PASS/FAIL |
| T5 | is_sim_mode() ContextVar | PASS/FAIL |
| T6 | is_sim_mode() concurrent isolation | PASS/FAIL |

## Regression Tests
- Total: X tests
- Passed: X
- Failed: X (list any failures)

## Verdict
- ALL PASS: Wave 1 complete, ready for Wave 2
- ANY FAIL: [describe failure and impact]
```
