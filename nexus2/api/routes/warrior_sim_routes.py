"""
Warrior Simulation Routes

Simulation endpoints for testing the Warrior Trading strategy with MockBroker.
Includes test case loading for historical scenario replay.
"""

import os
import threading
import yaml
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


# =============================================================================
# ROUTER
# =============================================================================

sim_router = APIRouter()  # No separate tag - inherits from parent 'warrior' router


# =============================================================================
# SIM BROKER STATE
# =============================================================================

_warrior_sim_broker = None
_warrior_sim_broker_lock = threading.Lock()


def get_warrior_sim_broker():
    """Get Warrior simulation broker (thread-safe)."""
    with _warrior_sim_broker_lock:
        return _warrior_sim_broker


def set_warrior_sim_broker(broker):
    """Set Warrior simulation broker (thread-safe)."""
    global _warrior_sim_broker
    with _warrior_sim_broker_lock:
        _warrior_sim_broker = broker


# =============================================================================
# REQUEST MODELS
# =============================================================================

class WarriorSimEnableRequest(BaseModel):
    """Request to enable Warrior simulation mode."""
    initial_cash: float = Field(25000.0, description="Starting cash for sim account")


class WarriorSimOrderRequest(BaseModel):
    """Request to submit a simulated order."""
    symbol: str
    shares: int
    stop_price: float
    limit_price: Optional[float] = None
    trigger_type: str = "manual"


# =============================================================================
# SIM STATUS ENDPOINT
# =============================================================================

@sim_router.get("/sim/status")
async def get_warrior_sim_status():
    """Get Warrior simulation status."""
    broker = get_warrior_sim_broker()
    
    if broker is None:
        return {
            "sim_enabled": False,
            "message": "Simulation not initialized. POST /warrior/sim/enable to start.",
        }
    
    account = broker.get_account()
    positions = broker.get_positions()
    orders = broker.get_orders()
    
    return {
        "sim_enabled": True,
        "account": {
            "cash": account["cash"],
            "portfolio_value": account["portfolio_value"],
            "unrealized_pnl": account["unrealized_pnl"],
            "realized_pnl": account["realized_pnl"],
        },
        "positions": positions,
        "position_count": len(positions),
        "orders": orders,
    }


# =============================================================================
# SIM ENABLE/DISABLE/RESET
# =============================================================================

