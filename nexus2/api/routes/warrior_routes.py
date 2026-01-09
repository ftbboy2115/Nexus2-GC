"""
Warrior Trading Routes

API endpoints for controlling the Warrior Trading automation engine.
Separate from KK-style automation routes.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from decimal import Decimal

from nexus2.domain.automation.warrior_engine import (
    WarriorEngine,
    WarriorEngineConfig,
    get_warrior_engine,
)
from nexus2.domain.scanner.warrior_scanner_service import (
    WarriorScannerService,
    WarriorScanSettings,
    get_warrior_scanner_service,
)


router = APIRouter(prefix="/warrior", tags=["warrior"])


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class WarriorStartRequest(BaseModel):
    """Request to start Warrior engine."""
    sim_only: bool = True
    risk_per_trade: float = 100.0
    max_positions: int = 3
    max_candidates: int = 5  # How many candidates to watch for breakouts


class WarriorScannerSettingsRequest(BaseModel):
    """Request to update scanner settings."""
    max_float: Optional[int] = Field(None, description="Max float shares (default 100M)")
    min_rvol: Optional[float] = Field(None, description="Min relative volume (default 2.0)")
    min_gap: Optional[float] = Field(None, description="Min gap % (default 4.0)")
    min_price: Optional[float] = Field(None, description="Min price (default $1.50)")
    max_price: Optional[float] = Field(None, description="Max price (default $20)")
    require_catalyst: Optional[bool] = Field(None, description="Require news/earnings")


class WarriorMonitorSettingsRequest(BaseModel):
    """Request to update monitor settings."""
    mental_stop_cents: Optional[float] = Field(None, description="Mental stop in cents (default 15)")
    profit_target_r: Optional[float] = Field(None, description="Profit target R multiple (default 2.0)")
    profit_target_cents: Optional[float] = Field(None, description="Fixed cents target (0 = use R-based)")
    partial_exit_fraction: Optional[float] = Field(None, description="Partial exit % (default 0.5)")


class WarriorEngineConfigRequest(BaseModel):
    """Request to update engine configuration."""
    max_candidates: Optional[int] = Field(None, ge=1, le=20, description="Max candidates to watch (1-20)")
    scanner_interval_minutes: Optional[int] = Field(None, ge=1, le=60, description="Scan interval in minutes")
    risk_per_trade: Optional[float] = Field(None, gt=0, description="Risk per trade in dollars")
    max_positions: Optional[int] = Field(None, ge=1, le=10, description="Max simultaneous positions")
    max_daily_loss: Optional[float] = Field(None, gt=0, description="Max daily loss before stopping")
    orb_enabled: Optional[bool] = Field(None, description="Enable ORB breakouts")
    pmh_enabled: Optional[bool] = Field(None, description="Enable PMH breakouts")


class WarriorCandidateResponse(BaseModel):
    """A Warrior Trading candidate."""
    symbol: str
    name: str
    price: float
    gap_percent: float
    relative_volume: float
    float_shares: Optional[int]
    catalyst_type: str
    catalyst_description: str
    quality_score: int
    is_ideal_float: bool
    is_ideal_rvol: bool
    is_ideal_gap: bool


class WarriorScanResponse(BaseModel):
    """Response from Warrior scan."""
    candidates: List[WarriorCandidateResponse]
    processed_count: int
    filtered_count: int
    avg_rvol: float
    avg_gap: float


# =============================================================================
# ENGINE STATE (Singleton)
# =============================================================================

# Use the singleton from warrior_engine
def get_engine() -> WarriorEngine:
    return get_warrior_engine()


# =============================================================================
# ENGINE CONTROL ROUTES
# =============================================================================

@router.get("/status")
async def get_warrior_status():
    """
    Get current Warrior engine status.
    
    Returns engine state, watchlist, and statistics.
    """
    engine = get_engine()
    return engine.get_status()


@router.post("/start")
async def start_warrior_engine(request: WarriorStartRequest = WarriorStartRequest()):
    """
    Start the Warrior automation engine.
    
    Begins pre-market scanning and entry monitoring.
    """
    engine = get_engine()
    
    # Update config
    engine.config.sim_only = request.sim_only
    engine.config.risk_per_trade = Decimal(str(request.risk_per_trade))
    engine.config.max_positions = request.max_positions
    engine.config.max_candidates = request.max_candidates
    
    # Wire up default callbacks if none are set
    # These use real market data for quotes but don't submit real orders (sim_only)
    if engine._get_quote is None:
        from nexus2.adapters.market_data.unified import UnifiedMarketData
        umd = UnifiedMarketData()
        
        async def default_get_quote(symbol: str):
            """Get quote from real market data (Alpaca for pre-market)."""
            quote = umd.get_quote(symbol)
            return float(quote.price) if quote else None
        
        engine.set_callbacks(
            get_quote=default_get_quote,
            # submit_order stays None in sim_only mode (no real orders)
        )
    
    result = await engine.start()
    return result


@router.post("/stop")
async def stop_warrior_engine():
    """
    Stop the Warrior automation engine.
    
    Stops all scanning and monitoring. Does NOT close positions.
    """
    engine = get_engine()
    result = await engine.stop()
    return result


@router.post("/pause")
async def pause_warrior_engine():
    """Pause the Warrior engine (continue monitoring, stop new entries)."""
    engine = get_engine()
    return await engine.pause()


@router.post("/resume")
async def resume_warrior_engine():
    """Resume the Warrior engine."""
    engine = get_engine()
    return await engine.resume()


@router.put("/config")
async def update_warrior_config(request: WarriorEngineConfigRequest):
    """
    Update Warrior engine configuration.
    
    Allows runtime updates to:
    - max_candidates: How many stocks to watch
    - scanner_interval_minutes: How often to scan
    - risk_per_trade: Risk per trade in dollars
    - max_positions: Max concurrent positions
    - max_daily_loss: Stop trading limit
    - orb_enabled/pmh_enabled: Entry triggers
    """
    engine = get_engine()
    updated = {}
    
    if request.max_candidates is not None:
        engine.config.max_candidates = request.max_candidates
        updated["max_candidates"] = request.max_candidates
    
    if request.scanner_interval_minutes is not None:
        old_interval = engine.config.scanner_interval_minutes
        engine.config.scanner_interval_minutes = request.scanner_interval_minutes
        updated["scanner_interval_minutes"] = request.scanner_interval_minutes
        # Interrupt sleep if new interval is shorter
        if request.scanner_interval_minutes < old_interval:
            engine.interrupt_scan_sleep()
    
    if request.risk_per_trade is not None:
        engine.config.risk_per_trade = Decimal(str(request.risk_per_trade))
        updated["risk_per_trade"] = request.risk_per_trade
    
    if request.max_positions is not None:
        engine.config.max_positions = request.max_positions
        updated["max_positions"] = request.max_positions
    
    if request.max_daily_loss is not None:
        engine.config.max_daily_loss = Decimal(str(request.max_daily_loss))
        updated["max_daily_loss"] = request.max_daily_loss
    
    if request.orb_enabled is not None:
        engine.config.orb_enabled = request.orb_enabled
        updated["orb_enabled"] = request.orb_enabled
    
    if request.pmh_enabled is not None:
        engine.config.pmh_enabled = request.pmh_enabled
        updated["pmh_enabled"] = request.pmh_enabled
    
    return {
        "status": "updated",
        "updated_fields": updated,
        "current_config": {
            "max_candidates": engine.config.max_candidates,
            "scanner_interval_minutes": engine.config.scanner_interval_minutes,
            "risk_per_trade": float(engine.config.risk_per_trade),
            "max_positions": engine.config.max_positions,
            "max_daily_loss": float(engine.config.max_daily_loss),
            "orb_enabled": engine.config.orb_enabled,
            "pmh_enabled": engine.config.pmh_enabled,
        }
    }


# =============================================================================
# SCANNER ROUTES
# =============================================================================

@router.post("/scanner/run", response_model=WarriorScanResponse)
async def run_warrior_scan():
    """
    Run a Warrior Trading scan.
    
    Scans for low-float momentum stocks matching Ross Cameron's 5 Pillars:
    1. Float < 100M (ideal < 20M)
    2. RVOL > 2x (ideal 3-5x)
    3. Catalyst (news/earnings/former runner)
    4. Price $1.50 - $20
    5. Gap > 4%
    """
    scanner = get_warrior_scanner_service()
    result = scanner.scan(verbose=False)
    
    candidates = [
        WarriorCandidateResponse(
            symbol=c.symbol,
            name=c.name,
            price=float(c.price),
            gap_percent=float(c.gap_percent),
            relative_volume=float(c.relative_volume),
            float_shares=c.float_shares,
            catalyst_type=c.catalyst_type,
            catalyst_description=c.catalyst_description,
            quality_score=c.quality_score,
            is_ideal_float=c.is_ideal_float,
            is_ideal_rvol=c.is_ideal_rvol,
            is_ideal_gap=c.is_ideal_gap,
        )
        for c in result.candidates
    ]
    
    return WarriorScanResponse(
        candidates=candidates,
        processed_count=result.processed_count,
        filtered_count=result.filtered_count,
        avg_rvol=float(result.avg_rvol),
        avg_gap=float(result.avg_gap),
    )


@router.get("/scanner/settings")
async def get_warrior_scanner_settings():
    """Get current Warrior scanner settings."""
    scanner = get_warrior_scanner_service()
    s = scanner.settings
    
    return {
        "max_float": s.max_float,
        "ideal_float": s.ideal_float,
        "min_rvol": float(s.min_rvol),
        "ideal_rvol": float(s.ideal_rvol),
        "min_gap": float(s.min_gap),
        "ideal_gap": float(s.ideal_gap),
        "min_price": float(s.min_price),
        "max_price": float(s.max_price),
        "require_catalyst": s.require_catalyst,
        "exclude_chinese_stocks": s.exclude_chinese_stocks,
        "min_dollar_volume": float(s.min_dollar_volume),
    }


@router.put("/scanner/settings")
async def update_warrior_scanner_settings(request: WarriorScannerSettingsRequest):
    """Update Warrior scanner settings."""
    scanner = get_warrior_scanner_service()
    
    if request.max_float is not None:
        scanner.settings.max_float = request.max_float
    if request.min_rvol is not None:
        scanner.settings.min_rvol = Decimal(str(request.min_rvol))
    if request.min_gap is not None:
        scanner.settings.min_gap = Decimal(str(request.min_gap))
    if request.min_price is not None:
        scanner.settings.min_price = Decimal(str(request.min_price))
    if request.max_price is not None:
        scanner.settings.max_price = Decimal(str(request.max_price))
    if request.require_catalyst is not None:
        scanner.settings.require_catalyst = request.require_catalyst
    
    return {"status": "updated", "settings": await get_warrior_scanner_settings()}


# =============================================================================
# MONITOR ROUTES
# =============================================================================

@router.get("/monitor/status")
async def get_warrior_monitor_status():
    """Get Warrior position monitor status."""
    engine = get_engine()
    return engine.monitor.get_status()


@router.get("/monitor/settings")
async def get_warrior_monitor_settings():
    """Get current Warrior monitor settings."""
    engine = get_engine()
    s = engine.monitor.settings
    
    return {
        "mental_stop_cents": float(s.mental_stop_cents),
        "use_technical_stop": s.use_technical_stop,
        "profit_target_r": s.profit_target_r,
        "partial_exit_fraction": s.partial_exit_fraction,
        "move_stop_to_breakeven": s.move_stop_to_breakeven,
        "enable_candle_under_candle": s.enable_candle_under_candle,
        "enable_topping_tail": s.enable_topping_tail,
        "topping_tail_threshold": s.topping_tail_threshold,
        "check_interval_seconds": s.check_interval_seconds,
    }


@router.put("/monitor/settings")
async def update_warrior_monitor_settings(request: WarriorMonitorSettingsRequest):
    """Update Warrior monitor settings."""
    engine = get_engine()
    
    if request.mental_stop_cents is not None:
        engine.monitor.settings.mental_stop_cents = Decimal(str(request.mental_stop_cents))
    if request.profit_target_r is not None:
        engine.monitor.settings.profit_target_r = request.profit_target_r
    if request.partial_exit_fraction is not None:
        engine.monitor.settings.partial_exit_fraction = request.partial_exit_fraction
    
    return {"status": "updated", "settings": await get_warrior_monitor_settings()}


# =============================================================================
# POSITIONS & WATCHLIST ROUTES
# =============================================================================

@router.get("/positions")
async def get_warrior_positions():
    """Get positions being monitored by Warrior engine."""
    engine = get_engine()
    positions = engine.monitor.get_positions()
    
    return {
        "count": len(positions),
        "positions": [
            {
                "position_id": p.position_id,
                "symbol": p.symbol,
                "entry_price": float(p.entry_price),
                "shares": p.shares,
                "current_stop": float(p.current_stop),
                "profit_target": float(p.profit_target),
                "partial_taken": p.partial_taken,
                "high_since_entry": float(p.high_since_entry),
                "entry_time": p.entry_time.isoformat() if p.entry_time else None,
            }
            for p in positions
        ],
    }


@router.get("/watchlist")
async def get_warrior_watchlist():
    """Get current Warrior watchlist (candidates being watched for entry)."""
    engine = get_engine()
    status = engine.get_status()
    
    return {
        "count": status["watchlist_count"],
        "watchlist": status["watchlist"],
    }


# =============================================================================
# DIAGNOSTICS
# =============================================================================

@router.get("/diagnostics")
async def get_warrior_diagnostics():
    """
    Get detailed diagnostics for Warrior Trading system.
    
    Includes engine, scanner, monitor, and rejection statistics.
    """
    from nexus2.domain.automation.rejection_tracker import get_rejection_tracker
    
    engine = get_engine()
    scanner = get_warrior_scanner_service()
    tracker = get_rejection_tracker()
    
    # Get warrior-specific rejections
    warrior_rejections = tracker.get_recent(count=50, scanner="warrior")
    rejection_summary = tracker.get_summary()
    
    return {
        "engine": engine.get_status(),
        "scanner_settings": await get_warrior_scanner_settings(),
        "monitor_settings": await get_warrior_monitor_settings(),
        "rejections": {
            "recent": warrior_rejections[-10:],  # Last 10
            "total_warrior": rejection_summary.get("by_scanner", {}).get("warrior", 0),
            "by_reason": {
                k: v for k, v in rejection_summary.get("by_reason", {}).items()
                if k in ["float_too_high", "rvol_too_low", "no_catalyst", "price_out_of_range"]
            },
        },
    }


# =============================================================================
# SIMULATION ROUTES
# =============================================================================

import threading
from uuid import uuid4

# Warrior-specific sim broker (separate from KK-style automation)
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


@router.get("/sim/status")
async def get_warrior_sim_status():
    """
    Get Warrior simulation status.
    
    Returns whether sim mode is active, account info, and positions.
    """
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


@router.post("/sim/enable")
async def enable_warrior_sim(request: WarriorSimEnableRequest = WarriorSimEnableRequest()):
    """
    Enable Warrior simulation mode with MockBroker.
    
    Creates a new MockBroker with specified initial cash.
    """
    from nexus2.adapters.simulation.mock_broker import MockBroker
    
    broker = MockBroker(initial_cash=request.initial_cash)
    set_warrior_sim_broker(broker)
    
    # Configure engine for sim mode
    engine = get_engine()
    engine.config.sim_only = True
    
    # Wire up engine callbacks to MockBroker
    async def sim_submit_order(symbol: str, shares: int, side: str = "buy", order_type: str = "market", stop_loss: float = None, limit_price: float = None, trigger_type: str = "orb"):
        """Submit order to MockBroker."""
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
        """Get price - try MockBroker first, fallback to real market data."""
        sim_broker = get_warrior_sim_broker()
        if sim_broker:
            price = sim_broker.get_price(symbol)
            if price is not None:
                return price
        
        # Fallback to real market data (Alpaca for real-time)
        from nexus2.adapters.market_data.unified import UnifiedMarketData
        umd = UnifiedMarketData()
        quote = umd.get_quote(symbol)
        return float(quote.price) if quote else None
    
    async def sim_get_positions():
        """Get positions from MockBroker."""
        sim_broker = get_warrior_sim_broker()
        return sim_broker.get_positions() if sim_broker else []
    
    async def sim_execute_exit(signal):
        """Execute exit signal on MockBroker."""
        sim_broker = get_warrior_sim_broker()
        if sim_broker is None:
            print("[Sim] No broker for exit execution")
            return False
        
        # Sell the shares
        success = sim_broker.sell_position(signal.symbol, signal.shares_to_exit)
        if success:
            print(f"[Sim] Executed exit: {signal.symbol} x{signal.shares_to_exit} @ ${signal.exit_price}")
        return success
    
    async def sim_update_stop(position_id: str, new_stop_price):
        """Update stop price in MockBroker."""
        sim_broker = get_warrior_sim_broker()
        if sim_broker is None:
            print(f"[Sim] No broker for stop update")
            return False
        
        # Get symbol from monitor's position (position_id is a UUID)
        from nexus2.domain.automation.warrior_monitor import get_warrior_monitor
        monitor = get_warrior_monitor()
        symbol = None
        
        # Look up symbol from monitor's positions
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
    )
    
    # Also wire up monitor callbacks for exit execution
    from nexus2.domain.automation.warrior_monitor import get_warrior_monitor
    monitor = get_warrior_monitor()
    monitor.set_callbacks(
        get_price=sim_get_quote,
        execute_exit=sim_execute_exit,
        update_stop=sim_update_stop,
    )
    
    return {
        "status": "enabled",
        "initial_cash": request.initial_cash,
        "message": "Warrior simulation mode enabled with MockBroker",
    }


@router.post("/sim/reset")
async def reset_warrior_sim(request: WarriorSimEnableRequest = WarriorSimEnableRequest()):
    """
    Reset Warrior simulation to initial state.
    
    Clears all positions and resets cash.
    """
    from nexus2.adapters.simulation.mock_broker import MockBroker
    
    broker = MockBroker(initial_cash=request.initial_cash)
    set_warrior_sim_broker(broker)
    
    # Clear engine statistics
    engine = get_engine()
    engine.stats.trades_today = 0
    engine.stats.pnl_today = Decimal("0")
    
    return {
        "status": "reset",
        "initial_cash": request.initial_cash,
        "message": "Warrior simulation reset to initial state",
    }


@router.post("/sim/order")
async def submit_warrior_sim_order(request: WarriorSimOrderRequest):
    """
    Submit a simulated order to MockBroker.
    
    For manual testing of the simulation environment.
    """
    broker = get_warrior_sim_broker()
    
    if broker is None:
        raise HTTPException(
            status_code=400,
            detail="Simulation not enabled. POST /warrior/sim/enable first.",
        )
    
    # Set price if not already set
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
    
    return {
        "status": "filled" if is_filled else "rejected",
        "symbol": request.symbol,
        "shares": request.shares,
        "fill_price": float(fill_price) if fill_price else None,
        "stop_price": request.stop_price,
    }


@router.post("/sim/sell")
async def sell_warrior_sim_position(symbol: str, shares: Optional[int] = None):
    """
    Sell a simulated position (partial or full).
    """
    broker = get_warrior_sim_broker()
    
    if broker is None:
        raise HTTPException(
            status_code=400,
            detail="Simulation not enabled. POST /warrior/sim/enable first.",
        )
    
    sold = broker.sell_position(symbol, shares)
    
    if sold:
        return {
            "status": "sold",
            "symbol": symbol,
            "shares_sold": shares or "all",
        }
    else:
        raise HTTPException(
            status_code=404,
            detail=f"No position found for {symbol}",
        )


@router.put("/sim/price")
async def set_warrior_sim_price(symbol: str, price: float):
    """
    Set the current price for a symbol in simulation.
    
    Used to simulate price movements.
    """
    broker = get_warrior_sim_broker()
    
    if broker is None:
        raise HTTPException(
            status_code=400,
            detail="Simulation not enabled. POST /warrior/sim/enable first.",
        )
    
    broker.set_price(symbol, price)
    
    # Check for stop triggers in MockBroker
    broker._check_stop_orders(symbol)
    
    # Also trigger monitor check for profit targets and mental stops
    from nexus2.domain.automation.warrior_monitor import get_warrior_monitor
    monitor = get_warrior_monitor()
    if monitor._running:
        await monitor._check_all_positions()
    
    return {
        "status": "updated",
        "symbol": symbol,
        "price": price,
    }


# =============================================================================
# ALPACA ACCOUNT B BROKER ROUTES
# =============================================================================

# Warrior-specific Alpaca broker (Account B - isolated from KK automation)
_warrior_alpaca_broker = None


def get_warrior_alpaca_broker():
    """Get Warrior's Alpaca broker (Account B) if configured."""
    return _warrior_alpaca_broker


