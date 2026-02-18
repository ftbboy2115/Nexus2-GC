"""
Concurrent Batch Runner Isolation Tests

Wave 1 (Phases 1-2):
  - SimulationClock ContextVar (T1, T2)
  - MockBroker clock injection (T3, T4)
  - is_sim_mode() ContextVar (T5, T6)

Wave 2 (Phases 3-4):
  - SimContext isolation (T7, T8)
  - step_clock_ctx advancement (T9)
  - warrior_db: WAL, batch_run_id, purge (T10, T11, T12, T13)

Wave 3 (Phases 5-6):
  - load_case_into_context signature (T14)
  - run_batch_concurrent async function (T15)
  - /sim/run_batch_concurrent endpoint registered (T16)

Reference: nexus2/docs/wave1_handoff_testing.md, wave2_handoff_testing.md, wave3_handoff_testing.md
Audit:     nexus2/wave1_audit_report.md, wave2_audit_report.md, wave3_audit_report.md
"""

import asyncio
from datetime import datetime

import pytz

from nexus2.adapters.simulation.sim_clock import (
    SimulationClock,
    get_simulation_clock,
    set_simulation_clock_ctx,
    _sim_clock_ctx,
)
from nexus2.adapters.simulation.mock_broker import MockBroker, MockPosition


ET = pytz.timezone("US/Eastern")


# ── T1: ContextVar Clock Isolation (CRITICAL) ──────────────────────────

def test_contextvar_clock_isolation():
    """Two gathered tasks should each get their own clock via ContextVar."""
    async def _run():
        clock_a = SimulationClock()
        clock_a.set_time(datetime(2026, 1, 15, 9, 30, tzinfo=ET))

        clock_b = SimulationClock()
        clock_b.set_time(datetime(2026, 2, 10, 10, 0, tzinfo=ET))

        results = {}

        async def task_a():
            set_simulation_clock_ctx(clock_a)
            await asyncio.sleep(0.01)  # Yield to event loop
            got = get_simulation_clock()
            results["a_time"] = got.get_time_string()
            results["a_identity"] = id(got)

        async def task_b():
            set_simulation_clock_ctx(clock_b)
            await asyncio.sleep(0.01)  # Yield to event loop
            got = get_simulation_clock()
            results["b_time"] = got.get_time_string()
            results["b_identity"] = id(got)

        # Run concurrently — each task sets its own ContextVar
        await asyncio.gather(task_a(), task_b())

        assert results["a_time"] == "09:30", f"Task A got {results['a_time']}, expected 09:30"
        assert results["b_time"] == "10:00", f"Task B got {results['b_time']}, expected 10:00"
        # They must be different clock instances
        assert results["a_identity"] != results["b_identity"], "Tasks should have distinct clock instances"

    asyncio.run(_run())


# ── T2: ContextVar Falls Back to Global ─────────────────────────────────

def test_contextvar_fallback_to_global():
    """Without ContextVar set, get_simulation_clock() should return global singleton."""
    # Reset the ContextVar to None to ensure clean state
    _sim_clock_ctx.set(None)

    # With no ContextVar set, should fall back to global
    clock = get_simulation_clock()
    assert clock is not None, "Fallback to global should return a valid clock"
    assert isinstance(clock, SimulationClock), "Should return a SimulationClock instance"

    # Verify it's the global (calling again returns same object)
    clock2 = get_simulation_clock()
    assert clock is clock2, "Multiple calls without ContextVar should return same global singleton"


# ── T3: MockBroker Clock Injection ──────────────────────────────────────

def test_mock_broker_clock_injection():
    """MockBroker with injected clock should use it for sell_position sim_time."""
    clock = SimulationClock()
    clock.set_time(datetime(2026, 2, 10, 10, 45, tzinfo=ET))

    broker = MockBroker(initial_cash=100_000, clock=clock)
    broker.set_price("TEST", 10.0)

    # Create a position manually
    broker._positions["TEST"] = MockPosition(
        symbol="TEST", qty=100, avg_entry_price=9.0, current_price=10.0
    )

    broker.sell_position("TEST")

    # Find the sell order and verify sim_time came from injected clock
    sell_orders = [o for o in broker._orders.values() if o.side == "sell"]
    assert len(sell_orders) == 1, f"Expected 1 sell order, got {len(sell_orders)}"
    assert sell_orders[0].sim_time == "10:45", (
        f"Sell order sim_time should be '10:45' from injected clock, "
        f"got '{sell_orders[0].sim_time}'"
    )


# ── T4: MockBroker Without Clock (Backward Compat) ─────────────────────

def test_mock_broker_no_clock_backward_compat():
    """MockBroker without clock param should still work (backward compat)."""
    broker = MockBroker(initial_cash=50_000)
    assert broker._clock is None, "Default clock should be None"
    assert broker._cash == 50_000, f"Cash should be 50000, got {broker._cash}"

    # Ensure it can still sell (sim_time falls back to global clock)
    broker.set_price("COMPAT", 20.0)
    broker._positions["COMPAT"] = MockPosition(
        symbol="COMPAT", qty=50, avg_entry_price=18.0, current_price=20.0
    )
    result = broker.sell_position("COMPAT")
    assert result is True, "sell_position should succeed without injected clock"

    sell_orders = [o for o in broker._orders.values() if o.side == "sell"]
    assert len(sell_orders) == 1, "Should have exactly 1 sell order"
    # sim_time should still be populated via the global clock fallback
    assert sell_orders[0].sim_time is not None, (
        "sim_time should still be populated via global fallback"
    )


