"""
Simulation Routes

API endpoints for controlling the mock trading simulation environment.
Extracted from automation.py for maintainability.
"""

from fastapi import APIRouter
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

# Create a separate router for simulation endpoints
router = APIRouter(prefix="/automation", tags=["simulation"])


# ==================== SIMULATION ENDPOINTS ====================

@router.get("/simulation/status", response_model=dict)
async def get_simulation_status():
    """
    Get simulation environment status.
    
    Returns current simulation clock time, broker state, and market data info.
    """
    from nexus2.adapters.simulation import (
        get_simulation_clock, 
        get_mock_market_data
    )
    
    clock = get_simulation_clock()
    data = get_mock_market_data()
    
    # Get mock broker from execute_callback if it exists
    broker_state = None
    try:
        # Import and check the execute_callback for _mock_broker
        from nexus2.api.routes.automation import start_scheduler
        # The mock broker is attached to execute_callback inside start_scheduler's closure
        # We'll access it through a module-level reference instead
        from nexus2.api.routes.automation_state import get_sim_broker
        mock_broker = get_sim_broker()
        if mock_broker:
            broker_state = mock_broker.to_dict()
    except Exception:
        pass
    
    return {
        "clock": clock.to_dict(),
        "market_data": data.to_dict(),
        "broker": broker_state,
    }


@router.get("/simulation/positions", response_model=dict)
async def get_sim_positions():
    """
    Get positions from MockBroker (sim mode only).
    
    Returns simulated positions, account balance, and P&L.
    """
    try:
        from nexus2.api.routes.automation_state import get_sim_broker
        mock_broker = get_sim_broker()
        
        if not mock_broker:
            return {
                "status": "no_broker",
                "message": "MockBroker not initialized. Start scheduler in sim_mode first.",
                "positions": [],
                "count": 0,
            }
        
        positions = mock_broker.get_positions()
        account = mock_broker.get_account()
        
        return {
            "status": "ok",
            "positions": positions,
            "count": len(positions),
            "account": account,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "positions": [],
            "count": 0,
        }


@router.post("/simulation/reset", response_model=dict)
async def reset_simulation(
    start_date: str = None,  # YYYY-MM-DD format
    initial_cash: float = 100_000.0,
    load_synthetic: bool = True,
    symbols: list[str] = None,
):
    """
    Reset simulation environment.
    
    Args:
        start_date: Starting date for simulation (default: 60 days ago)
        initial_cash: Starting cash balance
        load_synthetic: Generate synthetic test data
        symbols: Symbols to load data for (default: NVDA, AAPL, MSFT)
    """
    from nexus2.adapters.simulation import (
        reset_simulation_clock,
        reset_mock_market_data
    )
    from nexus2.adapters.simulation.mock_broker import MockBroker
    from datetime import datetime, timedelta
    import pytz
    
    ET = pytz.timezone("US/Eastern")
    
    # Parse start date or default to 60 days ago
    if start_date:
        start_dt = ET.localize(datetime.strptime(start_date, "%Y-%m-%d").replace(hour=9, minute=30))
    else:
        start_dt = datetime.now(ET) - timedelta(days=60)
        start_dt = start_dt.replace(hour=9, minute=30, second=0, microsecond=0)
    
    # Reset clock
    clock = reset_simulation_clock(start_time=start_dt)
    
    # Reset market data
    data = reset_mock_market_data()
    data.set_clock(clock)
    
    # Load synthetic data if requested
    if symbols is None:
        symbols = ["NVDA", "AAPL", "MSFT", "TSLA", "META"]
    
    if load_synthetic:
        for sym in symbols:
            data.load_synthetic_data(sym, start_price=150.0, days=60)
    
    # Create mock broker (use thread-safe setter)
    from nexus2.api.routes.automation_state import set_sim_broker
    broker = MockBroker(initial_cash=initial_cash)
    set_sim_broker(broker)
    
    # Set initial prices from loaded data
    for sym in data.get_symbols():
        price = data.get_current_price(sym)
        if price:
            broker.set_price(sym, price)
    
    # Clear database positions (simulation creates position records)
    from nexus2.db import SessionLocal, PositionRepository
    try:
        db = SessionLocal()
        position_repo = PositionRepository(db)
        open_positions = position_repo.get_open()
        for pos in open_positions:
            position_repo.close(pos.id, exit_price="0", remaining_shares=0)
        db.commit()
        logger.info(f"[Simulation] Cleared {len(open_positions)} database positions")
    except Exception as e:
        logger.warning(f"[Simulation] Could not clear DB positions: {e}")
    finally:
        db.close()
    
    logger.info(f"[Simulation] Reset: start={start_dt}, cash=${initial_cash:,.0f}, symbols={symbols}")
    
    return {
        "status": "reset",
        "clock": clock.to_dict(),
        "market_data": data.to_dict(),
        "broker": broker.to_dict(),
    }