def create_warrior_alpaca_broker():
    """Create AlpacaBroker using Account B credentials."""
    from nexus2 import config
    
    if not config.ALPACA_KEY_B or not config.ALPACA_SECRET_B:
        return None
    
    from nexus2.adapters.broker import AlpacaBroker, AlpacaBrokerConfig
    
    return AlpacaBroker(AlpacaBrokerConfig(
        api_key=config.ALPACA_KEY_B,
        api_secret=config.ALPACA_SECRET_B,
        paper=True,  # ALWAYS paper for Warrior
    ))


@router.get("/broker/status")
async def get_warrior_broker_status():
    """
    Get Warrior Alpaca broker status.
    
    Checks if Account B credentials are configured and broker is connected.
    """
    from nexus2 import config
    
    has_credentials = bool(config.ALPACA_KEY_B and config.ALPACA_SECRET_B)
    broker = get_warrior_alpaca_broker()
    
    if not has_credentials:
        return {
            "broker_enabled": False,
            "message": "Account B credentials not set. Add APCA_API_KEY_ID_B and APCA_API_SECRET_KEY_B to .env",
        }
    
    if broker is None:
        return {
            "broker_enabled": False,
            "credentials_set": True,
            "message": "Broker not initialized. POST /warrior/broker/enable to connect.",
        }
    
    # Try to get account info
    try:
        account_value = broker.get_account_value()
        positions = broker.get_positions()
        
        return {
            "broker_enabled": True,
            "paper_mode": True,
            "account_value": account_value,
            "positions_count": len(positions),
            "positions": [
                {
                    "symbol": p.symbol,
                    "qty": p.quantity,
                    "avg_price": float(p.average_entry_price),
                    "current_price": float(p.current_price),
                    "unrealized_pnl": float(p.unrealized_pnl),
                }
                for p in positions
            ],
        }
    except Exception as e:
        return {
            "broker_enabled": False,
            "error": str(e),
        }