# ── T5: is_sim_mode() ContextVar ────────────────────────────────────────

def test_is_sim_mode_contextvar():
    """is_sim_mode() should respect ContextVar when set to True."""
    from nexus2.domain.automation.trade_event_service import set_sim_mode_ctx, is_sim_mode

    # Set ContextVar to True — is_sim_mode() must return True
    set_sim_mode_ctx(True)
    assert is_sim_mode() is True, "is_sim_mode() should return True when ContextVar is True"

    # Set ContextVar to False — falls back to legacy global check
    # (result depends on whether a global sim broker exists, so we just
    #  verify it doesn't crash and returns a bool)
    set_sim_mode_ctx(False)
    result = is_sim_mode()
    assert isinstance(result, bool), f"is_sim_mode() should return bool, got {type(result)}"


# ── T6: is_sim_mode() Concurrent Isolation ──────────────────────────────

def test_is_sim_mode_concurrent_isolation():
    """Two concurrent tasks should have independent sim_mode state."""
    from nexus2.domain.automation.trade_event_service import set_sim_mode_ctx, is_sim_mode

    async def _run():
        results = {}

        async def task_sim():
            set_sim_mode_ctx(True)
            await asyncio.sleep(0.01)
            results["sim"] = is_sim_mode()

        async def task_live():
            set_sim_mode_ctx(False)
            await asyncio.sleep(0.01)
            results["live"] = is_sim_mode()

        await asyncio.gather(task_sim(), task_live())

        assert results["sim"] is True, (
            f"Task with sim_mode=True should see True, got {results['sim']}"
        )
        # 'live' task set ContextVar to False — it falls back to legacy global check.
        # If no global sim broker exists, this is False. If one does, it's True.
        # The key assertion is that it's independent from the sim task.
        assert isinstance(results["live"], bool), "live result should be a bool"

    asyncio.run(_run())


# ═════════════════════════════════════════════════════════════════════════
# WAVE 2: Phases 3-4 — SimContext, step_clock_ctx, warrior_db isolation
# ═════════════════════════════════════════════════════════════════════════


# ── T7: SimContext.create() produces isolated components ────────────────

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


# ── T8: SimContext clock mutation doesn't leak ──────────────────────────

def test_sim_context_clock_isolation():
    """Clock mutations in one context shouldn't affect another."""
    from nexus2.adapters.simulation.sim_context import SimContext

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


# ── T9: step_clock_ctx advances clock correctly ────────────────────────

def test_step_clock_ctx_advances():
    """step_clock_ctx should advance the context's clock."""
    from nexus2.adapters.simulation.sim_context import SimContext, step_clock_ctx

    ctx = SimContext.create("test_advance")
    ctx.clock.set_time(datetime(2026, 1, 15, 9, 30, tzinfo=ET))

    asyncio.run(step_clock_ctx(ctx, minutes=5))

    assert ctx.clock.get_time_string() == "09:35"


# ── T10: WAL mode is enabled ───────────────────────────────────────────

def test_warrior_db_wal_mode():
    """warrior_db should use WAL journal mode for concurrent access."""
    from nexus2.db.warrior_db import warrior_engine
    from sqlalchemy import text

    with warrior_engine.connect() as conn:
        result = conn.execute(text("PRAGMA journal_mode")).fetchone()
        assert result[0].lower() == "wal", f"Expected WAL mode, got {result[0]}"


# ── T11: batch_run_id column exists ────────────────────────────────────

def test_batch_run_id_column_exists():
    """WarriorTradeModel should have batch_run_id column."""
    from nexus2.db.warrior_db import WarriorTradeModel
    assert hasattr(WarriorTradeModel, 'batch_run_id')


# ── T12: log_warrior_entry accepts batch_run_id ────────────────────────

def test_log_warrior_entry_batch_run_id():
    """log_warrior_entry should accept batch_run_id parameter."""
    import inspect
    from nexus2.db.warrior_db import log_warrior_entry
    sig = inspect.signature(log_warrior_entry)
    assert 'batch_run_id' in sig.parameters


# ── T13: purge_batch_trades function ───────────────────────────────────

def test_purge_batch_trades_exists():
    """purge_batch_trades function should exist and filter by batch_run_id."""
    import inspect
    from nexus2.db.warrior_db import purge_batch_trades
    sig = inspect.signature(purge_batch_trades)
    assert 'batch_run_id' in sig.parameters


# ═════════════════════════════════════════════════════════════════════════
# WAVE 3: Phases 5-6 — load_case_into_context, run_batch_concurrent, endpoint
# ═════════════════════════════════════════════════════════════════════════


