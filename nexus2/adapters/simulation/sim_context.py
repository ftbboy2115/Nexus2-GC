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
    def create(cls, case_id: str, batch_id: Optional[str] = None, config_overrides: Optional[dict] = None, monitor_overrides: Optional[dict] = None) -> "SimContext":
        clock = SimulationClock()
        
        # MockBroker with injected clock (Wave 1 Phase 1B)
        broker = MockBroker(initial_cash=100_000, clock=clock)
        
        # Monitor with clean state (R2 fix)
        monitor = WarriorMonitor()
        monitor.sim_mode = True
        monitor._recently_exited_file = None
        monitor._recently_exited = {}
        monitor._recently_exited_sim_time = {}
        
        # Load saved monitor settings so concurrent runner uses same config as sequential
        # Without this, concurrent gets dataclass defaults while sequential gets saved settings
        try:
            from nexus2.db.warrior_monitor_settings import load_monitor_settings, apply_monitor_settings
            saved_settings = load_monitor_settings()
            if saved_settings:
                apply_monitor_settings(monitor.settings, saved_settings)
        except Exception as e:
            print(f"[SimContext] Failed to load saved monitor settings, using defaults: {e}")
        
        # Engine + Scanner per context (R3 fix)
        engine = WarriorEngine(
            config=WarriorEngineConfig(sim_only=True),
            scanner=WarriorScannerService(),
            monitor=monitor,
        )
        engine._pending_entries_file = None  # Disable disk persistence
        
        # Load BATCH settings (committed, version-controlled) — NOT the live settings
        # This prevents divergence when Windows and VPS have different warrior_settings.json
        try:
            from nexus2.db.warrior_settings import apply_settings_to_config
            import json
            from pathlib import Path
            batch_settings_file = Path(__file__).parent.parent.parent.parent / "data" / "warrior_settings_batch.json"
            if batch_settings_file.exists():
                with open(batch_settings_file, 'r') as f:
                    saved_engine_settings = json.load(f)
                log.info(f"[SimContext] Loaded batch settings from {batch_settings_file}")
            else:
                log.warning(f"[SimContext] Batch settings not found at {batch_settings_file}, using defaults")
                saved_engine_settings = None
            if saved_engine_settings:
                apply_settings_to_config(engine.config, saved_engine_settings)
                engine.config.sim_only = True  # Force sim_only regardless of saved settings
        except Exception as e:
            print(f"[SimContext] Failed to load batch engine settings, using defaults: {e}")
        
        # Apply config overrides from param sweep (takes precedence over saved settings)
        if config_overrides:
            from decimal import Decimal as _D
            for key, value in config_overrides.items():
                if hasattr(engine.config, key):
                    # Auto-convert to Decimal if existing field is Decimal (prevents float*Decimal TypeError)
                    current = getattr(engine.config, key)
                    if isinstance(current, _D) and not isinstance(value, _D):
                        value = _D(str(value))
                    setattr(engine.config, key, value)
                    log.info(f"[SimContext] Override: engine.config.{key} = {value}")
        
        # Apply monitor overrides from param sweep (takes precedence over saved settings)
        if monitor_overrides:
            for key, value in monitor_overrides.items():
                if hasattr(engine.monitor.settings, key):
                    setattr(engine.monitor.settings, key, value)
                    log.info(f"[SimContext] Override: monitor.settings.{key} = {value}")
        
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

            # Log exit to warrior_db (matches LIVE/sequential sim behavior)
            # Without this, trades stay status='open' and get_all_warrior_trades('closed') returns nothing
            try:
                from nexus2.db.warrior_db import (
                    get_all_warrior_trades_by_symbol, log_warrior_exit
                )
                # FIX: Close ALL active records, not just .first()
                # Scale-ins create new DB rows, and .first() only closes one,
                # leaving orphaned ghost trades with exit_reason=null.
                trades = get_all_warrior_trades_by_symbol(signal.symbol)
                for trade in trades:
                    exit_reason = signal.reason.value if hasattr(signal.reason, 'value') else str(signal.reason)
                    log_warrior_exit(
                        trade_id=trade["id"],
                        exit_price=float(signal.exit_price),
                        exit_reason=exit_reason,
                        quantity_exited=trade.get("remaining_quantity") or trade.get("quantity", 0),
                        exit_time_override=ctx.clock.current_time,
                    )
            except Exception as e:
                log.warning(f"[{case_id}] warrior_db exit log failed: {e}")

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
        Supports "1min", "5min", and "10s" timeframes.
        """
        time_with_seconds = _clock.get_time_string_with_seconds()
        time_str = _clock.get_time_string()

        # 10s timeframe: use 10s bars if available, fall back to 1min
        if timeframe == "10s":
            if _loader.has_10s_bars(symbol):
                # For 10s bars, exclude current 10s bar to avoid leakage
                # Step back by 10 seconds from current time
                bars = _loader.get_bars_up_to(symbol, time_with_seconds, "10s", include_continuity=False)
                if bars and len(bars) > limit:
                    bars = bars[-limit:]
                return bars
            else:
                # Fall back to 1min when 10s data unavailable
                timeframe = "1min"

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

    # -- Callback 6: sim_get_quote_with_spread (returns dict, not float) --
    async def sim_get_quote_with_spread(symbol: str, _broker=ctx.broker):
        """Return quote dict with price/bid/ask for sim mode.

        Downstream code (spread exit, entry guards) calls .get('bid') etc. on this,
        so we MUST return a dict — not a raw float like sim_get_price does.
        In sim there is no real spread, so bid == ask == price.
        """
        price = _broker.get_price(symbol)
        if price is None:
            return None
        return {"price": price, "bid": price, "ask": price}

    # -- set_callbacks (L960-967): wires callbacks 1,2,3,4,5 + callback 6 --
    ctx.engine.monitor.set_callbacks(
        get_price=sim_get_price,
        get_prices_batch=sim_get_prices_batch,
        execute_exit=sim_execute_exit,
        update_stop=sim_update_stop,
        get_intraday_candles=sim_get_intraday_bars,
        get_quote_with_spread=sim_get_quote_with_spread,  # Callback 6: returns dict (Phase 11 C3 fix)
        on_profit_exit=ctx.engine._handle_profit_exit,  # Enable re-entry after profitable exits
        on_exit_pnl=ctx.engine._handle_exit_pnl,  # Track P&L for re-entry quality gate
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



def _compute_avg_exit_price(wt: dict) -> float | None:
    """Compute volume-weighted average exit price across all exits (partials + final).

    Args:
        wt: Trade dict from warrior_db (has partial_exit_prices JSON, exit_price, remaining_quantity, quantity)

    Returns:
        Volume-weighted average exit price, or exit_price if no partials, or None if no exit.
    """
    import json

    exit_price_str = wt.get("exit_price")
    partial_json = wt.get("partial_exit_prices")

    # No exit at all
    if not exit_price_str:
        return None

    final_exit_price = float(exit_price_str)
    original_qty = wt.get("quantity", 0)

    # No partials — just use exit_price
    if not partial_json:
        return round(final_exit_price, 2)

    try:
        partials = json.loads(partial_json)
    except (json.JSONDecodeError, TypeError):
        return round(final_exit_price, 2)

    if not partials:
        return round(final_exit_price, 2)

    # Compute VWAP across all exits
    total_value = 0.0
    total_qty = 0
    for p in partials:
        total_value += p["price"] * p["qty"]
        total_qty += p["qty"]

    # Final exit quantity = original - partial total
    final_qty = original_qty - total_qty
    if final_qty > 0:
        total_value += final_exit_price * final_qty
        total_qty += final_qty

    if total_qty <= 0:
        return round(final_exit_price, 2)

    return round(total_value / total_qty, 4)


def _run_case_sync(case_tuple: tuple) -> dict:
    """
    Run a single test case in a separate process.
    Must be a top-level function (picklable for ProcessPoolExecutor).
    Receives (case_dict, yaml_data_dict, skip_guards[, config_overrides[, monitor_overrides]]) as a tuple.
    """
    # === PER-PROCESS IN-MEMORY DB (Phase 8) ===
    # Replace shared warrior.db with ephemeral in-memory SQLite.
    # Solves all 9 contamination vectors (F1-F7, A1a, A1b).
    # Each process gets clean state; DB is destroyed on process exit.
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import nexus2.db.warrior_db as wdb

    mem_engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    wdb.warrior_engine = mem_engine
    wdb.WarriorSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=mem_engine)
    wdb.WarriorBase.metadata.create_all(bind=mem_engine)

    import asyncio
    # Support 2-tuple through 5-tuple (with config_overrides and monitor_overrides)
    if len(case_tuple) == 5:
        case, yaml_data, skip_guards, config_overrides, monitor_overrides = case_tuple
    elif len(case_tuple) == 4:
        case, yaml_data, skip_guards, config_overrides = case_tuple
        monitor_overrides = None
    elif len(case_tuple) == 3:
        case, yaml_data, skip_guards = case_tuple
        config_overrides = None
        monitor_overrides = None
    else:
        case, yaml_data = case_tuple
        skip_guards = False
        config_overrides = None
        monitor_overrides = None
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_run_single_case_async(case, yaml_data, skip_guards=skip_guards, config_overrides=config_overrides, monitor_overrides=monitor_overrides))
    finally:
        loop.close()


async def _run_single_case_async(case: dict, yaml_data: dict, skip_guards: bool = False, config_overrides: Optional[dict] = None, monitor_overrides: Optional[dict] = None) -> dict:
    """Async wrapper that creates SimContext and runs one case in an isolated process.

    NOTE: Dual P&L System
    ---------------------
    Two independent P&L calculations exist in the sim engine:

    1. MockBroker P&L (top-level `total_pnl` in result):
       Formula: (current_price - avg_entry_price) × sell_qty
       Source: mock_broker.py → ctx.broker.get_account()["realized_pnl"]

    2. warrior_db P&L (per-trade `pnl` in result):
       Formula: (exit_price - entry) × quantity, accumulated across partial exits
       Source: warrior_db.py → trade.realized_pnl

    These can diverge when scale-ins shift avg_entry_price in MockBroker but
    warrior_db uses the original (or updated via complete_scaling) entry_price.
    The per-trade pnl from warrior_db is what users see in trade details.

    When partial exits occur, the displayed exit_price only shows the FINAL exit,
    while realized_pnl includes all partials. Use avg_exit_price for reconciliation.
    """
    import time
    case_id = case.get("id", "unknown")
    symbol = case.get("symbol", "")
    ross_pnl = case.get("ross_pnl", 0) or 0
    start = time.time()

    try:
        # Create isolated context with config and monitor overrides (param sweeps)
        ctx = SimContext.create(case_id, config_overrides=config_overrides, monitor_overrides=monitor_overrides)

        # Phase 1: Set skip_guards on engine (A/B testing mode)
        if skip_guards:
            assert ctx.engine.monitor.sim_mode, "skip_guards only allowed in simulation"
            ctx.engine.skip_guards = True
            log.info(f"[{case_id}] Guards DISABLED (A/B test mode)")

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

        # Step through full day: 04:00→20:00, matches sequential runner
        await step_clock_ctx(ctx, 960)

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

                # Log EOD exit to warrior_db — close ALL active records
                try:
                    from nexus2.db.warrior_db import (
                        get_all_warrior_trades_by_symbol, log_warrior_exit
                    )
                    # FIX: Close ALL active records, not just .first()
                    # Scale-ins create new DB rows, and .first() only closes one,
                    # leaving orphaned ghost trades with exit_reason=null.
                    trades = get_all_warrior_trades_by_symbol(pos_symbol)
                    for trade in trades:
                        log_warrior_exit(
                            trade_id=trade["id"],
                            exit_price=float(eod_price),
                            exit_reason="eod_close",
                            quantity_exited=trade.get("remaining_quantity") or trade.get("quantity", 0),
                            exit_time_override=ctx.clock.current_time,
                        )
                except Exception as e:
                    log.warning(f"[{case_id}] warrior_db EOD exit failed: {e}")

        # Collect results
        account = ctx.broker.get_account()
        realized = round(account.get("realized_pnl", 0), 2)
        unrealized = round(account.get("unrealized_pnl", 0), 2)
        total_pnl = round(realized + unrealized, 2)
        case_time = round(time.time() - start, 2)

        # Extract trade details from per-process in-memory warrior_db
        trades = []
        try:
            from nexus2.db.warrior_db import get_all_warrior_trades
            for status_filter in ("closed", "partial", "open"):
                result = get_all_warrior_trades(limit=100, status_filter=status_filter)
                for wt in (result.get("trades", []) if isinstance(result, dict) else []):
                    if wt.get("is_sim"):
                        trades.append({
                            "entry_price": round(float(wt.get("entry_price", 0)), 2),
                            "exit_price": round(float(wt.get("exit_price", 0)), 2) if wt.get("exit_price") else None,
                            "shares": wt.get("quantity", 0),
                            "pnl": round(float(wt.get("realized_pnl", 0)), 2),
                            # Partial exit enrichment (sim display fix)
                            "partial_taken": wt.get("partial_taken", False),
                            "remaining_quantity": wt.get("remaining_quantity"),
                            "avg_exit_price": _compute_avg_exit_price(wt),
                            "entry_trigger": wt.get("trigger_type"),
                            "exit_mode": wt.get("exit_mode"),
                            "exit_reason": wt.get("exit_reason"),
                            "entry_time": wt.get("entry_time"),
                            "exit_time": wt.get("exit_time"),
                            "stop_price": wt.get("stop_price"),
                            "stop_method": wt.get("stop_method"),
                            "target_price": wt.get("target_price"),
                            "support_level": wt.get("support_level"),
                        })
        except Exception as e:
            log.warning(f"[{case_id}] Failed to extract trades from warrior_db: {e}")

        # Extract guard block events from per-process in-memory tracking
        # FIX: Previously read from shared nexus.db which accumulated blocks
        # across ALL runs (no cleanup, no date filter). This caused guard_block_count
        # to grow with every batch run and misled root cause investigations.
        # Now uses in-memory list tracked by trade_event_service during THIS run only.
        guard_blocks = []
        try:
            import json as _json
            from nexus2.domain.automation.trade_event_service import trade_event_service as _tes
            blocks_raw = getattr(_tes, '_run_guard_blocks', [])
            for b in blocks_raw:
                if b.get("symbol", "").upper() == symbol.upper():
                    guard_blocks.append(b)
        except Exception as e:
            log.warning(f"[{case_id}] Failed to extract guard blocks: {e}")

        # Phase 2: Counterfactual guard analysis
        guard_analysis = None
        if guard_blocks:
            try:
                all_bars = ctx.loader.get_bars_up_to(symbol, "19:30", include_continuity=False)
                guard_analysis = analyze_guard_outcomes(guard_blocks, all_bars, symbol)
            except Exception as e:
                log.warning(f"[{case_id}] Guard analysis failed: {e}")

        return {
            "case_id": case_id, "symbol": symbol,
            "date": case.get("trade_date"),
            "bar_count": bar_count,
            "trades": trades,
            "realized_pnl": realized,
            "unrealized_pnl": unrealized,
            "total_pnl": total_pnl,
            "ross_pnl": ross_pnl,
            "delta": round(total_pnl - ross_pnl, 2),
            "guard_blocks": guard_blocks,
            "guard_block_count": len(guard_blocks),
            "guard_analysis": guard_analysis,
            "skip_guards": skip_guards,
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


def analyze_guard_outcomes(guard_blocks: list, bars: list, symbol: str) -> dict:
    """For each guard block, check what price did after the block.

    Returns per-guard-type accuracy stats and per-block detail.

    A block is "correct" if price at +15 min is LOWER than the blocked
    entry price. If price went higher, it was a "missed opportunity".
    """
    from collections import defaultdict

    outcomes = []
    by_guard = defaultdict(lambda: {"blocks": 0, "correct": 0, "missed": 0, "net_impact": 0.0})

    for block in guard_blocks:
        blocked_price = block.get("blocked_price")
        blocked_time = block.get("blocked_time")
        guard_type = block.get("guard", "unknown")

        if blocked_price is None or blocked_time is None or not bars:
            by_guard[guard_type]["blocks"] += 1
            continue

        blocked_price = float(blocked_price)

        # Parse blocked_time to compare with bar times
        # blocked_time is HH:MM or HH:MM:SS format
        block_time_str = str(blocked_time)
        if "T" in block_time_str:
            block_time_str = block_time_str.split("T")[1]
        # Normalize to HH:MM for comparison
        block_hhmm = block_time_str[:5] if len(block_time_str) >= 5 else block_time_str

        # Find bars AFTER the block time
        future_bars = []
        found_block_bar = False
        for b in bars:
            bar_time = getattr(b, "time", None) or ""
            if not bar_time:
                continue
            if bar_time >= block_hhmm:
                if not found_block_bar:
                    found_block_bar = True
                    continue  # Skip the block bar itself
                future_bars.append(b)

        if not future_bars:
            by_guard[guard_type]["blocks"] += 1
            continue

        # Price at various horizons
        def _price_at_offset(bars_after, minutes):
            for b in bars_after:
                bar_time = getattr(b, "time", None) or ""
                if not bar_time or not block_hhmm:
                    continue
                try:
                    bh, bm = int(bar_time.split(":")[0]), int(bar_time.split(":")[1])
                    oh, om = int(block_hhmm.split(":")[0]), int(block_hhmm.split(":")[1])
                    diff = (bh * 60 + bm) - (oh * 60 + om)
                    if diff >= minutes:
                        return float(getattr(b, "close", getattr(b, "high", 0)))
                except (ValueError, IndexError):
                    continue
            return None

        price_5m = _price_at_offset(future_bars, 5)
        price_15m = _price_at_offset(future_bars, 15)
        price_30m = _price_at_offset(future_bars, 30)

        # MFE/MAE from next 30 bars
        window = future_bars[:30]
        highs = [float(b.high) for b in window if hasattr(b, "high")]
        lows = [float(b.low) for b in window if hasattr(b, "low")]
        mfe = round(max(highs) - blocked_price, 4) if highs else 0
        mae = round(blocked_price - min(lows), 4) if lows else 0

        # Classify: correct if price_15m < blocked_price (would have been a losing entry)
        if price_15m is not None:
            outcome = "CORRECT_BLOCK" if price_15m < blocked_price else "MISSED_OPPORTUNITY"
            hypo_pnl = round(price_15m - blocked_price, 4)
        else:
            outcome = "NO_DATA"
            hypo_pnl = 0

        outcomes.append({
            "guard": guard_type,
            "blocked_price": blocked_price,
            "blocked_time": blocked_time,
            "price_5m": price_5m,
            "price_15m": price_15m,
            "price_30m": price_30m,
            "mfe": mfe,
            "mae": mae,
            "outcome": outcome,
            "hypothetical_pnl_15m": hypo_pnl,
        })

        # Aggregate by guard type
        by_guard[guard_type]["blocks"] += 1
        if outcome == "CORRECT_BLOCK":
            by_guard[guard_type]["correct"] += 1
        elif outcome == "MISSED_OPPORTUNITY":
            by_guard[guard_type]["missed"] += 1
        by_guard[guard_type]["net_impact"] += hypo_pnl

    total = len(outcomes)
    correct = sum(1 for o in outcomes if o["outcome"] == "CORRECT_BLOCK")
    missed = sum(1 for o in outcomes if o["outcome"] == "MISSED_OPPORTUNITY")

    # Per-guard summary
    by_guard_summary = {}
    for gtype, stats in by_guard.items():
        gt_total = stats["correct"] + stats["missed"]
        by_guard_summary[gtype] = {
            "blocks": stats["blocks"],
            "correct": stats["correct"],
            "missed": stats["missed"],
            "accuracy": round(stats["correct"] / gt_total, 3) if gt_total > 0 else None,
            "net_impact": round(stats["net_impact"], 2),
        }

    return {
        "total_blocks": len(guard_blocks),
        "analyzed_blocks": total,
        "correct_blocks": correct,
        "missed_opportunities": missed,
        "guard_accuracy": round(correct / (correct + missed), 3) if (correct + missed) > 0 else None,
        "net_guard_impact": round(sum(o["hypothetical_pnl_15m"] for o in outcomes), 2),
        "by_guard_type": by_guard_summary,
        "details": outcomes,
    }


async def run_batch_concurrent(cases: list, yaml_data: dict, skip_guards: bool = False, config_overrides: Optional[dict] = None, monitor_overrides: Optional[dict] = None) -> list:
    """
    Run all test cases in parallel using ProcessPoolExecutor.

    Each case runs in a separate process for true CPU parallelism,
    bypassing the GIL. Each process creates its own event loop and
    SimContext with fully isolated state.

    Args:
        cases: List of test case dicts from YAML
        yaml_data: Full YAML data dict
        skip_guards: If True, skip entry guards (A/B testing)
        config_overrides: Engine config overrides for param sweeps
        monitor_overrides: Monitor settings overrides for param sweeps

    Returns:
        List of result dicts, one per case
    """
    import asyncio
    import multiprocessing
    from concurrent.futures import ProcessPoolExecutor

    loop = asyncio.get_event_loop()
    max_workers = min(len(cases), multiprocessing.cpu_count(), 8)

    with ProcessPoolExecutor(max_workers=max_workers, mp_context=multiprocessing.get_context("spawn")) as pool:
        futures = [
            loop.run_in_executor(pool, _run_case_sync, (case, yaml_data, skip_guards, config_overrides, monitor_overrides))
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