@router.post("/broker/enable")
async def enable_warrior_broker():
    """
    Enable Alpaca Account B for Warrior engine.
    
    Wires WarriorEngine callbacks to real Alpaca paper trading.
    """
    global _warrior_alpaca_broker
    
    # Create broker
    broker = create_warrior_alpaca_broker()
    
    if broker is None:
        raise HTTPException(
            status_code=400,
            detail="Account B credentials not configured. Add APCA_API_KEY_ID_B and APCA_API_SECRET_KEY_B to .env",
        )
    
    _warrior_alpaca_broker = broker
    
    # Verify connection
    try:
        account_value = broker.get_account_value()
    except Exception as e:
        _warrior_alpaca_broker = None
        raise HTTPException(
            status_code=500,
            detail=f"Failed to connect to Alpaca: {e}",
        )
    
    # Wire engine callbacks to broker
    engine = get_engine()
    engine.config.sim_only = False  # Enable real order submission
    
    async def broker_submit_order(
        symbol: str,
        shares: int,
        side: str = "buy",
        order_type: str = "market",
        stop_loss: float = None,
        limit_price: float = None,
        **kwargs,  # Accept any extra args
    ):
        """Submit order to Alpaca Account B."""
        alpaca = get_warrior_alpaca_broker()
        if alpaca is None:
            print(f"[Warrior] No broker configured")
            return None
        
        try:
            # Warrior uses mental stops, so we use regular market order
            # (not bracket order since stops are managed by monitor)
            result = alpaca.submit_order(
                client_order_id=uuid4(),
                symbol=symbol,
                side=side,
                quantity=shares,
                order_type=order_type,
                limit_price=Decimal(str(limit_price)) if limit_price else None,
            )
            print(f"[Warrior] Order submitted: {symbol} x{shares} ({side})")
            return result
        except Exception as e:
            print(f"[Warrior] Alpaca order failed: {e}")
            return None
    
    async def broker_get_positions():
        """Get positions from Alpaca Account B."""
        alpaca = get_warrior_alpaca_broker()
        if alpaca is None:
            return []
        
        try:
            positions = alpaca.get_positions()
            return [
                {
                    "symbol": p.symbol,
                    "qty": p.quantity,
                    "avg_price": float(p.average_entry_price),
                    "current_price": float(p.current_price),
                    "unrealized_pnl": float(p.unrealized_pnl),
                }
                for p in positions
            ]
        except Exception as e:
            print(f"[Warrior] Failed to get positions: {e}")
            return []
    
    # Wire up quotes from UnifiedMarketData (Alpaca for real-time pre-market)
    from nexus2.adapters.market_data.unified import UnifiedMarketData
    umd = UnifiedMarketData()
    
    async def broker_get_quote(symbol: str):
        """Get quote from real market data (Alpaca for pre-market)."""
        quote = umd.get_quote(symbol)
        return float(quote.price) if quote else None
    
    engine.set_callbacks(
        submit_order=broker_submit_order,
        get_quote=broker_get_quote,
        get_positions=broker_get_positions,
    )
    
    return {
        "status": "enabled",
        "broker": "alpaca_paper_b",
        "account_value": account_value,
        "message": "WarriorEngine connected to Alpaca Account B (paper)",
    }