@router.post("/simulation/load_htf_pattern", response_model=dict)
async def load_htf_pattern(
    symbol: str = "HTFTEST",
    start_price: float = 50.0,
    move_percent: float = 120.0,  # 120% = HTF qualifies (needs 90%+)
    pullback_percent: float = 15.0,  # 15% pullback in flag
):
    """
    Load synthetic data with an HTF-qualifying pattern.
    
    Creates a stock with:
    - A strong uptrend (the "pole") 
    - A tight consolidation (the "flag")
    - Pullback within 25% (qualifying for HTF)
    """
    from nexus2.adapters.simulation import get_mock_market_data, get_simulation_clock
    from datetime import date, timedelta
    import random
    
    data = get_mock_market_data()
    clock = get_simulation_clock()
    
    sim_date = clock.get_trading_day()
    if isinstance(sim_date, str):
        sim_date = date.fromisoformat(sim_date)
    
    # Generate 90 trading days of data ENDING at sim_date
    # Work backwards to calculate start date
    total_trading_days = 90
    calendar_days = int(total_trading_days * 7 / 5) + 10  # Rough estimate + buffer
    start_date = sim_date - timedelta(days=calendar_days)
    
    # Generate trading days between start and sim_date
    trading_dates = []
    current = start_date
    while current <= sim_date:
        if current.weekday() < 5:  # Mon-Fri
            trading_dates.append(current)
        current += timedelta(days=1)
    
    # Take last 90 trading days
    trading_dates = trading_dates[-total_trading_days:]
    
    if len(trading_dates) < 60:  # Need at least 60 days for HTF scanner
        return {"error": "Not enough trading days", "count": len(trading_dates)}
    
    bars = []
    price = start_price
    
    # Split into pole (first 60%) and flag (last 40%)
    pole_days = int(len(trading_dates) * 0.6)
    flag_days = len(trading_dates) - pole_days
    
    # Calculate target high price
    target_high = start_price * (1 + move_percent / 100)
    daily_gain = (target_high / start_price) ** (1 / pole_days) - 1
    
    # Phase 1: Pole (strong uptrend)
    for i in range(pole_days):
        open_price = price
        price = price * (1 + daily_gain * (0.8 + random.random() * 0.4))
        close_price = price
        
        high_price = max(open_price, close_price) * (1 + random.random() * 0.02)
        low_price = min(open_price, close_price) * (1 - random.random() * 0.02)
        
        bars.append({
            "date": trading_dates[i].isoformat(),
            "open": round(open_price, 2),
            "high": round(high_price, 2),
            "low": round(low_price, 2),
            "close": round(close_price, 2),
            "volume": int(2_000_000 * (0.8 + random.random() * 0.4)),
        })
    
    highest_high = price
    pullback_target = highest_high * (1 - pullback_percent / 100)
    
    # Phase 2: Flag (tight consolidation)
    for i in range(flag_days):
        open_price = price
        volatility = 0.01
        price = price * (1 + (random.random() - 0.5) * volatility)
        
        # Keep in range
        if price < pullback_target:
            price = pullback_target * (1 + random.random() * 0.02)
        if price > highest_high:
            price = highest_high * (1 - random.random() * 0.02)
        
        close_price = price
        high_price = max(open_price, close_price) * (1 + random.random() * 0.01)
        low_price = min(open_price, close_price) * (1 - random.random() * 0.01)
        
        bars.append({
            "date": trading_dates[pole_days + i].isoformat(),
            "open": round(open_price, 2),
            "high": round(high_price, 2),
            "low": round(low_price, 2),
            "close": round(close_price, 2),
            "volume": int(500_000 * (0.8 + random.random() * 0.4)),
        })
    
    count = data.load_data(symbol, bars)
    
    return {
        "status": "loaded",
        "symbol": symbol,
        "bars_loaded": count,
        "start_price": start_price,
        "target_high": round(highest_high, 2),
        "move_percent": round((highest_high - start_price) / start_price * 100, 1),
        "current_price": round(price, 2),
        "pullback_percent": round((highest_high - price) / highest_high * 100, 1),
        "date_range": f"{trading_dates[0].isoformat()} to {trading_dates[-1].isoformat()}",
    }


