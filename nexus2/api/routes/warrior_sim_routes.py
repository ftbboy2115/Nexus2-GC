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

sim_router = APIRouter(tags=["warrior-sim"])


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
    async def sim_submit_order(symbol: str, shares: int, side: str = "buy", order_type: str = "market", stop_loss: float = None, limit_price: float = None, trigger_type: str = "orb"):
        sim_broker = get_warrior_sim_broker()
        if sim_broker is None:
            return None
        
        result = sim_broker.submit_bracket_order(
            client_order_id=uuid4(),
            symbol=symbol,
            quantity=shares,
            stop_loss_price=stop_loss,
            limit_price=Decimal(str(limit_price)) if limit_price else None,
        )
        return result
    
    async def sim_get_quote(symbol: str):
        sim_broker = get_warrior_sim_broker()
        if sim_broker:
            price = sim_broker.get_price(symbol)
            if price is not None:
                return price
        
        from nexus2.adapters.market_data.unified import UnifiedMarketData
        umd = UnifiedMarketData()
        quote = umd.get_quote(symbol)
        return float(quote.price) if quote else None
    
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
        
        success = sim_broker.sell_position(signal.symbol, signal.shares_to_exit)
        if success:
            print(f"[Sim] Executed exit: {signal.symbol} x{signal.shares_to_exit} @ ${signal.exit_price}")
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
    """List available Warrior test cases."""
    yaml_path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "tests", "test_cases", "warrior_setups.yaml"
    )
    
    if not os.path.exists(yaml_path):
        return {"test_cases": [], "message": "No test cases file found"}
    
    with open(yaml_path, "r") as f:
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
            "trade_date": tc.get("trade_date"),
            "synthetic": tc.get("synthetic", False),
        })
    
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
    data = loader.load_test_case(case_id)
    
    if data is None:
        raise HTTPException(status_code=404, detail=f"Test case '{case_id}' not found")
    
    # Parse date and set clock to 9:30 AM on that date
    ET = pytz.timezone("US/Eastern")
    trade_date = datetime.strptime(data.date, "%Y-%m-%d")
    market_open = ET.localize(trade_date.replace(hour=9, minute=30, second=0))
    
    clock = reset_simulation_clock(start_time=market_open)
    
    # Ensure sim broker exists
    broker = get_warrior_sim_broker()
    if broker is None:
        from nexus2.adapters.simulation.mock_broker import MockBroker
        broker = MockBroker(initial_cash=25000.0)
        set_warrior_sim_broker(broker)
    
    # Set up MockMarketData with the clock
    from nexus2.adapters.simulation import get_mock_market_data
    mock_data = get_mock_market_data()
    mock_data.set_clock(clock)
    
    # Set initial price from first bar
    symbol = data.symbol
    entry_price = data.bars[0].open if data.bars else 10.0
    broker.set_price(symbol, entry_price)
    
    # Load synthetic historical data for VWAP/EMA calculation
    mock_data.load_synthetic_data(
        symbol=symbol,
        start_price=entry_price * 0.9,
        days=30,
        volatility=0.03,
        trend=0.005,
    )
    
    # Extract premarket data
    premarket = data.premarket
    gap_pct = premarket.get("gap_percent", 25.0)
    pmh = Decimal(str(premarket.get("pmh", entry_price)))
    prev_close = premarket.get("previous_close", entry_price * 0.8)
    
    # Create a WatchedCandidate and add to watchlist
    candidate = WarriorCandidate(
        symbol=symbol,
        name=symbol,
        price=Decimal(str(entry_price)),
        gap_percent=Decimal(str(gap_pct)),
        relative_volume=Decimal("10.0"),
        float_shares=premarket.get("float_shares"),
        catalyst_type=premarket.get("catalyst", "news"),
        catalyst_description=f"Historical replay: {case_id}",
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
        engine._watchlist[symbol] = watched
        added_to_watchlist = True
        print(f"[Historical Replay] Added {symbol} to watchlist: PMH=${pmh}, gap={gap_pct}%, {len(data.bars)} bars loaded")
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
    
    # Trigger entry check if engine is running with sim mode
    engine = get_engine()
    entry_triggered = None
    if engine and engine._state in ("running", "premarket"):
        try:
            await check_entry_triggers(engine)
            # Check if any entry was triggered for the symbols
            for symbol in loader.get_loaded_symbols():
                if symbol in engine._watchlist:
                    watched = engine._watchlist[symbol]
                    if watched.entry_triggered:
                        entry_triggered = {
                            "symbol": symbol,
                            "pmh": str(watched.pmh),
                            "trigger_time": time_str,
                        }
        except Exception as e:
            print(f"[Historical Replay] Entry check error: {e}")
    
    return {
        "status": "stepped",
        "minutes": minutes,
        "clock": clock.to_dict(),
        "prices": prices,
        "entry_triggered": entry_triggered,
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