@router.post("/broker/test")
async def test_warrior_broker():
    """
    Test Alpaca connection by placing and canceling a limit order.
    
    Places a $1 limit buy on AAPL, then immediately cancels it.
    """
    broker = get_warrior_alpaca_broker()
    
    if broker is None:
        raise HTTPException(
            status_code=400,
            detail="Broker not enabled. Call POST /warrior/broker/enable first.",
        )
    
    try:
        import time
        from uuid import uuid4
        from decimal import Decimal
        
        print("[Warrior] Testing Alpaca connection...")
        
        # Use broker's submit_order method with a limit order that won't fill
        test_client_id = uuid4()
        order = broker.submit_order(
            client_order_id=test_client_id,
            symbol="AAPL",
            side="buy",
            quantity=1,
            order_type="limit",
            limit_price=Decimal("1.00"),
        )
        
        order_id = order.broker_order_id
        print(f"[Warrior] Test order placed: {order_id}")
        
        # Wait a moment
        time.sleep(0.5)
        
        # Cancel the order
        broker.cancel_order(order_id)
        print(f"[Warrior] Test order canceled: {order_id}")
        
        return {
            "status": "success",
            "message": "Alpaca connection verified - order placed and canceled",
            "order_id": str(order_id),
        }
    except Exception as e:
        print(f"[Warrior] Test order failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Alpaca test failed: {e}",
        )


