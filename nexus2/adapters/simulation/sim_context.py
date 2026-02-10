"""
SimContext: Fully isolated simulation environment for one test case.
Used by the concurrent batch runner to prevent cross-case state leakage.
"""
from dataclasses import dataclass
from uuid import uuid4
from typing import Optional
import logging

from nexus2.adapters.simulation.sim_clock import SimulationClock
from nexus2.adapters.simulation.mock_broker import MockBroker
from nexus2.adapters.simulation.historical_bar_loader import HistoricalBarLoader
from nexus2.domain.automation.warrior_engine import WarriorEngine, WarriorEngineConfig
from nexus2.domain.automation.warrior_engine_types import WarriorEngineState
from nexus2.domain.scanner.warrior_scanner_service import WarriorScannerService
from nexus2.domain.automation.warrior_monitor import WarriorMonitor

log = logging.getLogger(__name__)


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


def load_case_into_context(ctx: SimContext, case: dict, yaml_data: dict) -> int:
    """
    Load a test case into a SimContext.

    Replicates load_historical_test_case() from warrior_sim_routes.py
    but uses ctx.loader, ctx.clock, ctx.broker, ctx.engine instead of globals.

    CRITICAL: All callback closures capture ctx.broker/ctx.loader/ctx.clock via
    default args to prevent cross-context leakage during concurrent execution.

    Args:
        ctx: The SimContext to load into
        case: Test case dict from YAML (has 'id', 'symbol', 'ross_pnl', etc.)
        yaml_data: Full YAML data dict (for looking up case by ID)

    Returns:
        Number of bars loaded
    """
    from datetime import datetime
    from decimal import Decimal
    import os
    import pytz

    from nexus2.domain.automation.warrior_engine import WatchedCandidate
    from nexus2.domain.scanner.warrior_scanner_service import WarriorCandidate

    ET = pytz.timezone("US/Eastern")
    case_id = case.get("id")

    # ── Step 1: Load bar data into ctx.loader ────────────────────────────
    ctx.loader.reset()
    data = ctx.loader.load_test_case(case_id)

    if data is None:
        log.warning(f"[{case_id}] Test case not found in loader")
        return 0

    # ── Step 2: Set clock to first bar's time ────────────────────────────
    trade_date = datetime.strptime(data.date, "%Y-%m-%d")

    if data.bars:
        first_bar_time = data.bars[0].time  # e.g. "07:56"
        hour, minute = map(int, first_bar_time.split(":"))
        start_time = ET.localize(trade_date.replace(hour=hour, minute=minute, second=0))
    else:
        start_time = ET.localize(trade_date.replace(hour=9, minute=30, second=0))

    ctx.clock.set_time(start_time)

    # ── Step 3: Set initial price on broker ──────────────────────────────
    symbol = data.symbol
    entry_price = data.bars[0].open if data.bars else 10.0
    ctx.broker.reset()
    ctx.broker.set_price(symbol, entry_price)

    # ── Step 4: Load mock market data (daily bars for VWAP/EMA) ──────────
    from nexus2.adapters.simulation.mock_market_data import MockMarketData

    mock_data = MockMarketData()
    mock_data.set_clock(ctx.clock)

    if data.bars:
        date_str = data.date
        daily_bars = [{
            "date": date_str,
            "open": float(data.bars[0].open),
            "high": max(b.high for b in data.bars),
            "low": min(b.low for b in data.bars),
            "close": float(data.bars[-1].close),
            "volume": sum(b.volume for b in data.bars),
        }]
        mock_data.load_data(symbol, daily_bars)

    # ── Step 5: Create WatchedCandidate + add to engine watchlist ────────
    premarket = data.premarket
    gap_pct = premarket.get("gap_percent", 25.0)
    pmh = Decimal(str(premarket.get("pmh", entry_price)))
    prev_close = premarket.get("previous_close", entry_price * 0.8)

    # Catalyst date for freshness scoring
    catalyst_date_str = premarket.get("catalyst_date")
    if catalyst_date_str:
        try:
            catalyst_date = ET.localize(datetime.strptime(catalyst_date_str, "%Y-%m-%d %H:%M"))
        except ValueError:
            catalyst_date = ET.localize(datetime.strptime(catalyst_date_str, "%Y-%m-%d").replace(hour=9, minute=30))
    else:
        catalyst_date = ET.localize(trade_date.replace(hour=9, minute=30, second=0))

    candidate = WarriorCandidate(
        symbol=symbol,
        name=symbol,
        price=Decimal(str(entry_price)),
        gap_percent=Decimal(str(gap_pct)),
        relative_volume=Decimal("10.0"),
        float_shares=premarket.get("float_shares"),
        catalyst_type=premarket.get("catalyst", "news"),
        catalyst_description=premarket.get("catalyst_description", f"Batch replay: {case_id}"),
        catalyst_date=catalyst_date,
        is_ideal_float=True,
        is_ideal_rvol=True,
        is_ideal_gap=True,
        session_high=pmh,
        session_low=Decimal(str(prev_close)),
    )

    watched = WatchedCandidate(
        candidate=candidate,
        pmh=pmh,
        setup_type=data.setup_type,
        ross_entry=Decimal(str(data.ross_entry)) if data.ross_entry else None,
        ross_pnl=Decimal(str(data.ross_pnl)) if data.ross_pnl else None,
    )

    # Fresh start: clear state
    ctx.engine._watchlist.clear()
    ctx.engine._pending_entries.clear()
    ctx.engine._symbol_fails.clear()
    watched.entry_triggered = False
    ctx.engine._watchlist[symbol] = watched

    # ── Step 6: Wire all 11 callbacks ────────────────────────────────────
    # CRITICAL: Every closure captures ctx components via default args
    # to prevent cross-context leakage during concurrent execution.

    # -- Monitor state setup (L839-841) --
    ctx.engine.monitor.sim_mode = True
    ctx.engine.monitor._sim_clock = ctx.clock
    ctx.engine.monitor._recently_exited_sim_time.clear()

    # -- Callback 1: get_price (L843) --
    async def sim_get_price(symbol: str, _broker=ctx.broker):
        price = _broker.get_price(symbol)
        return price if price is not None else None

    # -- Callback 2: get_prices_batch (L851) --
    async def sim_get_prices_batch(symbols, _broker=ctx.broker):
        result = {}
        for s in symbols:
            price = _broker.get_price(s)
            if price:
                result[s] = price
        return result

    # -- Callback 3: execute_exit (L861) --
    async def sim_execute_exit(signal, _broker=ctx.broker):
        if _broker is None:
            return False

        from nexus2.domain.automation.warrior_types import WarriorExitReason
        is_partial = signal.reason == WarriorExitReason.PARTIAL_EXIT

        if is_partial:
            shares_to_sell = signal.shares_to_exit
        else:
            # FULL EXIT: sell ALL broker shares
            positions = _broker.get_positions()
            broker_position = next(
                (p for p in positions if p.get("symbol") == signal.symbol), None
            )
            if broker_position:
                broker_shares = broker_position.get("qty", 0) or broker_position.get("shares", 0)
                shares_to_sell = broker_shares if broker_shares > 0 else signal.shares_to_exit
            else:
                shares_to_sell = signal.shares_to_exit

        success = _broker.sell_position(signal.symbol, shares_to_sell)
        if success:
            log.info(f"[{case_id}] EXIT: {signal.symbol} x{shares_to_sell} @ ${signal.exit_price}")
        return success

    # -- Callback 4: update_stop (L895) --
    async def sim_update_stop(position_id: str, new_stop_price, _broker=ctx.broker, _monitor=ctx.monitor):
        if _broker is None:
            return False
        symbol = None
        for pos in _monitor.get_positions():
            if pos.position_id == position_id:
                symbol = pos.symbol
                break
        if not symbol:
            return False
        success = _broker.update_stop(symbol, float(new_stop_price))
        if success:
            log.info(f"[{case_id}] Updated stop: {symbol} -> ${new_stop_price:.2f}")
        return success

    # -- Callback 5: get_intraday_candles (L920) --
    async def sim_get_intraday_bars(symbol: str, timeframe: str = "1min", limit: int = 50,
                                     _loader=ctx.loader, _clock=ctx.clock):
        """Return historical bars up to current simulated time.

        Excludes current minute's bar to avoid future data leakage.
        """
        time_with_seconds = _clock.get_time_string_with_seconds()
        time_str = _clock.get_time_string()

        seconds = int(time_with_seconds.split(":")[-1]) if ":" in time_with_seconds else 0
        if seconds > 0:
            hour, minute = int(time_str.split(":")[0]), int(time_str.split(":")[1])
            if minute > 0:
                minute -= 1
            else:
                hour -= 1
                minute = 59
            time_str = f"{hour:02d}:{minute:02d}"

        bars = _loader.get_bars_up_to(symbol, time_str, timeframe, include_continuity=True)

        if bars and len(bars) > limit + 100:
            bars = bars[-(limit + 50):]
        return bars

    # -- set_callbacks (L960-967): wires callbacks 1,2,3,4,5 + callback 6 --
    ctx.engine.monitor.set_callbacks(
        get_price=sim_get_price,
        get_prices_batch=sim_get_prices_batch,
        execute_exit=sim_execute_exit,
        update_stop=sim_update_stop,
        get_intraday_candles=sim_get_intraday_bars,
        get_quote_with_spread=sim_get_price,  # Callback 6: same as get_price in sim
    )

    # -- Callbacks cleared (L971-973) --
    ctx.engine.monitor._get_broker_positions = None  # Callback 7: prevent Alpaca calls
    ctx.engine.monitor._submit_scale_order = None    # Callback 8: set to sim_submit_order below
    ctx.engine.monitor._get_order_status = None      # Callback 9: MockBroker fills instantly

    # -- Callback 10: engine._get_intraday_bars (L975) --
    ctx.engine._get_intraday_bars = sim_get_intraday_bars

    # -- Callback 11: engine._get_quote (L1002) --
    async def sim_get_quote_historical(symbol: str, _loader=ctx.loader, _clock=ctx.clock, _broker=ctx.broker):
        """Return price from historical bar loader at current simulated time."""
        if _loader.has_10s_bars(symbol):
            time_str = _clock.get_time_string_with_seconds()
            price = _loader.get_10s_price_at(symbol, time_str)
            if price:
                return price

        time_str = _clock.get_time_string()
        price = _loader.get_price_at(symbol, time_str)
        if price:
            return price

        return _broker.get_price(symbol)

    ctx.engine._get_quote = sim_get_quote_historical

    # -- Callback 12: engine._submit_order (L1042) --
    async def sim_submit_order_historical(
        symbol: str, shares: int, side: str = "buy", order_type: str = "market",
        stop_loss: float = None, limit_price: float = None, trigger_type: str = "orb",
        exit_mode: str = None, entry_trigger: str = None,
        _broker=ctx.broker, _clock=ctx.clock, **kwargs
    ):
        """Submit order through MockBroker for historical replay."""
        if _broker is None:
            return None

        from decimal import Decimal as D
        from uuid import uuid4 as _uuid4

        sim_time = _clock.get_time_string() if _clock and _clock.current_time else None

        result = _broker.submit_bracket_order(
            client_order_id=_uuid4(),
            symbol=symbol,
            quantity=shares,
            stop_loss_price=None,  # Monitor controls exits
            limit_price=D(str(limit_price)) if limit_price else None,
            exit_mode=exit_mode,
            sim_time=sim_time,
            entry_trigger=entry_trigger,
        )

        if result:
            log.info(f"[{case_id}] ORDER: {symbol} x{shares} @ ${limit_price} ({side})")
        return result

    ctx.engine._submit_order = sim_submit_order_historical

    # -- Callback 13: engine._get_order_status = None (L1046) --
    ctx.engine._get_order_status = None

    # -- Callback 14: monitor._submit_scale_order (L1049) --
    ctx.engine.monitor._submit_scale_order = sim_submit_order_historical

    # Set engine to RUNNING so step_clock_ctx triggers entry checks
    # Can't call engine.start() because it spawns background tasks we don't want
    ctx.engine.state = WarriorEngineState.RUNNING

    # Attach per-context clock to engine for concurrent safety (Phase 7 Task 3)
    # warrior_entry_helpers.update_candidate_technicals uses getattr(engine, '_sim_clock')
    ctx.engine._sim_clock = ctx.clock

    log.info(f"[{case_id}] Loaded {len(data.bars)} bars for {symbol}, engine=RUNNING, all callbacks wired")
    return len(data.bars)



