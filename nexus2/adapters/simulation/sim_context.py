"""
SimContext: Fully isolated simulation environment for one test case.
Used by the concurrent batch runner to prevent cross-case state leakage.
"""
from dataclasses import dataclass
from uuid import uuid4
from typing import Optional

from nexus2.adapters.simulation.sim_clock import SimulationClock
from nexus2.adapters.simulation.mock_broker import MockBroker
from nexus2.adapters.simulation.historical_bar_loader import HistoricalBarLoader
from nexus2.domain.automation.warrior_engine import WarriorEngine, WarriorEngineConfig
from nexus2.domain.scanner.warrior_scanner_service import WarriorScannerService
from nexus2.domain.automation.warrior_monitor import WarriorMonitor


@dataclass
class SimContext:
    """Fully isolated simulation environment for one test case."""
    broker: MockBroker
    clock: SimulationClock
    loader: HistoricalBarLoader
    engine: WarriorEngine
    monitor: WarriorMonitor
    batch_id: str
    case_id: str
    
    @classmethod
    def create(cls, case_id: str, batch_id: Optional[str] = None) -> "SimContext":
        clock = SimulationClock()
        
        # MockBroker with injected clock (Wave 1 Phase 1B)
        broker = MockBroker(initial_cash=100_000, clock=clock)
        
        # Monitor with clean state (R2 fix)
        monitor = WarriorMonitor()
        monitor.sim_mode = True
        monitor._recently_exited_file = None
        monitor._recently_exited = {}
        monitor._recently_exited_sim_time = {}
        
        # Engine + Scanner per context (R3 fix)
        engine = WarriorEngine(
            config=WarriorEngineConfig(sim_only=True),
            scanner=WarriorScannerService(),
            monitor=monitor,
        )
        engine._pending_entries_file = None  # Disable disk persistence
        
        return cls(
            broker=broker,
            clock=clock,
            loader=HistoricalBarLoader(),
            engine=engine,
            monitor=monitor,
            batch_id=batch_id or str(uuid4()),
            case_id=case_id,
        )


async def step_clock_ctx(ctx: SimContext, minutes: int):
    """
    Step a SimContext's clock forward, processing entries/exits each step.
    
    This is the concurrent-safe version of warrior_sim_routes.step_clock().
    Always headless — no chart data generation.
    """
    from nexus2.domain.automation.warrior_engine_entry import check_entry_triggers
    import logging
    log = logging.getLogger(__name__)
    
    # Determine step granularity (same logic as step_clock L1119-1134)
    use_10s_stepping = any(
        ctx.loader.has_10s_bars(sym) for sym in ctx.loader.get_loaded_symbols()
    )
    
    if use_10s_stepping:
        total_steps = minutes * 6
        step_seconds = 10
    else:
        total_steps = minutes
        step_seconds = 0
    
    for step_idx in range(total_steps):
        # Step forward
        if use_10s_stepping:
            ctx.clock.step_forward(minutes=0, seconds=step_seconds)
            time_str = ctx.clock.get_time_string_with_seconds()
        else:
            ctx.clock.step_forward(minutes=1)
            time_str = ctx.clock.get_time_string()
        
        # Update prices for all loaded symbols
        for symbol in ctx.loader.get_loaded_symbols():
            if use_10s_stepping and ctx.loader.has_10s_bars(symbol):
                price = ctx.loader.get_10s_price_at(symbol, time_str)
            else:
                price = ctx.loader.get_price_at(symbol, ctx.clock.get_time_string())
            
            if price:
                ctx.broker.set_price(symbol, price)
        
        # Check engine state
        engine_state_str = (
            ctx.engine.state.value 
            if hasattr(ctx.engine.state, 'value') 
            else str(ctx.engine.state)
        )
        
        # Trigger entry check if engine is running
        if engine_state_str in ("running", "premarket"):
            try:
                await check_entry_triggers(ctx.engine)
            except Exception as e:
                log.warning(f"[{ctx.case_id}] Entry check error at {time_str}: {e}")
        
        # Check positions for exits (monitor tick)
        if ctx.monitor._positions:
            try:
                # Ensure batch price callback is available
                if not ctx.monitor._get_prices_batch:
                    async def sim_get_prices_batch(symbols, _broker=ctx.broker):
                        result = {}
                        for s in symbols:
                            price = _broker.get_price(s)
                            if price:
                                result[s] = price
                        return result
                    ctx.monitor._get_prices_batch = sim_get_prices_batch
                
                await ctx.monitor._check_all_positions()
            except Exception as e:
                log.error(f"[{ctx.case_id}] Monitor check error at {time_str}: {e}")