@sim_router.post("/sim/enable")
async def enable_warrior_sim(request: WarriorSimEnableRequest = WarriorSimEnableRequest()):
    """Enable Warrior simulation mode with MockBroker."""
    from nexus2.adapters.simulation.mock_broker import MockBroker
    from .warrior_routes import get_engine
    
    broker = MockBroker(initial_cash=request.initial_cash)
    set_warrior_sim_broker(broker)
    
    # Configure engine for sim mode
    engine = get_engine()
    engine.config.sim_only = True
    engine.monitor.sim_mode = True
    
    # Wire up sim callbacks
    async def sim_submit_order(symbol: str, shares: int, side: str = "buy", order_type: str = "market", stop_loss: float = None, limit_price: float = None, trigger_type: str = "orb", exit_mode: str = None):
        sim_broker = get_warrior_sim_broker()
        if sim_broker is None:
            return None
        
        # Get sim_time from simulation clock for GUI display
        from nexus2.adapters.simulation import get_simulation_clock
        sim_clock = get_simulation_clock()
        sim_time = sim_clock.get_time_string() if sim_clock and sim_clock.current_time else None
        
        # Don't create broker-level hard stops in sim mode
        # Let the monitor handle all exits (mental stops, profit targets, etc.)
        # This properly tests the monitor exit logic
        result = sim_broker.submit_bracket_order(
            client_order_id=uuid4(),
            symbol=symbol,
            quantity=shares,
            stop_loss_price=None,  # Monitor controls exits, not broker stops
            limit_price=Decimal(str(limit_price)) if limit_price else None,
            exit_mode=exit_mode,
            sim_time=sim_time,
        )
        return result

    
    async def sim_get_quote(symbol: str):
        # Priority 1: Get price from MockBroker
        sim_broker = get_warrior_sim_broker()
        if sim_broker:
            price = sim_broker.get_price(symbol)
            if price is not None:
                return price
        
        # Priority 2: Get price from HistoricalBarLoader (for historical replay)
        # Do NOT fall back to Alpaca - that causes stale quote rejections
        from nexus2.adapters.simulation import get_historical_bar_loader, get_simulation_clock
        loader = get_historical_bar_loader()
        clock = get_simulation_clock()
        if loader and clock:
            time_str = clock.get_time_string()
            price = loader.get_price_at(symbol, time_str)
            if price:
                return price
        
        # No fallback to Alpaca in sim mode - return None
        return None
    
    async def sim_get_positions():
        sim_broker = get_warrior_sim_broker()
        return sim_broker.get_positions() if sim_broker else []
    
    async def sim_get_intraday_bars(symbol: str, timeframe: str = "1min", limit: int = 50):
        """Get intraday bars from MockMarketData for VWAP/EMA calculation."""
        from nexus2.adapters.simulation import get_mock_market_data
        mock_data = get_mock_market_data()
        
        # Get intraday bars from MockMarketData
        bars = mock_data.get_intraday_bars(symbol, timeframe, limit)
        return bars
    
    async def sim_execute_exit(signal):
        sim_broker = get_warrior_sim_broker()
        if sim_broker is None:
            print("[Sim] No broker for exit execution")
            return False
        
        # For FULL exits: sell ALL broker shares (prevents orphaned shares from multiple positions)
        # For PARTIAL exits: sell signal.shares_to_exit only
        from nexus2.domain.automation.warrior_types import WarriorExitReason
        is_partial = signal.reason == WarriorExitReason.PARTIAL_EXIT
        
        if is_partial:
            shares_to_sell = signal.shares_to_exit
        else:
            # FULL EXIT: Check broker position and sell ALL shares
            broker_position = sim_broker.get_position(signal.symbol)
            if broker_position:
                broker_shares = broker_position.get("qty", 0) or broker_position.get("shares", 0)
                if broker_shares > signal.shares_to_exit:
                    print(
                        f"[Sim] {signal.symbol}: Broker has {broker_shares} shares, "
                        f"signal has {signal.shares_to_exit} - selling ALL to prevent orphan"
                    )
                shares_to_sell = broker_shares if broker_shares > 0 else signal.shares_to_exit
            else:
                shares_to_sell = signal.shares_to_exit
        
        success = sim_broker.sell_position(signal.symbol, shares_to_sell)
        if success:
            print(f"[Sim] Executed exit: {signal.symbol} x{shares_to_sell} @ ${signal.exit_price}")
            from nexus2.domain.automation.trade_event_service import trade_event_service
            exit_reason = signal.reason.value if hasattr(signal.reason, 'value') else str(signal.reason)
            trade_event_service.log_warrior_exit(
                position_id=signal.position_id,
                symbol=signal.symbol,
                exit_price=signal.exit_price,
                exit_reason=exit_reason.lower(),
                pnl=signal.pnl_estimate if hasattr(signal, 'pnl_estimate') else None,
            )
        return success
    
    async def sim_update_stop(position_id: str, new_stop_price):
        sim_broker = get_warrior_sim_broker()
        if sim_broker is None:
            return False
        
        from nexus2.domain.automation.warrior_monitor import get_warrior_monitor
        monitor = get_warrior_monitor()
        symbol = None
        
        for pos in monitor.get_positions():
            if pos.position_id == position_id:
                symbol = pos.symbol
                break
        
        if not symbol:
            print(f"[Sim] Could not find symbol for position_id: {position_id[:8]}...")
            return False
        
        success = sim_broker.update_stop(symbol, float(new_stop_price))
        print(f"[Sim] Update stop: {symbol} -> ${new_stop_price} (success={success})")
        return success
    
    engine.set_callbacks(
        submit_order=sim_submit_order,
        get_quote=sim_get_quote,
        get_positions=sim_get_positions,
        get_intraday_bars=sim_get_intraday_bars,  # For VWAP/EMA dynamic scoring
    )
    
    from nexus2.domain.automation.warrior_monitor import get_warrior_monitor
    monitor = get_warrior_monitor()
    monitor.set_callbacks(
        get_price=sim_get_quote,
        execute_exit=sim_execute_exit,
        update_stop=sim_update_stop,
        submit_scale_order=sim_submit_order,
    )
    
    return {
        "status": "enabled",
        "initial_cash": request.initial_cash,
        "message": "Warrior simulation mode enabled with MockBroker",
    }


@sim_router.post("/sim/reset")
async def reset_warrior_sim(request: WarriorSimEnableRequest = WarriorSimEnableRequest()):
    """Reset Warrior simulation to initial state."""
    from nexus2.adapters.simulation.mock_broker import MockBroker
    from .warrior_routes import get_engine
    
    broker = MockBroker(initial_cash=request.initial_cash)
    set_warrior_sim_broker(broker)
    
    engine = get_engine()
    engine.stats.trades_today = 0
    engine.stats.pnl_today = Decimal("0")
    
    return {
        "status": "reset",
        "initial_cash": request.initial_cash,
        "message": "Warrior simulation reset to initial state",
    }


@sim_router.post("/sim/disable")
async def disable_warrior_sim():
    """Disable Warrior simulation mode."""
    from .warrior_routes import get_engine
    
    set_warrior_sim_broker(None)
    
    engine = get_engine()
    engine.config.sim_only = False
    engine.monitor.sim_mode = False
    
    return {
        "status": "disabled",
        "message": "Warrior simulation mode disabled",
    }


# =============================================================================
# SIM ORDER/PRICE ENDPOINTS
# =============================================================================