@router.get("/simulation/debug", response_model=dict)
async def debug_simulation():
    """
    Debug endpoint - shows what get_gainers() and get_actives() return.
    Also shows EP session snapshots to debug gap calculations.
    """
    from nexus2.adapters.simulation import get_simulation_clock, get_mock_market_data
    
    clock = get_simulation_clock()
    data = get_mock_market_data()
    
    # Ensure clock is connected
    if data._sim_clock is None:
        data.set_clock(clock)
    
    gainers = data.get_gainers()[:5]
    
    # Build EP snapshots for top gainers to show gap vs change
    ep_snapshots = []
    for g in gainers:
        snap = data.build_ep_session_snapshot(g["symbol"])
        if snap:
            # Calculate gap (open vs yesterday close)
            gap_pct = ((snap["session_open"] - snap["yesterday_close"]) / snap["yesterday_close"]) * 100
            ep_snapshots.append({
                "symbol": g["symbol"],
                "yesterday_close": snap["yesterday_close"],
                "session_open": snap["session_open"],
                "session_close": snap["last_price"],
                "gap_pct": round(gap_pct, 2),  # THIS is what EP scanner checks
                "change_pct": round(g["change_percent"], 2),  # This is close vs yesterday
            })
    
    return {
        "clock": clock.get_trading_day(),
        "is_market_hours": clock.is_market_hours(),
        "gainers": gainers,
        "actives": data.get_actives()[:5],
        "symbols": data.get_symbols(),
        "ep_snapshots": ep_snapshots,  # NEW: Shows gap vs change
    }


@router.post("/simulation/diagnostic_scan", response_model=dict)
async def diagnostic_scan():
    """
    Run EP scanner directly with MockMarketData and capture all debug output.
    
    This shows exactly why candidates are being rejected.
    """
    from nexus2.adapters.simulation import get_simulation_clock, get_mock_market_data
    from nexus2.domain.scanner.ep_scanner_service import EPScannerService, EPScanSettings
    import io
    import sys
    
    clock = get_simulation_clock()
    data = get_mock_market_data()
    
    # Ensure clock is connected
    if data._sim_clock is None:
        data.set_clock(clock)
    
    # Use relaxed sim_mode settings
    sim_ep_settings = EPScanSettings(
        min_gap=3.0,    # 3% gap minimum 
        min_rvol=0.5,   # 0.5x relative volume
        min_price=5.0,
        min_dollar_vol=1_000_000,  # Lower for simulation
    )
    
    # Create scanner with MockMarketData
    ep_scanner = EPScannerService(settings=sim_ep_settings, market_data=data)
    
    # Capture stdout for verbose output
    old_stdout = sys.stdout
    sys.stdout = captured = io.StringIO()
    
    try:
        # Run scan with verbose=True
        result = ep_scanner.scan(verbose=True)
    finally:
        sys.stdout = old_stdout
    
    verbose_output = captured.getvalue()
    
    return {
        "clock": clock.get_trading_day(),
        "candidates_found": len(result.candidates),
        "processed_count": result.processed_count,
        "filtered_count": result.filtered_count,
        "candidates": [
            {
                "symbol": c.symbol,
                "gap_percent": float(c.gap_percent) if c.gap_percent else None,
                "relative_volume": float(c.relative_volume) if c.relative_volume else None,
                "status": c.status.value if c.status else None,
            }
            for c in result.candidates
        ],
        "verbose_output": verbose_output.split("\n") if verbose_output else [],
    }