# =============================================================================
# WARRIOR TEST CASE ROUTES
# =============================================================================

@router.get("/sim/test_cases")
async def list_warrior_test_cases():
    """
    List available Warrior test cases.
    
    Returns test cases from warrior_setups.yaml for historical backtesting.
    """
    import os
    import yaml
    
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
    
    return {
        "test_cases": summary,
        "count": len(summary),
    }


@router.post("/sim/load_test_case")
async def load_warrior_test_case(case_id: str):
    """
    Load a Warrior test case into the MockBroker.
    
    Sets up prices and runs scanner to see if it would catch the stock.
    """
    import os
    import yaml
    
    # Load YAML
    yaml_path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "tests", "test_cases", "warrior_setups.yaml"
    )
    
    if not os.path.exists(yaml_path):
        raise HTTPException(status_code=404, detail="Test cases file not found")
    
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)
    
    test_cases = data.get("test_cases", [])
    
    # Find the test case
    case = None
    for tc in test_cases:
        if tc.get("id") == case_id:
            case = tc
            break
    
    if case is None:
        available = [tc.get("id") for tc in test_cases]
        raise HTTPException(
            status_code=404,
            detail=f"Test case '{case_id}' not found. Available: {available}"
        )
    
    # Ensure sim is enabled
    broker = get_warrior_sim_broker()
    if broker is None:
        # Auto-enable
        from nexus2.adapters.simulation.mock_broker import MockBroker
        broker = MockBroker(initial_cash=25000.0)
        set_warrior_sim_broker(broker)
    
    # Set price based on premarket data
    premarket = case.get("premarket_data", {})
    expected = case.get("expected", {})
    
    symbol = case.get("symbol")
    entry_price = expected.get("entry_near")
    
    if entry_price:
        broker.set_price(symbol, entry_price)
    
    # Evaluate with scanner to see if it would pass
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
    
    # For Mock Market: add to watchlist regardless of scanner result
    # This allows testing historical trades that may not pass current scanner filters
    engine = get_engine()
    
    from nexus2.domain.automation.warrior_engine import WatchedCandidate
    from nexus2.domain.scanner.warrior_scanner_service import WarriorCandidate
    
    # Create mock candidate if scanner rejected
    if not candidate:
        candidate = WarriorCandidate(
            symbol=symbol,
            name=symbol,
            price=Decimal(str(current_price)) if current_price else Decimal("0"),
            gap_percent=Decimal(str(gap_pct)),
            relative_volume=Decimal("10.0"),  # Mock high RVOL for test
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
    
    watched = WatchedCandidate(
        candidate=candidate,
        pmh=pmh,
    )
    
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