@sim_router.post("/sim/order")
async def submit_warrior_sim_order(request: WarriorSimOrderRequest):
    """Submit a simulated order to MockBroker."""
    broker = get_warrior_sim_broker()
    
    if broker is None:
        raise HTTPException(status_code=400, detail="Simulation not enabled.")
    
    current_price = broker.get_price(request.symbol)
    if current_price is None and request.limit_price:
        broker.set_price(request.symbol, request.limit_price)
    
    result = broker.submit_bracket_order(
        client_order_id=uuid4(),
        symbol=request.symbol,
        quantity=request.shares,
        stop_loss_price=request.stop_price,
        limit_price=Decimal(str(request.limit_price)) if request.limit_price else None,
    )
    
    is_filled = getattr(result, 'is_accepted', False) or getattr(result, 'filled_qty', 0) > 0
    fill_price = getattr(result, 'avg_fill_price', request.limit_price)
    
    if is_filled:
        from nexus2.domain.automation.trade_event_service import trade_event_service
        trade_event_service.log_warrior_entry(
            position_id=str(uuid4()),
            symbol=request.symbol,
            entry_price=float(fill_price) if fill_price else 0,
            stop_price=request.stop_price,
            shares=request.shares,
            trigger_type=request.trigger_type or "manual",
        )
    
    return {
        "status": "filled" if is_filled else "rejected",
        "symbol": request.symbol,
        "shares": request.shares,
        "fill_price": float(fill_price) if fill_price else None,
        "stop_price": request.stop_price,
    }


@sim_router.post("/sim/sell")
async def sell_warrior_sim_position(symbol: str, shares: Optional[int] = None):
    """Sell a simulated position."""
    broker = get_warrior_sim_broker()
    
    if broker is None:
        raise HTTPException(status_code=400, detail="Simulation not enabled.")
    
    sold = broker.sell_position(symbol, shares)
    
    if sold:
        return {"status": "sold", "symbol": symbol, "shares_sold": shares or "all"}
    else:
        raise HTTPException(status_code=404, detail=f"No position found for {symbol}")


@sim_router.put("/sim/price")
async def set_warrior_sim_price(symbol: str, price: float):
    """Set the current price for a symbol in simulation."""
    from .warrior_routes import get_engine
    
    broker = get_warrior_sim_broker()
    
    if broker is None:
        raise HTTPException(status_code=400, detail="Simulation not enabled.")
    
    broker.set_price(symbol, price)
    broker._check_stop_orders(symbol)
    
    from nexus2.domain.automation.warrior_monitor import get_warrior_monitor
    monitor = get_warrior_monitor()
    if monitor._running:
        await monitor._check_all_positions()
    
    return {"status": "updated", "symbol": symbol, "price": price}


# =============================================================================
# TEST CASE ENDPOINTS
# =============================================================================

@sim_router.get("/sim/test_cases")
async def list_warrior_test_cases():
    """List available Warrior test cases (YAML and JSON intraday files)."""
    import json
    
    base_path = os.path.join(os.path.dirname(__file__), "..", "..", "tests", "test_cases")
    summary = []
    json_symbols = set()  # Track symbols loaded from JSON to avoid duplicates
    
    # 1. First, scan intraday directory for JSON files (preferred - has bar data)
    intraday_path = os.path.join(base_path, "intraday")
    if os.path.exists(intraday_path):
        for filename in os.listdir(intraday_path):
            if filename.endswith(".json"):
                json_path = os.path.join(intraday_path, filename)
                try:
                    with open(json_path, "r") as f:
                        tc_data = json.load(f)
                    
                    # Extract info from JSON test case
                    symbol = tc_data.get("symbol", filename.replace(".json", "").upper())
                    json_symbols.add(symbol)  # Track for duplicate filtering
                    date = tc_data.get("date", "")
                    premarket = tc_data.get("premarket", {})
                    catalyst = premarket.get("catalyst", "")
                    gap_pct = premarket.get("gap_percent", 0)
                    bar_count = len(tc_data.get("bars", []))
                    
                    # Create description from available data
                    description = f"{date} - {catalyst}" if catalyst else date
                    if bar_count > 0:
                        description += f" ({bar_count} bars)"
                    
                    # Use filename without extension as ID
                    case_id = filename.replace(".json", "")
                    
                    summary.append({
                        "id": case_id,
                        "symbol": symbol,
                        "setup_type": "historical_replay",
                        "outcome": "real_data",
                        "description": description,
                        "trade_date": date,
                        "synthetic": False,
                        "has_bars": bar_count > 0,
                        "gap_percent": gap_pct,
                    })
                except Exception as e:
                    print(f"[Test Cases] Error loading {filename}: {e}")
    
    # 2. Load from YAML file (legacy format) - skip entries that have JSON equivalent
    yaml_path = os.path.join(base_path, "warrior_setups.yaml")
    if os.path.exists(yaml_path):
        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f)
        
        for tc in data.get("test_cases", []):
            symbol = tc.get("symbol")
            # Skip if we already have this symbol from JSON files
            if symbol in json_symbols:
                continue
            summary.append({
                "id": tc.get("id"),
                "symbol": symbol,
                "setup_type": tc.get("setup_type"),
                "outcome": tc.get("outcome"),
                "description": tc.get("description"),
                "trade_date": tc.get("trade_date"),
                "synthetic": tc.get("synthetic", False),
            })
    
    # Sort by date (most recent first), then by symbol
    summary.sort(key=lambda x: (x.get("trade_date", "") or "", x.get("symbol", "")), reverse=True)
    
    return {"test_cases": summary, "count": len(summary)}