def _run_case_sync(case_tuple: tuple) -> dict:
    """
    Run a single test case in a separate process.
    Must be a top-level function (picklable for ProcessPoolExecutor).
    Receives (case_dict, yaml_data_dict) as a tuple.
    """
    import asyncio
    case, yaml_data = case_tuple
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_run_single_case_async(case, yaml_data))
    finally:
        loop.close()


async def _run_single_case_async(case: dict, yaml_data: dict) -> dict:
    """Async wrapper that creates SimContext and runs one case in an isolated process."""
    import time
    case_id = case.get("id", "unknown")
    symbol = case.get("symbol", "")
    ross_pnl = case.get("ross_pnl", 0) or 0
    start = time.time()

    try:
        # Create isolated context (fresh process = no shared state)
        ctx = SimContext.create(case_id)

        # Set ContextVars for this task
        from nexus2.adapters.simulation.sim_clock import set_simulation_clock_ctx
        from nexus2.domain.automation.trade_event_service import set_sim_mode_ctx
        set_simulation_clock_ctx(ctx.clock)
        set_sim_mode_ctx(True)

        # Load test case into context
        bar_count = load_case_into_context(ctx, case, yaml_data)

        if bar_count == 0:
            return {
                "case_id": case_id, "symbol": symbol,
                "date": case.get("trade_date"),
                "bar_count": 0, "trades": [], "total_pnl": 0,
                "ross_pnl": ross_pnl, "delta": -ross_pnl,
                "error": "No bars loaded",
            }

        # Step through all bars + 30 min EOD buffer
        await step_clock_ctx(ctx, bar_count + 30)

        # EOD close: force-close any open positions
        eod_positions = ctx.broker.get_positions()
        for pos in eod_positions:
            pos_symbol = pos.get("symbol")
            pos_qty = pos.get("qty", 0)
            if pos_qty > 0:
                eod_price = ctx.broker._current_prices.get(
                    pos_symbol, pos.get("avg_price", 0)
                )
                ctx.broker.sell_position(pos_symbol, pos_qty)

                # Log EOD exit to warrior_db
                try:
                    from nexus2.db.warrior_db import (
                        get_warrior_trade_by_symbol, log_warrior_exit
                    )
                    trade = get_warrior_trade_by_symbol(pos_symbol)
                    if trade:
                        log_warrior_exit(
                            trade_id=trade["id"],
                            exit_price=float(eod_price),
                            exit_reason="eod_close",
                            quantity_exited=pos_qty,
                        )
                except Exception as e:
                    log.warning(f"[{case_id}] warrior_db EOD exit failed: {e}")

        # Collect results
        account = ctx.broker.get_account()
        realized = round(account.get("realized_pnl", 0), 2)
        unrealized = round(account.get("unrealized_pnl", 0), 2)
        total_pnl = round(realized + unrealized, 2)
        case_time = round(time.time() - start, 2)

        return {
            "case_id": case_id, "symbol": symbol,
            "date": case.get("trade_date"),
            "bar_count": bar_count,
            "trades": [],
            "realized_pnl": realized,
            "unrealized_pnl": unrealized,
            "total_pnl": total_pnl,
            "ross_pnl": ross_pnl,
            "delta": round(total_pnl - ross_pnl, 2),
            "runtime_seconds": case_time,
        }
    except Exception as e:
        log.error(f"[{case_id}] Failed: {e}")
        return {
            "case_id": case_id, "symbol": symbol,
            "date": case.get("trade_date"),
            "bar_count": 0, "trades": [], "total_pnl": 0,
            "ross_pnl": ross_pnl, "delta": -ross_pnl,
            "error": str(e),
            "runtime_seconds": round(time.time() - start, 2),
        }


async def run_batch_concurrent(cases: list, yaml_data: dict) -> list:
    """
    Run all test cases in parallel using ProcessPoolExecutor.

    Each case runs in a separate process for true CPU parallelism,
    bypassing the GIL. Each process creates its own event loop and
    SimContext with fully isolated state.

    Args:
        cases: List of test case dicts from YAML
        yaml_data: Full YAML data dict

    Returns:
        List of result dicts, one per case
    """
    import asyncio
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor

    loop = asyncio.get_event_loop()
    max_workers = min(len(cases), multiprocessing.cpu_count(), 8)

    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = [
            loop.run_in_executor(pool, _run_case_sync, (case, yaml_data))
            for case in cases
        ]
        results = await asyncio.gather(*futures, return_exceptions=True)

    # Convert exceptions to error dicts
    final = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            final.append({
                "case_id": cases[i].get("id"),
                "symbol": cases[i].get("symbol"),
                "error": str(r),
                "total_pnl": 0,
                "ross_pnl": cases[i].get("ross_pnl", 0) or 0,
            })
        else:
            final.append(r)
    return final