@router.get("/simulation/diagnostic_htf", response_model=dict)
async def diagnostic_htf(symbol: str = "HTFSTOCK"):
    """
    Debug HTF scanner data flow for a specific symbol.
    """
    from nexus2.adapters.simulation import get_simulation_clock, get_mock_market_data
    from nexus2.domain.scanner.htf_scanner_service import HTFScannerService, HTFScanSettings
    from decimal import Decimal
    
    clock = get_simulation_clock()
    data = get_mock_market_data()
    
    # Ensure clock is connected
    if data._sim_clock is None:
        data.set_clock(clock)
    
    sim_date = clock.get_trading_day()
    
    # Check what data is available
    raw_bars = data._data.get(symbol, [])
    daily_bars = data.get_daily_bars(symbol, days=90)
    history = data.get_historical_prices(symbol, days=90)
    
    # Calculate HTF metrics if we have data
    htf_metrics = {}
    if history and len(history) >= 60:
        window = history[-60:]
        highs = [Decimal(str(d.get("high", 0))) for d in window]
        lows = [Decimal(str(d.get("low", 0))) for d in window]
        
        highest_high = max(highs)
        lowest_low = min([l for l in lows if l > 0])
        current_close = Decimal(str(window[-1].get("close", 0)))
        
        move_pct = ((highest_high - lowest_low) / lowest_low) * 100 if lowest_low > 0 else 0
        pullback_pct = ((highest_high - current_close) / highest_high) * 100 if highest_high > 0 else 0
        
        htf_metrics = {
            "move_pct": float(move_pct),
            "pullback_pct": float(pullback_pct),
            "highest_high": float(highest_high),
            "lowest_low": float(lowest_low),
            "current_close": float(current_close),
            "passes_min_move": float(move_pct) >= 90,
            "passes_max_pullback": float(pullback_pct) <= 25,
        }
    
    return {
        "symbol": symbol,
        "sim_date": sim_date,
        "raw_bars_count": len(raw_bars),
        "daily_bars_count": len(daily_bars),
        "history_count": len(history),
        "first_bar_date": daily_bars[0].date if daily_bars else None,
        "last_bar_date": daily_bars[-1].date if daily_bars else None,
        "htf_metrics": htf_metrics,
    }