@sim_router.post("/sim/load_test_case")
async def load_warrior_test_case(case_id: str):
    """Load a Warrior test case into the MockBroker."""
    from .warrior_routes import get_engine
    from nexus2.domain.scanner.warrior_scanner_service import get_warrior_scanner_service
    from nexus2.domain.automation.warrior_engine import WatchedCandidate
    from nexus2.domain.scanner.warrior_scanner_service import WarriorCandidate
    
    yaml_path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "tests", "test_cases", "warrior_setups.yaml"
    )
    
    if not os.path.exists(yaml_path):
        raise HTTPException(status_code=404, detail="Test cases file not found")
    
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)
    
    test_cases = data.get("test_cases", [])
    
    case = None
    for tc in test_cases:
        if tc.get("id") == case_id:
            case = tc
            break
    
    if case is None:
        available = [tc.get("id") for tc in test_cases]
        raise HTTPException(status_code=404, detail=f"Test case '{case_id}' not found. Available: {available}")
    
    broker = get_warrior_sim_broker()
    if broker is None:
        from nexus2.adapters.simulation.mock_broker import MockBroker
        broker = MockBroker(initial_cash=25000.0)
        set_warrior_sim_broker(broker)
    
    premarket = case.get("premarket_data", {})
    expected = case.get("expected", {})
    symbol = case.get("symbol")
    entry_price = expected.get("entry_near")
    
    if entry_price:
        broker.set_price(symbol, entry_price)
        
        # Load synthetic data into MockMarketData for VWAP/EMA calculation
        from nexus2.adapters.simulation import get_mock_market_data
        mock_data = get_mock_market_data()
        mock_data.load_synthetic_data(
            symbol=symbol,
            start_price=entry_price * 0.9,  # Start 10% lower
            days=30,  # 30 days of history
            volatility=0.03,  # 3% daily volatility
            trend=0.005,  # Slight uptrend
        )
        print(f"[Mock Market] Loaded synthetic data for {symbol} (price=${entry_price:.2f})")
    
    scanner = get_warrior_scanner_service()
    gap_pct = premarket.get("gap_percent", 0)
    prev_close = premarket.get("previous_close", 1.0)
    current_price = prev_close * (1 + gap_pct / 100) if prev_close else entry_price
    
    candidate = scanner._evaluate_symbol(
        symbol=symbol,
        name=symbol,
        price=Decimal(str(current_price)) if current_price else Decimal("0"),
        change_percent=Decimal(str(gap_pct)),
    )
    
    scanner_result = "PASSED" if candidate else "REJECTED"
    scanner_score = candidate.quality_score if candidate else None
    
    if not candidate:
        candidate = WarriorCandidate(
            symbol=symbol,
            name=symbol,
            price=Decimal(str(current_price)) if current_price else Decimal("0"),
            gap_percent=Decimal(str(gap_pct)),
            relative_volume=Decimal("10.0"),
            float_shares=None,
            catalyst_type=premarket.get("catalyst", "news"),
            catalyst_description=case.get("description", "Mock Market test"),
            is_ideal_float=True,
            is_ideal_rvol=True,
            is_ideal_gap=True,
            session_high=Decimal(str(premarket.get("premarket_high", 0))),
            session_low=Decimal(str(prev_close)),
        )
    
    pmh = Decimal(str(premarket.get("premarket_high", entry_price or current_price)))
    
    watched = WatchedCandidate(candidate=candidate, pmh=pmh)
    
    engine = get_engine()
    engine._watchlist[symbol] = watched
    
    print(f"[Mock Market] Added {symbol} to watchlist: gap={gap_pct}%, PMH=${pmh} (scanner: {scanner_result})")
    
    return {
        "status": "loaded",
        "case_id": case_id,
        "symbol": symbol,
        "setup_type": case.get("setup_type"),
        "description": case.get("description"),
        "trade_date": case.get("trade_date"),
        "premarket_data": premarket,
        "expected": expected,
        "scanner_result": scanner_result,
        "scanner_score": scanner_score,
        "current_sim_price": entry_price,
        "synthetic": case.get("synthetic", False),
        "added_to_watchlist": candidate is not None,
    }


# =============================================================================
# HISTORICAL REPLAY ENDPOINTS
# =============================================================================