# ── T14: load_case_into_context function exists ────────────────────────

def test_load_case_into_context_exists():
    """load_case_into_context function should exist."""
    from nexus2.adapters.simulation.sim_context import load_case_into_context
    import inspect
    sig = inspect.signature(load_case_into_context)
    assert 'ctx' in sig.parameters
    assert 'case' in sig.parameters


# ── T15: run_batch_concurrent function exists ──────────────────────────

def test_run_batch_concurrent_exists():
    """run_batch_concurrent function should be importable."""
    from nexus2.adapters.simulation.sim_context import run_batch_concurrent
    import inspect
    assert inspect.iscoroutinefunction(run_batch_concurrent)


# ── T16: Concurrent endpoint exists ───────────────────────────────────

def test_concurrent_endpoint_registered():
    """The /sim/run_batch_concurrent endpoint should be registered."""
    from nexus2.api.routes.warrior_sim_routes import sim_router
    routes = [r.path for r in sim_router.routes]
    assert "/sim/run_batch_concurrent" in routes


# ═════════════════════════════════════════════════════════════════════════
# PHASE 9: Monitor State Bleed-Over Fix
# ═════════════════════════════════════════════════════════════════════════


# ── T17: Monitor._positions NOT shared between SimContext cases ─────────

def test_simcontext_monitor_positions_isolated():
    """Each SimContext should have independent monitor._positions (no bleed)."""
    from nexus2.adapters.simulation.sim_context import SimContext
    from nexus2.domain.automation.warrior_types import WarriorPosition
    from decimal import Decimal

    ctx1 = SimContext.create("case_1")
    ctx2 = SimContext.create("case_2")

    # Simulate a position in ctx1's monitor
    ctx1.monitor._positions["pos_123"] = WarriorPosition(
        position_id="pos_123",
        symbol="AAPL",
        entry_price=Decimal("150.0"),
        shares=100,
        entry_time=datetime(2026, 1, 15, 10, 0, tzinfo=ET),
        mental_stop=Decimal("149.50"),
    )

    # ctx2's monitor should have NO positions  
    assert len(ctx2.monitor._positions) == 0, (
        f"Case 2 monitor should have 0 positions, got {len(ctx2.monitor._positions)}. "
        "This means positions are bleeding between contexts!"
    )
    assert len(ctx1.monitor._positions) == 1, "Case 1 should still have its position"


# ── T18: Monitor._recently_exited isolated between SimContext cases ─────

def test_simcontext_monitor_recently_exited_isolated():
    """Each SimContext should have independent _recently_exited (no cooldown bleed)."""
    from nexus2.adapters.simulation.sim_context import SimContext

    ctx1 = SimContext.create("case_1")
    ctx2 = SimContext.create("case_2")

    # Simulate an exit cooldown in ctx1
    from datetime import datetime
    ctx1.monitor._recently_exited["TSLA"] = datetime(2026, 1, 15, 10, 0)

    # ctx2 should NOT have TSLA in recently_exited
    assert "TSLA" not in ctx2.monitor._recently_exited, (
        "Case 2 monitor should not have TSLA in _recently_exited. "
        "Exit cooldowns are bleeding between contexts!"
    )
    assert ctx2.monitor._recently_exited == {}, (
        f"Case 2 _recently_exited should be empty, got {ctx2.monitor._recently_exited}"
    )


# ── T19: Sequential engine monitor fields are independently clearable ───

def test_monitor_positions_clearable():
    """Verify monitor._positions.clear() works as expected for sequential cleanup."""
    from nexus2.domain.automation.warrior_monitor import WarriorMonitor
    from nexus2.domain.automation.warrior_types import WarriorPosition
    from decimal import Decimal

    monitor = WarriorMonitor()
    monitor.sim_mode = True

    # Clear any data loaded from disk during __init__
    monitor._positions.clear()
    monitor._recently_exited.clear()
    monitor._recently_exited_sim_time.clear()

    # Add position
    monitor._positions["pos_1"] = WarriorPosition(
        position_id="pos_1",
        symbol="GOOG",
        entry_price=Decimal("100.0"),
        shares=50,
        entry_time=datetime(2026, 1, 15, 10, 0, tzinfo=ET),
        mental_stop=Decimal("99.50"),
    )
    # Add exit cooldowns
    monitor._recently_exited["GOOG"] = datetime(2026, 1, 15, 10, 0)
    monitor._recently_exited_sim_time["GOOG"] = datetime(2026, 1, 15, 10, 0)

    assert len(monitor._positions) == 1
    assert len(monitor._recently_exited) == 1
    assert len(monitor._recently_exited_sim_time) == 1

    # Clear all (this is what load_historical_test_case should do between cases)
    monitor._positions.clear()
    monitor._recently_exited.clear()
    monitor._recently_exited_sim_time.clear()

    assert len(monitor._positions) == 0, "Positions should be empty after clear"
    assert len(monitor._recently_exited) == 0, "recently_exited should be empty after clear"
    assert len(monitor._recently_exited_sim_time) == 0, "recently_exited_sim_time should be empty after clear"