@router.post("/simulation/diagnostic_unified_scan", response_model=dict)
async def diagnostic_unified_scan():
    """
    Run UnifiedScannerService directly with MockMarketData and verbose mode.
    
    Mirrors how force_scan works but captures all verbose output to diagnose issues.
    """
    from nexus2.adapters.simulation import get_simulation_clock, get_mock_market_data
    from nexus2.domain.scanner.ep_scanner_service import EPScannerService, EPScanSettings
    from nexus2.domain.scanner.breakout_scanner_service import BreakoutScannerService
    from nexus2.domain.scanner.htf_scanner_service import HTFScannerService
    from nexus2.domain.automation.unified_scanner import (
        UnifiedScannerService,
        UnifiedScanSettings,
        ScanMode,
    )
    import io
    import sys
    
    clock = get_simulation_clock()
    data = get_mock_market_data()
    
    # Ensure clock is connected
    if data._sim_clock is None:
        data.set_clock(clock)
    
    # Use relaxed sim settings
    sim_ep_settings = EPScanSettings(
        min_gap=3.0,
        min_rvol=0.5,
        min_price=5.0,
        min_dollar_vol=1_000_000,
    )
    
    # HTF settings with longer lookback to capture full pole+flag
    from nexus2.domain.scanner.htf_scanner_service import HTFScanSettings
    sim_htf_settings = HTFScanSettings(
        lookback_days=90,  # Capture full pole+flag pattern
        min_dollar_vol=Decimal("1000000"),  # Lower for sim
    )
    
    # Create scanners with MockMarketData
    ep_scanner = EPScannerService(settings=sim_ep_settings, market_data=data)
    breakout_scanner = BreakoutScannerService(market_data=data)
    htf_scanner = HTFScannerService(settings=sim_htf_settings, market_data=data)
    
    # Use same settings as force_scan
    settings = UnifiedScanSettings(
        modes=[ScanMode.EP_ONLY, ScanMode.BREAKOUT_ONLY, ScanMode.HTF_ONLY],
        min_quality_score=5,  # Relaxed for sim
        stop_mode="atr",
        max_stop_atr=1.5,
        max_stop_percent=25.0,  # Relaxed for sim (gap days have wide OR)
    )
    
    scanner = UnifiedScannerService(
        settings=settings,
        ep_scanner=ep_scanner,
        breakout_scanner=breakout_scanner,
        htf_scanner=htf_scanner,
    )
    
    # Capture verbose output
    old_stdout = sys.stdout
    sys.stdout = captured = io.StringIO()
    
    try:
        result = scanner.scan(verbose=True)
    finally:
        sys.stdout = old_stdout
    
    verbose_output = captured.getvalue()
    
    return {
        "clock": clock.get_trading_day(),
        "symbols_loaded": data.get_symbols(),
        "total_signals": result.total_signals,
        "ep_count": result.ep_count,
        "breakout_count": result.breakout_count,
        "htf_count": result.htf_count,
        "signals": [
            {
                "symbol": s.symbol,
                "setup_type": s.setup_type.value,
                "quality_score": s.quality_score,
                "entry_price": float(s.entry_price),
                "tactical_stop": float(s.tactical_stop),
                "tier": s.tier,
            }
            for s in result.signals
        ],
        "diagnostics": [
            {
                "scanner": d.scanner,
                "enabled": d.enabled,
                "candidates_found": d.candidates_found,
                "candidates_passed": d.candidates_passed,
                "rejections": [
                    {"symbol": r.symbol, "reason": r.reason, "threshold": r.threshold, "actual": r.actual_value}
                    for r in d.rejections
                ] if d.rejections else [],
            }
            for d in result.diagnostics
        ],
        "verbose_output": verbose_output.split("\n") if verbose_output else [],
    }