@sim_router.post("/sim/load_historical")
async def load_historical_test_case(case_id: str):
    """
    Load a historical test case with intraday bar data.
    
    Sets the simulation clock to 9:30 AM, loads real intraday bars,
    and adds the symbol to the watchlist so the engine can take trades.
    """
    from nexus2.adapters.simulation import (
        get_historical_bar_loader,
        get_simulation_clock,
        reset_simulation_clock
    )
    from nexus2.domain.automation.warrior_engine import WatchedCandidate
    from nexus2.domain.scanner.warrior_scanner_service import WarriorCandidate
    from datetime import datetime
    from decimal import Decimal
    import pytz
    
    from nexus2.api.routes.warrior_routes import get_engine
    
    loader = get_historical_bar_loader()
    loader.reset()  # Clear previous test case data (LCFY bars before loading PAVM)
    data = loader.load_test_case(case_id)
    
    if data is None:
        raise HTTPException(status_code=404, detail=f"Test case '{case_id}' not found")
    
    # Parse date and set clock to first bar's time (supports pre-market)
    ET = pytz.timezone("US/Eastern")
    trade_date = datetime.strptime(data.date, "%Y-%m-%d")
    
    # Use first bar's time if available, otherwise default to 9:30 AM
    if data.bars:
        first_bar_time = data.bars[0].time  # e.g. "07:56"
        hour, minute = map(int, first_bar_time.split(":"))
        start_time = ET.localize(trade_date.replace(hour=hour, minute=minute, second=0))
    else:
        start_time = ET.localize(trade_date.replace(hour=9, minute=30, second=0))
    
    clock = reset_simulation_clock(start_time=start_time)
    
    # Ensure sim broker exists
    broker = get_warrior_sim_broker()
    if broker is None:
        from nexus2.adapters.simulation.mock_broker import MockBroker
        broker = MockBroker(initial_cash=25000.0)
        set_warrior_sim_broker(broker)
    
    # Reset broker state when loading new test case (clears previous orders/positions)
    broker.reset()
    
    # Set up MockMarketData with the clock
    from nexus2.adapters.simulation import get_mock_market_data
    mock_data = get_mock_market_data()
    mock_data.reset()  # Clear previous test case data (LCFY prices when loading PAVM)
    mock_data.set_clock(clock)
    
    # Set initial price from first bar
    symbol = data.symbol
    entry_price = data.bars[0].open if data.bars else 10.0
    broker.set_price(symbol, entry_price)
    
    # Load historical bars from test case for VWAP/EMA calculation
    # Previously used synthetic data which gave wrong VWAP values
    # Now we convert the test case's intraday bars to daily format for historical data
    if data.bars:
        # Convert intraday bars (t/o/h/l/c/v format) to daily bars for mock market data
        # Group bars by date and aggregate to daily OHLCV
        date_str = data.date  # e.g., "2026-01-16"
        daily_bars = [{
            "date": date_str,
            "open": float(data.bars[0].open),
            "high": max(b.high for b in data.bars),
            "low": min(b.low for b in data.bars),
            "close": float(data.bars[-1].close),
            "volume": sum(b.volume for b in data.bars)
        }]
        mock_data.load_data(symbol, daily_bars)
        print(f"[Historical Replay] Loaded real historical data: {len(daily_bars)} daily bars for {symbol}")
    
    # Extract premarket data
    premarket = data.premarket
    gap_pct = premarket.get("gap_percent", 25.0)
    pmh = Decimal(str(premarket.get("pmh", entry_price)))
    prev_close = premarket.get("previous_close", entry_price * 0.8)
    
    # Catalyst date for freshness scoring
    # If specified in YAML, use it. Otherwise default to market open (9:30 AM on trade date)
    catalyst_date_str = premarket.get("catalyst_date")
    if catalyst_date_str:
        # Parse explicit catalyst date from YAML (format: "2026-01-17 08:00")
        try:
            catalyst_date = ET.localize(datetime.strptime(catalyst_date_str, "%Y-%m-%d %H:%M"))
        except ValueError:
            # Try date-only format
            catalyst_date = ET.localize(datetime.strptime(catalyst_date_str, "%Y-%m-%d").replace(hour=9, minute=30))
    else:
        # Default to market open for backwards compatibility
        catalyst_date = ET.localize(trade_date.replace(hour=9, minute=30, second=0))
    
    # Create a WatchedCandidate and add to watchlist
    candidate = WarriorCandidate(
        symbol=symbol,
        name=symbol,
        price=Decimal(str(entry_price)),
        gap_percent=Decimal(str(gap_pct)),
        relative_volume=Decimal("10.0"),
        float_shares=premarket.get("float_shares"),
        catalyst_type=premarket.get("catalyst", "news"),
        catalyst_description=premarket.get("catalyst_description", f"Historical replay: {case_id}"),
        catalyst_date=catalyst_date,  # For freshness scoring
        is_ideal_float=True,
        is_ideal_rvol=True,
        is_ideal_gap=True,
        session_high=pmh,
        session_low=Decimal(str(prev_close)),
    )
    
    watched = WatchedCandidate(candidate=candidate, pmh=pmh)
    
    engine = get_engine()
    added_to_watchlist = False
    if engine:
        # FRESH START: Clear all watchlist entries and pending entries when loading new test case
        # This prevents old symbols (e.g., PAVM) from trading when loading a new case (e.g., LCFY)
        engine._watchlist.clear()
        engine._pending_entries.clear()
        print(f"[Historical Replay] Cleared watchlist and pending entries for fresh start")
        
        # Reset the watched candidate (fresh state)
        watched.entry_triggered = False
        
        engine._watchlist[symbol] = watched
        added_to_watchlist = True
        print(f"[Historical Replay] Added {symbol} to watchlist: PMH=${pmh}, gap={gap_pct}%, {len(data.bars)} bars loaded")
        
        # =========================================================================
        # Re-wire monitor callbacks to use MockBroker for historical replay
        # Without this, monitor evaluates positions against LIVE Alpaca prices
        # =========================================================================
        engine.monitor.sim_mode = True
        
        async def sim_get_price(symbol: str):
            sim_broker = get_warrior_sim_broker()
            if sim_broker:
                price = sim_broker.get_price(symbol)
                if price is not None:
                    return price
            return None
        
        async def sim_get_prices_batch(symbols):
            sim_broker = get_warrior_sim_broker()
            result = {}
            for s in symbols:
                if sim_broker:
                    price = sim_broker.get_price(s)
                    if price:
                        result[s] = price
            return result
        
        async def sim_execute_exit(signal):
            sim_broker = get_warrior_sim_broker()
            if sim_broker is None:
                print("[Historical Replay] No broker for exit execution")
                return False
            
            # For FULL exits: sell ALL broker shares (prevents orphaned shares)
            from nexus2.domain.automation.warrior_types import WarriorExitReason
            is_partial = signal.reason == WarriorExitReason.PARTIAL_EXIT
            
            if is_partial:
                shares_to_sell = signal.shares_to_exit
            else:
                # FULL EXIT: Check broker position and sell ALL shares
                broker_position = sim_broker.get_position(signal.symbol)
                if broker_position:
                    broker_shares = broker_position.get("qty", 0) or broker_position.get("shares", 0)
                    if broker_shares > signal.shares_to_exit:
                        print(
                            f"[Historical Replay] {signal.symbol}: Broker has {broker_shares} shares, "
                            f"signal has {signal.shares_to_exit} - selling ALL"
                        )
                    shares_to_sell = broker_shares if broker_shares > 0 else signal.shares_to_exit
                else:
                    shares_to_sell = signal.shares_to_exit
            
            success = sim_broker.sell_position(signal.symbol, shares_to_sell)
            if success:
                print(f"[Historical Replay] EXIT: {signal.symbol} x{shares_to_sell} @ ${signal.exit_price}")
            return success
        
        async def sim_update_stop(position_id: str, new_stop_price):
            """Update stop in MockBroker for historical replay."""
            sim_broker = get_warrior_sim_broker()
            if sim_broker is None:
                return False
            
            # Find symbol from position_id
            symbol = None
            for pos in engine.monitor.get_positions():
                if pos.position_id == position_id:
                    symbol = pos.symbol
                    break
            
            if not symbol:
                print(f"[Historical Replay] Could not find symbol for position {position_id[:8]}...")
                return False
            
            success = sim_broker.update_stop(symbol, float(new_stop_price))
            if success:
                print(f"[Historical Replay] Updated stop: {symbol} -> ${new_stop_price:.2f}")
            return success
        
        engine.monitor.set_callbacks(
            get_price=sim_get_price,
            get_prices_batch=sim_get_prices_batch,
            execute_exit=sim_execute_exit,
            update_stop=sim_update_stop,
        )
        
        # Wire _get_intraday_bars to use historical bar loader at simulated time
        # Without this, entry stop calculation uses real (stale) bars instead of simulated-time bars
        async def sim_get_intraday_bars(symbol: str, timeframe: str = "1min", limit: int = 50):
            """Return historical bars up to current simulated time."""
            loader = get_historical_bar_loader()
            time_str = clock.get_time_string()
            bars = loader.get_bars_up_to(symbol, time_str, timeframe)
            # Return last N bars per limit
            if bars and len(bars) > limit:
                bars = bars[-limit:]
            return bars
        
        engine._get_intraday_bars = sim_get_intraday_bars

        # Wire _get_quote to use historical bar loader at simulated time
        # This is CRITICAL - entry logic at warrior_engine_entry.py:53 uses engine._get_quote
        # Without this, it falls back to Alpaca which causes stale quote rejections
        async def sim_get_quote_historical(symbol: str):
            """Return price from historical bar loader at current simulated time."""
            loader = get_historical_bar_loader()
            time_str = clock.get_time_string()
            price = loader.get_price_at(symbol, time_str)
            if price:
                return price
            # Fallback to broker price if loader doesn't have it
            sim_broker = get_warrior_sim_broker()
            if sim_broker:
                return sim_broker.get_price(symbol)
            return None
        
        engine._get_quote = sim_get_quote_historical

        # Wire _submit_order to use MockBroker for historical replay
        # This is CRITICAL - Alpaca broker callbacks are set on server startup and OVERWRITE sim callbacks
        # Without this, orders go to real Alpaca broker instead of MockBroker
        async def sim_submit_order_historical(
            symbol: str, shares: int, side: str = "buy", order_type: str = "market",
            stop_loss: float = None, limit_price: float = None, trigger_type: str = "orb",
            exit_mode: str = None, **kwargs
        ):
            """Submit order through MockBroker for historical replay."""
            sim_broker = get_warrior_sim_broker()
            if sim_broker is None:
                print(f"[Historical Replay] No MockBroker for order submission")
                return None
            
            from decimal import Decimal
            from uuid import uuid4
            
            # Get sim_time for order tracking
            sim_time = clock.get_time_string() if clock and clock.current_time else None
            
            result = sim_broker.submit_bracket_order(
                client_order_id=uuid4(),
                symbol=symbol,
                quantity=shares,
                stop_loss_price=None,  # Monitor controls exits
                limit_price=Decimal(str(limit_price)) if limit_price else None,
                exit_mode=exit_mode,
                sim_time=sim_time,
            )
            
            if result:
                print(f"[Historical Replay] MockBroker order: {symbol} x{shares} @ ${limit_price} ({side})")
            return result
        
        engine._submit_order = sim_submit_order_historical

        # Disable live Alpaca order status polling during replay
        # MockBroker fills are instantaneous, no need to poll
        engine._get_order_status = None
        print(f"[Historical Replay] Engine + Monitor callbacks re-wired to MockBroker")
    else:
        print(f"[Historical Replay] Engine not initialized, cannot add to watchlist")
    
    return {
        "status": "loaded",
        "case_id": case_id,
        "symbol": data.symbol,
        "date": data.date,
        "bar_count": len(data.bars),
        "premarket": data.premarket,
        "clock": clock.to_dict(),
        "added_to_watchlist": added_to_watchlist,
    }


