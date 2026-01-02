"""
Simulation Routes

API endpoints for controlling the mock trading simulation environment.
Extracted from automation.py for maintainability.
"""

from fastapi import APIRouter
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
    from nexus2.adapters.simulation.mock_broker import MockBroker
    
    clock = get_simulation_clock()
    data = get_mock_market_data()
    
    # Get global mock broker if exists
    broker_state = None
    if hasattr(get_simulation_status, '_mock_broker'):
        broker = get_simulation_status._mock_broker
        broker_state = broker.to_dict()
    
    return {
        "clock": clock.to_dict(),
        "market_data": data.to_dict(),
        "broker": broker_state,
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
    
    # Create mock broker
    broker = MockBroker(initial_cash=initial_cash)
    get_simulation_status._mock_broker = broker
    
    # Set initial prices from loaded data
    for sym in data.get_symbols():
        price = data.get_current_price(sym)
        if price:
            broker.set_price(sym, price)
    
    logger.info(f"[Simulation] Reset: start={start_dt}, cash=${initial_cash:,.0f}, symbols={symbols}")
    
    return {
        "status": "reset",
        "clock": clock.to_dict(),
        "market_data": data.to_dict(),
        "broker": broker.to_dict(),
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
    
    # Create scanners with MockMarketData
    ep_scanner = EPScannerService(settings=sim_ep_settings, market_data=data)
    breakout_scanner = BreakoutScannerService(market_data=data)
    htf_scanner = HTFScannerService(market_data=data)
    
    # Use same settings as force_scan
    settings = UnifiedScanSettings(
        modes=[ScanMode.EP_ONLY, ScanMode.BREAKOUT_ONLY, ScanMode.HTF_ONLY],
        min_quality_score=5,  # Relaxed for sim
        stop_mode="atr",
        max_stop_atr=1.5,
        max_stop_percent=8.0,
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
    
    # Update broker prices if exists
    if hasattr(get_simulation_status, '_mock_broker'):
        broker = get_simulation_status._mock_broker
        for sym, price in new_prices.items():
            broker.set_price(sym, price)
    
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
    if hasattr(get_simulation_status, '_mock_broker'):
        broker = get_simulation_status._mock_broker
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
    # Scanner needs ~20 bars of history, so set clock 30+ bars into the data
    if bar_dicts:
        from datetime import datetime
        import pytz
        ET = pytz.timezone("US/Eastern")
        
        # Use bar at position 30 (or last if fewer bars) for enough lookback
        target_idx = min(30, len(bar_dicts) - 1)
        target_date_str = bar_dicts[target_idx]["date"]
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d")
        clock.set_time(ET.localize(target_date.replace(hour=9, minute=30)))
        
        logger.info(f"[Simulation] Clock set to {target_date_str} (bar {target_idx + 1} of {len(bar_dicts)})")
    
    # Update broker price if exists
    if hasattr(get_simulation_status, '_mock_broker') and bar_dicts:
        broker = get_simulation_status._mock_broker
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
    
    # Fetch from FMP
    logger.info(f"[TestCase] Loading {days} days of historical data for {symbol}...")
    bars = fmp.get_daily_bars(symbol.upper(), limit=days)
    
    if not bars:
        return {
            "error": f"Failed to load data for {symbol}",
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