@router.post("/simulation/debug_execute_path", response_model=dict)
async def debug_execute_path():
    """
    Debug endpoint that mimics exactly what execute_callback does.
    This helps trace where MockMarketData stops being used.
    """
    from nexus2.db import SessionLocal, SchedulerSettingsRepository
    from nexus2.domain.automation.services import create_unified_scanner_callback
    from nexus2.adapters.simulation import get_simulation_clock, get_mock_market_data
    
    debug_info = {}
    
    # Step 1: Read settings exactly like execute_callback
    db = SessionLocal()
    try:
        settings_repo = SchedulerSettingsRepository(db)
        sched_settings = settings_repo.get()
        
        sim_mode_setting = getattr(sched_settings, 'sim_mode', False)
        debug_info["sim_mode_raw"] = str(sim_mode_setting)
        debug_info["sim_mode_type"] = type(sim_mode_setting).__name__
        
        sim_mode = sim_mode_setting == "true" if isinstance(sim_mode_setting, str) else bool(sim_mode_setting)
        debug_info["sim_mode_final"] = sim_mode
        
        scan_modes = sched_settings.scan_modes.split(",") if sched_settings.scan_modes else ["ep", "breakout", "htf"]
        debug_info["scan_modes"] = scan_modes
        
    finally:
        db.close()
    
    # Step 2: Create scanner callback
    scanner_func = await create_unified_scanner_callback(
        min_quality=5,
        max_stop_percent=8.0,
        stop_mode="atr",
        max_stop_atr=1.5,
        scan_modes=scan_modes,
        htf_frequency="every_cycle",
        sim_mode=sim_mode,
    )
    
    # Step 3: Call the scanner
    result = await scanner_func()
    
    # Step 4: Check if MockMarketData was used
    clock = get_simulation_clock()
    mock_data = get_mock_market_data()
    debug_info["clock_date"] = clock.get_trading_day()
    debug_info["mock_symbols"] = mock_data.get_symbols()
    
    # Step 5: Return results
    signals = []
    if hasattr(result, 'signals'):
        for sig in result.signals:
            signals.append({
                "symbol": getattr(sig, 'symbol', ''),
                "setup_type": str(getattr(sig, 'setup_type', '')),
                "quality_score": getattr(sig, 'quality_score', 0),
            })
    
    return {
        "debug_info": debug_info,
        "signals_count": len(signals),
        "signals": signals,
    }



@router.post("/simulation/advance", response_model=dict)
async def advance_simulation(
    minutes: int = 0,
    hours: int = 0,
    days: int = 0,
    to_market_open: bool = False,
    to_eod: bool = False,
):
    """
    Advance simulation time.
    
    Args:
        minutes: Advance by N minutes
        hours: Advance by N hours
        days: Advance by N days
        to_market_open: Advance to next market open
        to_eod: Advance to end of day (4:00 PM)
    """
    from nexus2.adapters.simulation import get_simulation_clock, get_mock_market_data
    
    clock = get_simulation_clock()
    data = get_mock_market_data()
    
    old_time = clock.current_time
    
    if to_market_open:
        clock.advance_to_next_market_open()
    elif to_eod:
        clock.advance_to_market_close()
    else:
        clock.advance(minutes=minutes, hours=hours, days=days)
    
    # Update market data prices for new date
    new_prices = data.advance_day()
    
    # Update broker prices if exists (use the thread-safe getter)
    from nexus2.api.routes.automation_state import get_sim_broker
    broker = get_sim_broker()
    if broker is not None:
        for sym, price in new_prices.items():
            broker.set_price(sym, price)
            # Check if stop was triggered
            broker._check_stop_orders(sym)
        print(f"📊 [SIM] Updated prices: {new_prices}")
    
    logger.info(f"[Simulation] Advanced: {old_time} -> {clock.current_time}")
    
    return {
        "old_time": old_time.isoformat(),
        "new_time": clock.current_time.isoformat(),
        "is_market_hours": clock.is_market_hours(),
        "is_eod_window": clock.is_eod_window(),
        "new_prices": new_prices,
    }


@router.get("/simulation/broker", response_model=dict)
async def get_simulation_broker():
    """Get simulation broker state (positions, orders, P&L)."""
    from nexus2.api.routes.automation_state import get_sim_broker
    broker = get_sim_broker()
    if broker is not None:
        return broker.to_dict()
    return {"error": "Simulation not initialized. Call /simulation/reset first."}