@sim_router.post("/sim/step")
async def step_clock(minutes: int = 1):
    """
    Step the simulation clock forward by specified minutes.
    
    Also updates the mock price based on historical bar data
    and triggers entry checks if engine is running.
    """
    from nexus2.adapters.simulation import (
        get_simulation_clock,
        get_historical_bar_loader,
    )
    from nexus2.domain.automation.warrior_engine_entry import check_entry_triggers
    from nexus2.api.routes.warrior_routes import get_engine
    
    clock = get_simulation_clock()
    loader = get_historical_bar_loader()
    
    # Step forward
    clock.step_forward(minutes)
    time_str = clock.get_time_string()
    
    # Update prices for all loaded symbols
    broker = get_warrior_sim_broker()
    prices = {}
    
    for symbol in loader.get_loaded_symbols():
        price = loader.get_price_at(symbol, time_str)
        if price and broker:
            broker.set_price(symbol, price)
            prices[symbol] = price
    
    # DEBUG: Log step info
    print(f"[Historical Replay] Step to {time_str}, prices: {prices}")
    
    # Trigger entry check if engine is running with sim mode
    engine = get_engine()
    entry_triggered = None
    # Check engine state - handle both enum and string values
    engine_state_str = engine.state.value if hasattr(engine.state, 'value') else str(engine.state) if engine else None
    if engine and engine_state_str in ("running", "premarket"):
        print(f"[Historical Replay] Engine state: {engine_state_str}, checking entry triggers...")
        try:
            await check_entry_triggers(engine)
            # Check if any entry was triggered for the symbols
            for symbol in loader.get_loaded_symbols():
                if symbol in engine._watchlist:
                    watched = engine._watchlist[symbol]
                    print(f"[Historical Replay] {symbol}: entry_triggered={watched.entry_triggered}, pmh={watched.pmh}")
                    if watched.entry_triggered:
                        entry_triggered = {
                            "symbol": symbol,
                            "pmh": str(watched.pmh),
                            "trigger_time": time_str,
                        }
        except Exception as e:
            print(f"[Historical Replay] Entry check error: {e}")
    else:
        print(f"[Historical Replay] Engine not ready: engine={engine}, state={engine.state if engine else 'N/A'}")
    
    # =========================================================================
    # MONITOR TICK: Check positions for exits, scaling, and profit targets
    # =========================================================================
    if engine and engine.monitor and engine.monitor._positions:
        try:
            # Ensure batch price callback is available for monitor
            if not engine.monitor._get_prices_batch:
                async def sim_get_prices_batch(symbols):
                    result = {}
                    for s in symbols:
                        if broker:
                            price = broker.get_price(s)
                            if price:
                                result[s] = price
                    return result
                engine.monitor._get_prices_batch = sim_get_prices_batch
            
            await engine.monitor._check_all_positions()
            print(f"[Historical Replay] Monitor tick complete - {len(engine.monitor._positions)} positions checked")
        except Exception as e:
            print(f"[Historical Replay] Monitor check error: {e}")
    
    # Get orders for GUI
    orders = []
    if broker:
        orders = broker.get_orders()
    
    return {
        "status": "stepped",
        "minutes": minutes,
        "clock": clock.to_dict(),
        "prices": prices,
        "entry_triggered": entry_triggered,
        "orders": orders,
    }


@sim_router.get("/sim/orders")
async def get_sim_orders():
    """
    Get all MockBroker orders for GUI visibility.
    
    Returns orders with their current status (PENDING, FILLED, CANCELLED).
    """
    broker = get_warrior_sim_broker()
    if broker is None:
        return {"orders": [], "error": "MockBroker not available"}
    
    return {
        "orders": broker.get_orders(),
        "positions": broker.get_positions(),
        "account": broker.get_account(),
    }


@sim_router.post("/sim/step_back")
async def step_clock_back(minutes: int = 1):
    """Step the simulation clock backward by specified minutes."""
    from nexus2.adapters.simulation import (
        get_simulation_clock,
        get_historical_bar_loader,
    )
    
    clock = get_simulation_clock()
    loader = get_historical_bar_loader()
    
    # Step backward
    clock.step_back(minutes)
    time_str = clock.get_time_string()
    
    # Update prices for all loaded symbols
    broker = get_warrior_sim_broker()
    prices = {}
    
    for symbol in loader.get_loaded_symbols():
        price = loader.get_price_at(symbol, time_str)
        if price and broker:
            broker.set_price(symbol, price)
            prices[symbol] = price
    
    return {
        "status": "stepped_back",
        "minutes": minutes,
        "clock": clock.to_dict(),
        "prices": prices,
    }