@router.post("/simulation/load_historical", response_model=dict)
async def load_historical_data(
    symbol: str,
    start_date: str = None,  # YYYY-MM-DD
    end_date: str = None,  # YYYY-MM-DD
    days: int = 120,  # Default to 120 days if no dates provided
):
    """
    Load real historical data from FMP API for backtesting.
    
    Args:
        symbol: Stock symbol (e.g., SMCI, NVDA)
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        days: Number of days to load (if dates not provided)
    
    Returns:
        Dict with loaded bar count and date range
    """
    from nexus2.adapters.market_data.fmp_adapter import get_fmp_adapter
    from nexus2.adapters.simulation import get_mock_market_data, get_simulation_clock
    
    fmp = get_fmp_adapter()
    data = get_mock_market_data()
    clock = get_simulation_clock()
    
    # Connect clock to data if not already
    if data._sim_clock is None:
        data.set_clock(clock)
    
    # Calculate days needed
    if start_date and end_date:
        from datetime import datetime
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        days = (end - start).days + 30  # Extra buffer for lookback
    
    # Fetch from FMP
    logger.info(f"[Simulation] Loading {days} days of historical data for {symbol}...")
    bars = fmp.get_daily_bars(symbol.upper(), limit=days + 30)
    
    if not bars:
        return {
            "error": f"Failed to load data for {symbol}. Check symbol and FMP rate limits.",
            "rate_stats": fmp.get_rate_stats()
        }
    
    # Convert OHLCV to dict format and filter by date range if provided
    bar_dicts = []
    for bar in bars:
        bar_date = bar.timestamp.strftime("%Y-%m-%d")
        
        # Filter by date range if provided
        if start_date and bar_date < start_date:
            continue
        if end_date and bar_date > end_date:
            continue
        
        bar_dicts.append({
            "date": bar_date,
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": bar.volume,
        })
    
    # Load into MockMarketData
    count = data.load_data(symbol.upper(), bar_dicts)
    
    # Set simulation clock to date with enough history for scanner lookback
    # Only if clock wasn't explicitly set by user (check if clock is at default or very old)
    # The reset endpoint sets the clock, so we respect that
    if bar_dicts and data._sim_clock:
        from datetime import datetime
        import pytz
        ET = pytz.timezone("US/Eastern")
        
        current_clock_date = clock.get_trading_day()
        if isinstance(current_clock_date, str):
            current_clock_date = datetime.strptime(current_clock_date, "%Y-%m-%d").date()
        
        # Check if data covers the current clock date
        first_bar = datetime.strptime(bar_dicts[0]["date"], "%Y-%m-%d").date()
        last_bar = datetime.strptime(bar_dicts[-1]["date"], "%Y-%m-%d").date()
        
        if current_clock_date < first_bar or current_clock_date > last_bar:
            # Clock is outside data range, auto-adjust to a sensible date
            target_idx = min(30, len(bar_dicts) - 1)
            target_date_str = bar_dicts[target_idx]["date"]
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d")
            clock.set_time(ET.localize(target_date.replace(hour=9, minute=30)))
            logger.info(f"[Simulation] Clock adjusted to {target_date_str} (outside data range)")
        else:
            logger.info(f"[Simulation] Clock kept at {current_clock_date} (within data range)")
    
    # Update broker price if exists
    from nexus2.api.routes.automation_state import get_sim_broker
    broker = get_sim_broker()
    if broker is not None and bar_dicts:
        broker.set_price(symbol.upper(), bar_dicts[-1]["close"])
    
    logger.info(f"[Simulation] Loaded {count} bars for {symbol}")
    
    return {
        "symbol": symbol.upper(),
        "bars_loaded": count,
        "date_range": {
            "start": bar_dicts[0]["date"] if bar_dicts else None,
            "end": bar_dicts[-1]["date"] if bar_dicts else None,
        },
        "current_price": bar_dicts[-1]["close"] if bar_dicts else None,
        "clock": clock.to_dict(),
        "rate_stats": fmp.get_rate_stats(),
    }