@sim_router.post("/sim/reset_clock")
async def reset_clock_to_open():
    """Reset the simulation clock to market open (9:30 AM)."""
    from nexus2.adapters.simulation import (
        get_simulation_clock,
        get_historical_bar_loader,
    )
    
    clock = get_simulation_clock()
    loader = get_historical_bar_loader()
    
    # Reset to market open
    clock.reset_to_market_open()
    time_str = clock.get_time_string()
    
    # Update prices to opening prices
    broker = get_warrior_sim_broker()
    prices = {}
    
    for symbol in loader.get_loaded_symbols():
        price = loader.get_price_at(symbol, time_str)
        if price and broker:
            broker.set_price(symbol, price)
            prices[symbol] = price
    
    return {
        "status": "reset",
        "clock": clock.to_dict(),
        "prices": prices,
    }


@sim_router.post("/sim/speed")
async def set_playback_speed(speed: float = 1.0):
    """
    Set the playback speed for auto-advance.
    
    Args:
        speed: Speed multiplier (1.0, 2.0, 5.0, 10.0)
    """
    from nexus2.adapters.simulation import get_simulation_clock
    
    if speed not in [1.0, 2.0, 5.0, 10.0]:
        raise HTTPException(status_code=400, detail="Speed must be 1, 2, 5, or 10")
    
    clock = get_simulation_clock()
    clock.set_playback_speed(speed)
    
    return {
        "status": "speed_set",
        "speed": speed,
        "clock": clock.to_dict(),
    }


@sim_router.get("/sim/clock")
async def get_clock_status():
    """Get current simulation clock status."""
    from nexus2.adapters.simulation import (
        get_simulation_clock,
        get_historical_bar_loader,
    )
    
    clock = get_simulation_clock()
    loader = get_historical_bar_loader()
    
    # Get current prices
    broker = get_warrior_sim_broker()
    time_str = clock.get_time_string()
    
    prices = {}
    for symbol in loader.get_loaded_symbols():
        price = loader.get_price_at(symbol, time_str)
        if price:
            prices[symbol] = price
    
    return {
        "clock": clock.to_dict(),
        "loader": loader.to_dict(),
        "prices": prices,
        "sim_enabled": broker is not None,
    }


@sim_router.get("/exit-mode")
async def get_exit_mode():
    """Get current exit mode (base_hit or home_run)."""
    from nexus2.api.routes.warrior_routes import get_engine
    
    engine = get_engine()
    if not engine:
        return {"exit_mode": "unknown", "error": "Engine not initialized"}
    
    return {
        "exit_mode": engine.monitor.settings.session_exit_mode,
        "options": ["base_hit", "home_run"],
    }


@sim_router.post("/exit-mode")
async def set_exit_mode(mode: str = "base_hit"):
    """
    Set exit mode for the session.
    
    Args:
        mode: "base_hit" (quick +18¢ profit) or "home_run" (trail stop, let winners run)
    """
    from nexus2.api.routes.warrior_routes import get_engine
    
    if mode not in ("base_hit", "home_run"):
        raise HTTPException(status_code=400, detail=f"Invalid mode: {mode}. Use 'base_hit' or 'home_run'")
    
    engine = get_engine()
    if not engine:
        raise HTTPException(status_code=400, detail="Engine not initialized")
    
    old_mode = engine.monitor.settings.session_exit_mode
    engine.monitor.settings.session_exit_mode = mode
    
    print(f"[Warrior] Exit mode changed: {old_mode} → {mode}")
    
    return {
        "success": True,
        "old_mode": old_mode,
        "new_mode": mode,
    }