@router.post("/simulation/load_test_case", response_model=dict)
async def load_test_case(case_id: str):
    """
    Load a curated test case by ID.
    
    Test cases are defined in nexus2/tests/test_cases/kk_setups.yaml
    
    Args:
        case_id: Test case ID (e.g., smci_ep_2023, nvda_ep_2024)
    
    Returns:
        Dict with case details, loaded data info, and expected outcomes
    """
    import os
    import yaml
    
    # Load test cases from YAML
    yaml_path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "tests", "test_cases", "kk_setups.yaml"
    )
    yaml_path = os.path.normpath(yaml_path)
    
    if not os.path.exists(yaml_path):
        return {"error": f"Test cases file not found: {yaml_path}"}
    
    with open(yaml_path, 'r') as f:
        data = yaml.safe_load(f)
    
    # Find the test case
    test_cases = data.get("test_cases", [])
    case = None
    for tc in test_cases:
        if tc.get("id") == case_id:
            case = tc
            break
    
    if not case:
        available = [tc.get("id") for tc in test_cases]
        return {
            "error": f"Test case '{case_id}' not found",
            "available_cases": available,
        }
    
    # Load historical data for the symbol
    symbol = case["symbol"]
    start_date = case["date_range"]["start"]
    end_date = case["date_range"]["end"]
    
    from nexus2.adapters.market_data.fmp_adapter import get_fmp_adapter
    from nexus2.adapters.simulation import get_mock_market_data, get_simulation_clock
    
    fmp = get_fmp_adapter()
    market_data = get_mock_market_data()
    clock = get_simulation_clock()
    
    # Connect clock to data
    if market_data._sim_clock is None:
        market_data.set_clock(clock)
    
    # Calculate days needed
    from datetime import datetime
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    days = (end - start).days + 60  # Extra buffer
    
    # Fetch from FMP using date range (not limit) for historical backtesting
    logger.info(f"[TestCase] Loading historical data for {symbol} from {start_date} to {end_date}...")
    bars = fmp.get_daily_bars(symbol.upper(), from_date=start_date, to_date=end_date)
    
    if not bars:
        return {
            "error": f"Failed to load data for {symbol} (date range: {start_date} to {end_date})",
            "rate_stats": fmp.get_rate_stats()
        }
    
    # Convert and filter by date range
    bar_dicts = []
    for bar in bars:
        bar_date = bar.timestamp.strftime("%Y-%m-%d")
        if bar_date < start_date or bar_date > end_date:
            continue
        bar_dicts.append({
            "date": bar_date,
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": bar.volume,
        })
    
    # Load into MockMarketData
    count = market_data.load_data(symbol.upper(), bar_dicts)
    
    # Set clock to setup date if provided
    setup_date = case.get("setup_date", start_date)
    import pytz
    ET = pytz.timezone("US/Eastern")
    setup_dt = datetime.strptime(setup_date, "%Y-%m-%d")
    clock.set_time(ET.localize(setup_dt.replace(hour=9, minute=30)))
    
    logger.info(f"[TestCase] Loaded case '{case_id}': {symbol}, {count} bars, setup={setup_date}")
    
    return {
        "status": "loaded",
        "case_id": case_id,
        "symbol": symbol,
        "setup_type": case["setup_type"],
        "outcome": case["outcome"],
        "description": case["description"],
        "bars_loaded": count,
        "date_range": case["date_range"],
        "setup_date": case.get("setup_date"),
        "expected": case.get("expected", {}),
        "clock": clock.to_dict(),
        "rate_stats": fmp.get_rate_stats(),
    }


@router.get("/simulation/test_cases", response_model=dict)
async def list_test_cases():
    """List all available curated test cases."""
    import os
    import yaml
    
    yaml_path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "tests", "test_cases", "kk_setups.yaml"
    )
    yaml_path = os.path.normpath(yaml_path)
    
    if not os.path.exists(yaml_path):
        return {"error": f"Test cases file not found: {yaml_path}"}
    
    with open(yaml_path, 'r') as f:
        data = yaml.safe_load(f)
    
    test_cases = data.get("test_cases", [])
    
    summary = []
    for tc in test_cases:
        summary.append({
            "id": tc.get("id"),
            "symbol": tc.get("symbol"),
            "setup_type": tc.get("setup_type"),
            "outcome": tc.get("outcome"),
            "description": tc.get("description"),
        })
    
    return {
        "count": len(summary),
        "test_cases": summary,
    }
