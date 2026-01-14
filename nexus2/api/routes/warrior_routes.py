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
    """Request to start Warrior engine.
    
    All fields are Optional to preserve persisted settings.
    Only explicitly provided values will override current config.
    """
    sim_only: Optional[bool] = None
    risk_per_trade: Optional[float] = None
    max_positions: Optional[int] = None
    max_candidates: Optional[int] = None


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
    # Scaling settings (Ross Cameron methodology)
    enable_scaling: Optional[bool] = Field(None, description="Enable scaling into winners")
    max_scale_count: Optional[int] = Field(None, description="Max adds (1-5)")
    scale_size_pct: Optional[int] = Field(None, description="Add size as % of original")
    min_rvol_for_scale: Optional[float] = Field(None, description="Min RVOL for scaling")
    allow_scale_below_entry: Optional[bool] = Field(None, description="Allow scaling below entry")
    move_stop_to_breakeven_after_scale: Optional[bool] = Field(None, description="Move stop to breakeven after add")


class WarriorEngineConfigRequest(BaseModel):
    """Request to update engine configuration."""
    max_candidates: Optional[int] = Field(None, ge=1, le=20, description="Max candidates to watch (1-20)")
    scanner_interval_minutes: Optional[int] = Field(None, ge=1, le=60, description="Scan interval in minutes")
    risk_per_trade: Optional[float] = Field(None, gt=0, description="Risk per trade in dollars")
    max_positions: Optional[int] = Field(None, ge=1, le=20, description="Max simultaneous positions")
    max_daily_loss: Optional[float] = Field(None, gt=0, description="Max daily loss before stopping")
    orb_enabled: Optional[bool] = Field(None, description="Enable ORB breakouts")
    pmh_enabled: Optional[bool] = Field(None, description="Enable PMH breakouts")
    max_shares_per_trade: Optional[int] = Field(None, ge=1, description="Max shares per trade (for testing)")
    max_value_per_trade: Optional[float] = Field(None, gt=0, description="Max $ value per trade (for testing)")


class ScalingSettingsRequest(BaseModel):
    """Request to update scaling settings (Ross Cameron methodology)."""
    enable_scaling: Optional[bool] = Field(None, description="Enable scaling into winners")
    max_scale_count: Optional[int] = Field(None, ge=1, le=5, description="Max adds (1-5)")
    scale_size_pct: Optional[int] = Field(None, ge=10, le=200, description="Add size as % of original (10-200)")
    min_rvol_for_scale: Optional[float] = Field(None, ge=1.0, le=10.0, description="Min RVOL for scaling (1-10)")
    allow_scale_below_entry: Optional[bool] = Field(None, description="Allow scaling on pullback below entry")
    move_stop_to_breakeven_after_scale: Optional[bool] = Field(None, description="Move stop to breakeven after add")


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


# =============================================================================
# SCHWAB OAUTH ROUTES
# =============================================================================

@router.get("/schwab/auth-url")
async def get_schwab_auth_url():
    """
    Get Schwab OAuth authorization URL.
    
    Open this URL in a browser to log in to Schwab.
    After login, copy the 'code' from the callback URL and POST to /schwab/callback.
    """
    from nexus2.adapters.market_data.schwab_adapter import get_schwab_adapter
    schwab = get_schwab_adapter()
    
    if not schwab.client_id:
        raise HTTPException(400, "SCHWAB_CLIENT_ID not configured in .env")
    
    return {
        "auth_url": schwab.get_auth_url(),
        "instructions": "Open auth_url in browser, login, then POST the 'code' param to /warrior/schwab/callback",
    }


@router.post("/schwab/callback")
async def schwab_oauth_callback(code: str):
    """
    Exchange Schwab OAuth code for access tokens.
    
    After logging in via the auth_url, Schwab redirects to 127.0.0.1 with a code.
    Copy that code and POST here to complete authentication.
    """
    from nexus2.adapters.market_data.schwab_adapter import get_schwab_adapter
    schwab = get_schwab_adapter()
    
    success = schwab.exchange_code_for_tokens(code)
    
    if success:
        return {"status": "authenticated", "message": "Schwab tokens saved successfully"}
    else:
        raise HTTPException(400, "Failed to exchange code for tokens - check logs")


@router.get("/schwab/status")
async def get_schwab_status():
    """Check Schwab authentication status."""
    from nexus2.adapters.market_data.schwab_adapter import get_schwab_adapter
    schwab = get_schwab_adapter()
    
    return {
        "authenticated": schwab.is_authenticated(),
        "has_refresh_token": schwab._refresh_token is not None,
        "token_expiry": schwab._token_expiry.isoformat() if schwab._token_expiry else None,
    }


# =============================================================================
# ENGINE STATUS ROUTES
# =============================================================================

@router.get("/status")
async def get_warrior_status():
    """
    Get current Warrior engine status.
    
    Returns engine state, watchlist, and statistics.
    """
    engine = get_engine()
    status = engine.get_status()
    
    # Add auto_enable setting to status
    from nexus2.db.warrior_settings import get_auto_enable
    status["auto_enable"] = get_auto_enable()
    
    return status


class AutoEnableRequest(BaseModel):
    """Request to toggle auto-enable on startup."""
    enabled: bool = Field(..., description="True to auto-enable on startup, False to disable")


@router.patch("/auto-enable")
async def set_warrior_auto_enable(request: AutoEnableRequest):
    """
    Toggle Warrior auto-enable on server startup.
    
    When enabled, Warrior broker callbacks and position sync happen automatically
    when the server starts. Takes effect on next restart.
    """
    from nexus2.db.warrior_settings import set_auto_enable
    success = set_auto_enable(request.enabled)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save setting")
    
    return {
        "auto_enable": request.enabled,
        "message": f"Warrior auto-enable {'enabled' if request.enabled else 'disabled'}. Takes effect on next restart."
    }


@router.post("/start")
async def start_warrior_engine(request: WarriorStartRequest = WarriorStartRequest()):
    """
    Start the Warrior automation engine.
    
    Begins pre-market scanning and entry monitoring.
    """
    engine = get_engine()
    
    # Only update config for explicitly provided values (preserve loaded settings)
    if request.sim_only is not None:
        engine.config.sim_only = request.sim_only
    if request.risk_per_trade is not None:
        engine.config.risk_per_trade = Decimal(str(request.risk_per_trade))
    if request.max_positions is not None:
        engine.config.max_positions = request.max_positions
    if request.max_candidates is not None:
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
    
    if request.max_shares_per_trade is not None:
        engine.config.max_shares_per_trade = request.max_shares_per_trade
        updated["max_shares_per_trade"] = request.max_shares_per_trade
    
    if request.max_value_per_trade is not None:
        engine.config.max_value_per_trade = Decimal(str(request.max_value_per_trade))
        updated["max_value_per_trade"] = request.max_value_per_trade
    
    # Save settings to persist across restarts
    try:
        from nexus2.db.warrior_settings import save_warrior_settings, get_config_dict
        save_warrior_settings(get_config_dict(engine.config))
    except Exception as e:
        print(f"[Warrior] Failed to save settings: {e}")
    
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
            "max_shares_per_trade": engine.config.max_shares_per_trade,
            "max_value_per_trade": float(engine.config.max_value_per_trade) if engine.config.max_value_per_trade else None,
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
        # Scaling settings (Ross Cameron methodology)
        "enable_scaling": s.enable_scaling,
        "max_scale_count": s.max_scale_count,
        "scale_size_pct": s.scale_size_pct,
        "min_rvol_for_scale": s.min_rvol_for_scale,
        "allow_scale_below_entry": s.allow_scale_below_entry,
        "move_stop_to_breakeven_after_scale": s.move_stop_to_breakeven_after_scale,
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
    
    # Scaling settings (Ross Cameron methodology)
    if hasattr(request, 'enable_scaling') and request.enable_scaling is not None:
        engine.monitor.settings.enable_scaling = request.enable_scaling
    if hasattr(request, 'max_scale_count') and request.max_scale_count is not None:
        engine.monitor.settings.max_scale_count = request.max_scale_count
    if hasattr(request, 'scale_size_pct') and request.scale_size_pct is not None:
        engine.monitor.settings.scale_size_pct = request.scale_size_pct
    if hasattr(request, 'min_rvol_for_scale') and request.min_rvol_for_scale is not None:
        engine.monitor.settings.min_rvol_for_scale = request.min_rvol_for_scale
    if hasattr(request, 'allow_scale_below_entry') and request.allow_scale_below_entry is not None:
        engine.monitor.settings.allow_scale_below_entry = request.allow_scale_below_entry
    if hasattr(request, 'move_stop_to_breakeven_after_scale') and request.move_stop_to_breakeven_after_scale is not None:
        engine.monitor.settings.move_stop_to_breakeven_after_scale = request.move_stop_to_breakeven_after_scale
    
    # Persist settings to disk
    try:
        from nexus2.db.warrior_monitor_settings import save_monitor_settings, get_monitor_settings_dict
        save_monitor_settings(get_monitor_settings_dict(engine.monitor.settings))
    except Exception as e:
        print(f"[Warrior] Failed to persist monitor settings: {e}")
    
    return {"status": "updated", "settings": await get_warrior_monitor_settings()}


class ManualExitRequest(BaseModel):
    """Request to manually exit a position."""
    symbol: str
    limit_price: float = Field(..., description="Limit price for the sell order")
    shares: Optional[int] = Field(None, description="Shares to sell (default: all)")


@router.post("/manual_exit")
async def manual_exit_position(request: ManualExitRequest):
    """Manually exit a position at specified limit price.
    
    Cancels all pending sell orders for the symbol and submits a new limit sell.
    Useful for illiquid stocks where automated exits failed.
    """
    alpaca = get_warrior_alpaca_broker()
    if alpaca is None:
        raise HTTPException(status_code=400, detail="Warrior broker not enabled")
    
    symbol = request.symbol.upper()
    
    # Get current position from Alpaca
    positions = alpaca.get_positions()
    position = None
    for p in positions:
        pos_symbol = p.get("symbol") if isinstance(p, dict) else getattr(p, "symbol", None)
        if pos_symbol == symbol:
            position = p
            break
    
    if position is None:
        raise HTTPException(status_code=404, detail=f"No position found for {symbol}")
    
    # Get shares to sell
    if isinstance(position, dict):
        total_shares = int(float(position.get("qty", 0)))
    else:
        total_shares = int(float(getattr(position, "qty", 0)))
    
    shares_to_sell = request.shares if request.shares else total_shares
    
    # Cancel pending sell orders
    cancelled = alpaca.cancel_open_orders(symbol, side="sell")
    
    # Submit new limit sell
    from uuid import uuid4
    order = alpaca.submit_order(
        client_order_id=uuid4(),
        symbol=symbol,
        quantity=shares_to_sell,
        side="sell",
        order_type="limit",
        limit_price=Decimal(str(request.limit_price)),
        extended_hours=True,
    )
    
    # Remove from monitor if present
    engine = get_engine()
    for pos_id, pos in list(engine.monitor._positions.items()):
        if pos.symbol == symbol:
            engine.monitor.remove_position(pos_id)
            engine.monitor._recently_exited[symbol] = __import__('datetime').datetime.utcnow()
            engine.monitor._save_recently_exited()  # Persist for restart survival
            break
    
    return {
        "status": "submitted",
        "symbol": symbol,
        "shares": shares_to_sell,
        "limit_price": request.limit_price,
        "cancelled_orders": cancelled,
        "order_id": str(order.client_order_id) if order else None,
    }


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
    
    # Also set monitor to sim_mode (bypasses time checks for Mock Market testing)
    engine.monitor.sim_mode = True
    
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
            # Log exit event
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
        submit_scale_order=sim_submit_order,  # Reuse for scaling
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


@router.post("/sim/disable")
async def disable_warrior_sim():
    """
    Disable Warrior simulation mode.
    
    Clears MockBroker and resets engine to non-sim mode.
    """
    # Clear the MockBroker
    set_warrior_sim_broker(None)
    
    # Reset engine sim flags
    engine = get_engine()
    engine.config.sim_only = False
    engine.monitor.sim_mode = False
    
    return {
        "status": "disabled",
        "message": "Warrior simulation mode disabled",
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
    
    from uuid import uuid4
    result = broker.submit_bracket_order(
        client_order_id=uuid4(),
        symbol=request.symbol,
        quantity=request.shares,
        stop_loss_price=request.stop_price,
        limit_price=Decimal(str(request.limit_price)) if request.limit_price else None,
    )
    
    is_filled = getattr(result, 'is_accepted', False) or getattr(result, 'filled_qty', 0) > 0
    fill_price = getattr(result, 'avg_fill_price', request.limit_price)
    
    # Log entry event if filled
    if is_filled:
        from nexus2.domain.automation.trade_event_service import trade_event_service
        trade_event_service.log_warrior_entry(
            position_id=str(uuid4()),  # Generate unique ID for sim
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


def set_warrior_alpaca_broker(broker):
    """Set Warrior's Alpaca broker (for auto-enable on startup)."""
    global _warrior_alpaca_broker
    _warrior_alpaca_broker = broker


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
        
        # Calculate unrealized P&L and invested capital from positions
        total_unrealized_pnl = 0.0
        total_invested = 0.0
        positions_list = list(positions.values()) if isinstance(positions, dict) else positions
        for p in positions_list:
            total_unrealized_pnl += float(p.unrealized_pnl) if p.unrealized_pnl else 0
            total_invested += float(p.avg_price) * p.quantity if p.avg_price else 0
        
        # Get realized P&L from monitor (for display/tracking purposes)
        from nexus2.domain.automation.warrior_monitor import get_warrior_monitor
        monitor = get_warrior_monitor()
        monitor_realized_pnl = float(monitor.realized_pnl_today)
        
        # Get accurate daily P&L from Alpaca account (equity - last_equity)
        # This is the source of truth for total account P&L
        account_pnl = broker.get_account_daily_pnl()
        total_daily_pnl = account_pnl["daily_pnl"]
        daily_pnl_percent = account_pnl["daily_pnl_percent"]
        
        # Get capital stats from today's order history
        capital_stats = broker.get_daily_capital_stats()
        peak_exposure = capital_stats["peak_exposure"]
        total_capital_deployed = capital_stats["total_capital_deployed"]
        
        return {
            "broker_enabled": True,
            "paper_mode": True,
            "account_value": account_value,
            "positions_count": len(positions_list),
            # Daily P&L Summary
            "realized_pnl_today": monitor_realized_pnl,
            "unrealized_pnl": total_unrealized_pnl,
            "total_daily_pnl": total_daily_pnl,
            # Capital stats
            "invested_capital": total_invested,  # Current open positions
            "peak_exposure": peak_exposure,  # Max at risk today
            "total_capital_deployed": total_capital_deployed,  # Sum of all buys today
            "daily_pnl_percent": round(daily_pnl_percent, 2),  # Based on peak exposure
            # Positions
            "positions": [
                {
                    "symbol": p.symbol,
                    "qty": p.quantity,
                    "avg_price": float(p.avg_price),
                    "current_price": float(p.current_price),
                    "unrealized_pnl": float(p.unrealized_pnl),
                }
                for p in positions_list
            ],
        }
    except Exception as e:
        return {
            "broker_enabled": False,
            "error": str(e),
        }


@router.post("/broker/close/{symbol}")
async def close_warrior_position(symbol: str, limit_price: float = None):
    """
    Close a position manually via limit order (for after-hours).
    
    If no limit_price, uses current bid price.
    """
    broker = get_warrior_alpaca_broker()
    
    if broker is None:
        raise HTTPException(status_code=400, detail="Broker not enabled")
    
    try:
        positions = broker.get_positions()
        positions_dict = positions if isinstance(positions, dict) else {p.symbol: p for p in positions}
        
        if symbol not in positions_dict:
            raise HTTPException(status_code=404, detail=f"Position {symbol} not found")
        
        pos = positions_dict[symbol]
        qty = pos.quantity
        
        # Get limit price if not provided
        if limit_price is None:
            from nexus2.adapters.market_data import UnifiedMarketData
            market_data = UnifiedMarketData()
            quote = market_data.get_quote(symbol)
            if quote:
                limit_price = float(quote.price) if hasattr(quote, 'price') else float(pos.current_price) * 0.99
            else:
                limit_price = float(pos.current_price) * 0.99  # 1% below current
        
        # Submit sell order (extended hours for after-market)
        from uuid import uuid4
        result = broker.submit_order(
            client_order_id=uuid4(),
            symbol=symbol,
            side="sell",
            quantity=qty,
            order_type="limit",
            limit_price=Decimal(str(round(limit_price, 2))),
            extended_hours=True,
        )
        
        return {
            "success": True,
            "symbol": symbol,
            "shares": qty,
            "limit_price": limit_price,
            "result": result,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def wire_warrior_callbacks(broker) -> dict:
    """Wire WarriorEngine and Monitor callbacks to Alpaca broker.
    
    Extracted for reuse from both /broker/enable endpoint and startup auto-enable.
    
    Args:
        broker: AlpacaBroker instance (Account B)
        
    Returns:
        dict with status and account_value, or raises exception on failure
    """
    # Verify connection
    try:
        account_value = broker.get_account_value()
    except Exception as e:
        raise Exception(f"Failed to connect to Alpaca: {e}")
    
    # Wire engine callbacks to broker
    engine = get_engine()
    engine.config.sim_only = False  # Enable real order submission
    
    async def broker_submit_order(
        symbol: str,
        shares: int,
        side: str = "buy",
        order_type: str = "limit",  # Ross Cameron: always limit orders
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
            result = alpaca.submit_order(
                client_order_id=uuid4(),
                symbol=symbol,
                side=side,
                quantity=shares,
                order_type=order_type,
                limit_price=Decimal(str(limit_price)) if limit_price else None,
                extended_hours=True,
            )
            print(f"[Warrior] LIMIT order submitted: {symbol} x{shares} @ ${limit_price} ({side})")
            return result
        except Exception as e:
            error_str = str(e).lower()
            if "not tradable" in error_str or "is not fractionable" in error_str or "asset not found" in error_str:
                print(f"[Warrior] {symbol} is not tradable - adding to blacklist")
                return {"blacklist": True, "symbol": symbol, "error": str(e)}
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
                    "avg_price": float(p.avg_price),
                    "current_price": float(p.current_price) if p.current_price else 0,
                    "unrealized_pnl": float(p.unrealized_pnl),
                }
                for p in positions.values()
            ]
        except Exception as e:
            print(f"[Warrior] Failed to get positions: {e}")
            return []
    
    # Wire up quotes from UnifiedMarketData
    from nexus2.adapters.market_data.unified import UnifiedMarketData
    umd = UnifiedMarketData()
    
    async def broker_get_quote(symbol: str):
        """Get quote from real market data."""
        quote = umd.get_quote(symbol)
        return float(quote.price) if quote else None
    
    async def broker_get_quotes_batch(symbols: list):
        """Get quotes for multiple symbols in ONE API call."""
        try:
            from nexus2.adapters.market_data.alpaca_adapter import AlpacaAdapter
            alpaca = AlpacaAdapter()
            quotes = alpaca.get_quotes_batch(symbols)
            return {sym: float(q.price) for sym, q in quotes.items() if q}
        except Exception as e:
            print(f"[Warrior] Batch quote failed: {e}")
            return {}
    
    async def broker_get_intraday_bars(symbol: str, timeframe: str = "5min", limit: int = 50):
        """Get intraday bars for technical indicator calculation (VWAP, EMA, MACD).
        
        Returns list of bar objects with high, low, close, volume attributes.
        """
        try:
            from nexus2.adapters.market_data.alpaca_adapter import AlpacaAdapter
            from dataclasses import dataclass
            
            @dataclass
            class Bar:
                open: float
                high: float
                low: float
                close: float
                volume: int
            
            alpaca = AlpacaAdapter()
            # Use the existing bars method if available
            if hasattr(alpaca, 'get_bars'):
                bars = alpaca.get_bars(symbol, timeframe=timeframe, limit=limit)
                if bars:
                    # Convert to simple bar objects
                    return [Bar(
                        open=float(b.open),
                        high=float(b.high), 
                        low=float(b.low), 
                        close=float(b.close), 
                        volume=int(b.volume)
                    ) for b in bars]
            
            # Fallback: try FMP intraday bars
            from nexus2.adapters.market_data.fmp_adapter import get_fmp_adapter
            fmp = get_fmp_adapter()
            if fmp:
                # Get 5min bars from FMP using correct method
                fmp_bars = fmp.get_intraday_bars(symbol, timeframe="5min")
                if fmp_bars and len(fmp_bars) >= 5:
                    # FMP returns OHLCV objects, get last N bars
                    bars_to_use = fmp_bars[-limit:] if len(fmp_bars) > limit else fmp_bars
                    return [Bar(
                        open=float(b.open),
                        high=float(b.high),
                        low=float(b.low),
                        close=float(b.close),
                        volume=int(b.volume)
                    ) for b in bars_to_use]
            
            return None
        except Exception as e:
            print(f"[Warrior] Intraday bars failed for {symbol}: {e}")
            return None
    # Schwab quote cache (10-second TTL to stay under 120 calls/min limit)
    _schwab_quote_cache: dict = {}
    _schwab_cache_ttl = 10  # seconds
    
    async def broker_get_quote_with_spread(symbol: str):
        """Get quote with bid/ask spread for spread exit trigger.
        
        Priority: Alpaca (primary) -> Schwab (fallback when bid/ask = 0)
        Schwab fallback is cached for 10 seconds to respect rate limits.
        """
        import time
        
        bid = 0
        ask = 0
        price = 0
        
        # Try Alpaca first
        try:
            from nexus2.adapters.market_data.alpaca_adapter import AlpacaAdapter
            alpaca = AlpacaAdapter()
            quote = alpaca.get_quote(symbol)
            if quote:
                price = float(quote.price)
                bid = float(quote.bid) if hasattr(quote, 'bid') and quote.bid else 0
                ask = float(quote.ask) if hasattr(quote, 'ask') and quote.ask else 0
        except Exception as e:
            print(f"[Warrior] Alpaca quote failed for {symbol}: {e}")
        
        # Schwab fallback if Alpaca doesn't have bid/ask
        if bid <= 0 or ask <= 0:
            # Check cache first
            cache_key = symbol
            now = time.time()
            if cache_key in _schwab_quote_cache:
                cached_time, cached_data = _schwab_quote_cache[cache_key]
                if now - cached_time < _schwab_cache_ttl:
                    # Use cached Schwab data
                    bid = cached_data.get("bid", bid)
                    ask = cached_data.get("ask", ask)
                    price = cached_data.get("price", price)
                    # Don't print on cache hit to reduce log noise
                else:
                    # Cache expired, fetch new
                    del _schwab_quote_cache[cache_key]
            
            # Fetch from Schwab if not in cache
            if cache_key not in _schwab_quote_cache and (bid <= 0 or ask <= 0):
                try:
                    from nexus2.adapters.market_data.schwab_adapter import get_schwab_adapter
                    schwab = get_schwab_adapter()
                    if schwab.is_authenticated():
                        schwab_quote = schwab.get_quote(symbol)
                        if schwab_quote and schwab_quote.get("bid", 0) > 0:
                            bid = schwab_quote["bid"]
                            ask = schwab_quote["ask"]
                            price = schwab_quote.get("price", price)
                            # Cache the result
                            _schwab_quote_cache[cache_key] = (now, {"bid": bid, "ask": ask, "price": price})
                            print(f"[Warrior] Schwab fallback for {symbol}: bid=${bid:.2f}, ask=${ask:.2f} (cached 10s)")
                except Exception as e:
                    print(f"[Warrior] Schwab fallback failed for {symbol}: {e}")
        
        if price > 0 or bid > 0:
            return {"price": price, "bid": bid, "ask": ask}
        return None
    
    async def check_pending_fill(symbol: str) -> bool:
        """Check if there's a PENDING_FILL position for this symbol (unfilled buy order).
        
        Prevents duplicate buy orders when engine restarts before order fills.
        """
        try:
            from nexus2.db.database import SessionLocal
            from nexus2.db.repository import PositionRepository
            
            db = SessionLocal()
            try:
                repo = PositionRepository(db)
                # Get pending_fill positions, filter by symbol and account B (Warrior)
                pending = repo.get_all(status="pending_fill")
                for p in pending:
                    if p.symbol == symbol and p.account == "B":
                        print(f"[Warrior] {symbol}: Found existing PENDING_FILL position")
                        return True
                return False
            finally:
                db.close()
        except Exception as e:
            print(f"[Warrior] Pending fill check failed: {e}")
            return False  # Proceed if check fails
    
    async def broker_execute_exit(signal):
        """Execute exit order for a position."""
        alpaca = get_warrior_alpaca_broker()
        if alpaca is None:
            print("[Warrior] No broker - cannot execute exit")
            return None
        
        position_id = signal.position_id
        shares = signal.shares_to_exit
        reason = signal.reason.value if hasattr(signal.reason, 'value') else str(signal.reason)
        symbol = signal.symbol
        
        try:
            cancelled = alpaca.cancel_open_orders(symbol, side="sell")
            if cancelled > 0:
                print(f"[Warrior] Cancelled {cancelled} pending sell order(s) for {symbol} before exit")
            
            use_bid_pricing = reason in ("spread_exit", "after_hours_exit")
            
            if use_bid_pricing:
                spread_data = await broker_get_quote_with_spread(symbol)
                if spread_data and spread_data.get("bid", 0) > 0:
                    current_price = spread_data["bid"]
                    print(f"[Warrior] {reason} using bid: ${current_price:.2f} (ask=${spread_data.get('ask', 0):.2f})")
                else:
                    current_price = float(signal.exit_price)
                    print(f"[Warrior] No bid available, using signal price: ${current_price:.2f}")
            else:
                current_price = await broker_get_quote(symbol)
                signal_price = float(signal.exit_price)
                if current_price is None:
                    print(f"[Warrior] Cannot get quote for {symbol} - using signal exit price ${signal_price:.2f}")
                    current_price = signal_price
                elif current_price > signal_price * 1.05:
                    print(f"[Warrior] Stale quote detected: ${current_price:.2f} vs trigger ${signal_price:.2f} - using trigger price")
                    current_price = signal_price
            
            if hasattr(signal, 'exit_offset_percent') and signal.exit_offset_percent > 0.01:
                offset = 1.0 - signal.exit_offset_percent
                print(f"[Warrior] Using escalating offset: {signal.exit_offset_percent*100:.0f}% below bid")
            elif reason in ("mental_stop", "technical_stop", "breakout_failure", "time_stop", "spread_exit", "after_hours_exit"):
                offset = 0.99
            else:
                offset = 0.995
            
            limit_price = round(current_price * offset, 2)
            
            order = alpaca.submit_order(
                client_order_id=uuid4(),
                symbol=symbol,
                quantity=shares,
                side="sell",
                order_type="limit",
                limit_price=Decimal(str(limit_price)),
                extended_hours=True,
            )
            print(f"[Warrior] Exit LIMIT order submitted: {symbol} x{shares} @ ${limit_price:.2f} ({reason})")
            
            # Poll for actual fill price (up to 2 seconds)
            actual_fill_price = None
            order_id = str(order.id) if hasattr(order, 'id') else None
            if order_id:
                import asyncio
                for _ in range(4):  # 4 attempts, 500ms each = 2 seconds max
                    await asyncio.sleep(0.5)
                    try:
                        filled_order = alpaca.get_order(order_id)
                        if hasattr(filled_order, 'filled_avg_price') and filled_order.filled_avg_price:
                            actual_fill_price = float(filled_order.filled_avg_price)
                            print(f"[Warrior] {symbol} filled @ ${actual_fill_price:.2f}")
                            break
                        if hasattr(filled_order, 'status') and filled_order.status in ('filled', 'partially_filled'):
                            if filled_order.filled_avg_price:
                                actual_fill_price = float(filled_order.filled_avg_price)
                                print(f"[Warrior] {symbol} filled @ ${actual_fill_price:.2f}")
                                break
                    except Exception as poll_err:
                        print(f"[Warrior] Poll error: {poll_err}")
                        break
            
            # Use actual fill price if available, else fall back to limit price
            exit_price = actual_fill_price if actual_fill_price else float(limit_price)
            
            try:
                from nexus2.db.warrior_db import log_warrior_exit
                log_warrior_exit(position_id, exit_price, reason, shares)
            except Exception as e:
                print(f"[Warrior] Exit DB log failed: {e}")
            
            # Return dict with actual exit price so monitor can log accurate P&L
            return {"order": order, "actual_exit_price": exit_price}
        except Exception as e:
            print(f"[Warrior] Exit order failed: {e}")
            return None
    
    # Wire up monitor callbacks
    from nexus2.domain.automation.warrior_monitor import get_warrior_monitor
    monitor = get_warrior_monitor()
    monitor._execute_exit = broker_execute_exit
    
    async def broker_get_positions_async():
        """Async wrapper for broker.get_positions() for monitor sync."""
        try:
            positions = broker.get_positions()
            return [
                {"symbol": symbol, "qty": pos.quantity, "avg_price": pos.avg_price}
                for symbol, pos in positions.items()
            ]
        except Exception as e:
            print(f"[Warrior] Error getting broker positions: {e}")
            return None
    
    monitor.set_callbacks(
        get_broker_positions=broker_get_positions_async,
        get_prices_batch=broker_get_quotes_batch,
        get_price=broker_get_quote,
        get_quote_with_spread=broker_get_quote_with_spread,
        execute_exit=broker_execute_exit,
        get_intraday_candles=broker_get_intraday_bars,  # For technical stop calculation
        submit_scale_order=broker_submit_order,  # Reuse for scaling
    )
    
    engine.set_callbacks(
        submit_order=broker_submit_order,
        get_quote=broker_get_quote,
        get_quote_with_spread=broker_get_quote_with_spread,
        get_positions=broker_get_positions,
        check_pending_fill=check_pending_fill,
        get_intraday_bars=broker_get_intraday_bars,  # For technical entry validation
    )
    
    # Sync existing Alpaca positions to Monitor for restart recovery
    from nexus2.db.warrior_db import init_warrior_db, get_warrior_trade_by_symbol, close_orphaned_trades
    init_warrior_db()
    
    try:
        from nexus2.domain.automation.warrior_monitor import WarriorPosition
        from datetime import datetime
        
        alpaca_positions = broker.get_positions()
        print(f"[Warrior] Found {len(alpaca_positions)} Alpaca positions to sync")
        
        active_symbols = set(alpaca_positions.keys())
        close_orphaned_trades(active_symbols)
        
        synced_count = 0
        
        for symbol, pos in alpaca_positions.items():
            existing = [p for p in monitor.get_positions() if p.symbol == symbol]
            if existing:
                print(f"[Warrior] {symbol} already in monitor, skipping")
                continue
            
            saved_trade = get_warrior_trade_by_symbol(symbol)
            
            if saved_trade:
                entry_price = float(saved_trade["entry_price"])
                stop_price = float(saved_trade["stop_price"])
                target_price = float(saved_trade["target_price"]) if saved_trade["target_price"] else None
                support_level = float(saved_trade["support_level"]) if saved_trade["support_level"] else stop_price
                trade_id = saved_trade["id"]
                partial_taken = saved_trade.get("partial_taken", False)
                
                if partial_taken and stop_price < entry_price:
                    print(f"[Warrior] {symbol}: Partial taken, moving stop to breakeven (${entry_price:.2f})")
                    stop_price = entry_price
                
                print(f"[Warrior] Recovered {symbol} from DB: entry=${entry_price:.2f}, stop=${stop_price:.2f}")
            else:
                entry_price = float(pos.avg_price)
                mental_stop_cents = float(monitor.settings.mental_stop_cents)
                profit_target_r = float(monitor.settings.profit_target_r)
                
                # Try technical stop calculation using candle data
                stop_price = None
                stop_method = "fallback_15c"
                
                try:
                    candles = await broker_get_intraday_bars(symbol, "5min", limit=50)
                    if candles and len(candles) >= 5:
                        from nexus2.domain.indicators import get_stop_calculator
                        stop_calc = get_stop_calculator()
                        candle_dicts = [
                            {"high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
                            for c in candles
                        ]
                        stop_price, stop_method = stop_calc.get_best_stop(
                            candle_dicts, Decimal(str(entry_price)), symbol
                        )
                        stop_price = float(stop_price)
                        
                        # Check if already below stop - EXIT IMMEDIATELY if underwater
                        current_price = float(pos.current_price) if pos.current_price else 0
                        if current_price > 0 and current_price < stop_price:
                            print(f"[Warrior] {symbol}: UNDERWATER (${current_price:.2f} < stop ${stop_price:.2f} via {stop_method}) - EXITING NOW")
                            # Cancel any existing sell orders first
                            try:
                                cancelled = broker.cancel_open_orders(symbol, side="sell")
                                if cancelled > 0:
                                    print(f"[Warrior] {symbol}: Cancelled {cancelled} stale sell order(s)")
                            except Exception as cancel_err:
                                print(f"[Warrior] {symbol}: Cancel orders failed: {cancel_err}")
                            # Submit immediate exit at market-like limit
                            try:
                                exit_price = round(current_price * 0.98, 2)  # Aggressive limit, rounded
                                result = await broker_submit_order(
                                    symbol=symbol,
                                    shares=pos.quantity,
                                    side="sell",
                                    limit_price=exit_price,
                                )
                                print(f"[Warrior] {symbol}: Emergency exit order submitted @ ${exit_price:.2f}")
                            except Exception as exit_err:
                                print(f"[Warrior] {symbol}: Emergency exit failed: {exit_err}")
                            continue
                except Exception as e:
                    print(f"[Warrior] {symbol}: Technical stop calc failed: {e}")
                
                if stop_price is None:
                    stop_price = entry_price - (mental_stop_cents / 100)
                    stop_method = "fallback_15c"
                
                target_price = entry_price + (mental_stop_cents / 100 * profit_target_r)
                support_level = stop_price
                trade_id = str(uuid4())
                print(f"[Warrior] Synced {symbol}: entry=${entry_price:.2f}, stop=${stop_price:.2f} via {stop_method}")
            
            risk_per_share = Decimal(str(entry_price)) - Decimal(str(stop_price))
            new_pos = WarriorPosition(
                position_id=trade_id,
                symbol=symbol,
                entry_price=Decimal(str(entry_price)),
                shares=pos.quantity,
                entry_time=datetime.utcnow(),
                mental_stop=Decimal(str(stop_price)),
                technical_stop=Decimal(str(support_level)),
                current_stop=Decimal(str(stop_price)),
                profit_target=Decimal(str(target_price)) if target_price else Decimal("0"),
                risk_per_share=risk_per_share,
                high_since_entry=Decimal(str(entry_price)),
            )
            monitor._positions[trade_id] = new_pos
            synced_count += 1
            
            # Persist to DB so future syncs don't need to recalculate technical stop
            if not saved_trade:
                from nexus2.db.warrior_db import log_warrior_entry
                log_warrior_entry(
                    trade_id=trade_id,
                    symbol=symbol,
                    entry_price=entry_price,
                    quantity=pos.quantity,
                    stop_price=stop_price,
                    target_price=target_price,
                    trigger_type="synced",
                    support_level=support_level,
                )
        
        if synced_count > 0:
            print(f"[Warrior] Synced {synced_count} positions from Alpaca to Monitor")
        else:
            print(f"[Warrior] No new positions to sync")
    except Exception as e:
        import traceback
        print(f"[Warrior] Position sync failed: {e}")
        traceback.print_exc()
    
    return {
        "status": "enabled",
        "broker": "alpaca_paper_b",
        "account_value": account_value,
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
    
    # Wire callbacks and sync positions using shared function
    try:
        result = await wire_warrior_callbacks(broker)
        result["message"] = "WarriorEngine connected to Alpaca Account B (paper)"
        return result
    except Exception as e:
        _warrior_alpaca_broker = None
        raise HTTPException(status_code=500, detail=str(e))


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


@router.post("/db/backfill")
async def backfill_warrior_trades():
    """
    Backfill synced positions into the Warrior trade log.
    
    Creates DB records for positions that were synced from Alpaca
    but don't have trade log entries (e.g., opened before DB was set up).
    """
    from nexus2.db.warrior_db import log_warrior_entry, get_warrior_trade_by_symbol
    from nexus2.domain.automation.warrior_monitor import get_warrior_monitor
    from uuid import uuid4
    
    monitor = get_warrior_monitor()
    positions = monitor.get_positions()
    
    backfilled = []
    skipped = []
    
    for pos in positions:
        symbol = pos.symbol
        
        # Check if already in DB
        existing = get_warrior_trade_by_symbol(symbol)
        if existing:
            skipped.append(symbol)
            continue
        
        # Create DB record
        try:
            trade_id = str(uuid4())
            log_warrior_entry(
                trade_id=trade_id,
                symbol=symbol,
                entry_price=float(pos.entry_price),
                quantity=pos.shares,
                stop_price=float(pos.mental_stop),
                target_price=float(pos.profit_target),
                trigger_type="backfill",  # Mark as backfilled
                support_level=float(pos.technical_stop) if pos.technical_stop else None,
            )
            backfilled.append({
                "symbol": symbol,
                "entry_price": float(pos.entry_price),
                "stop_price": float(pos.mental_stop),
                "shares": pos.shares,
            })
        except Exception as e:
            print(f"[Warrior] Backfill failed for {symbol}: {e}")
    
    return {
        "status": "completed",
        "backfilled": backfilled,
        "skipped": skipped,
        "message": f"Backfilled {len(backfilled)} trades, skipped {len(skipped)} existing",
    }


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


# =============================================================================
# CANCEL ORDERS ENDPOINT
# =============================================================================

@router.delete("/orders/{symbol}", response_model=dict)
async def cancel_orders_for_symbol(symbol: str):
    """
    Cancel all open orders for a symbol.
    
    This cancels both entry and exit orders for the specified symbol.
    Useful for manual intervention when an order is stuck or unwanted.
    
    Args:
        symbol: Stock symbol (case-insensitive)
    
    Returns:
        List of cancelled order IDs
    """
    from nexus2.domain.automation.warrior_engine import get_warrior_engine
    
    engine = get_warrior_engine()
    if not engine:
        raise HTTPException(status_code=500, detail="Warrior engine not initialized")
    
    symbol = symbol.upper()
    
    # Check if engine has broker access
    if not engine.broker:
        raise HTTPException(status_code=400, detail="No broker configured")
    
    try:
        cancelled = []
        
        # Get all open orders from Alpaca
        orders = engine.broker.get_open_orders()
        
        for order in orders:
            order_symbol = getattr(order, 'symbol', None) or order.get('symbol', '')
            if order_symbol.upper() == symbol:
                order_id = getattr(order, 'id', None) or order.get('id', '')
                try:
                    engine.broker.cancel_order(order_id)
                    cancelled.append(str(order_id))
                    print(f"[Warrior] Cancelled order {order_id} for {symbol}")
                except Exception as e:
                    print(f"[Warrior] Failed to cancel order {order_id}: {e}")
        
        # Also clear pending exit status if cancelling exit orders
        if cancelled:
            try:
                from nexus2.db.warrior_db import get_warrior_trade_by_symbol, update_warrior_status
                from nexus2.domain.positions.position_state_machine import PositionStatus
                trade = get_warrior_trade_by_symbol(symbol)
                if trade and trade["status"] == PositionStatus.PENDING_EXIT.value:
                    # Revert to OPEN since exit was cancelled
                    update_warrior_status(trade["id"], PositionStatus.OPEN.value)
                    print(f"[Warrior] {symbol}: PENDING_EXIT → OPEN (exit cancelled)")
            except Exception as e:
                print(f"[Warrior] Failed to update status after cancel: {e}")
        
        return {
            "status": "success" if cancelled else "no_orders",
            "symbol": symbol,
            "cancelled_count": len(cancelled),
            "cancelled_order_ids": cancelled,
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel orders: {e}")


# =============================================================================
# TRADE HISTORY ENDPOINTS
# =============================================================================

@router.get("/trades", response_model=dict)
async def get_trade_history(limit: int = 50, status: str = None):
    """
    Get Warrior trade history with summary statistics.
    
    Args:
        limit: Maximum trades to return (default 50)
        status: Filter by status ('open', 'closed', or None for all)
    
    Returns:
        trades: List of trades
        summary: Win rate, total P&L, trade counts
    """
    from nexus2.db.warrior_db import get_all_warrior_trades
    
    result = get_all_warrior_trades(limit=limit, status_filter=status)
    return result


@router.get("/trades/{trade_id}", response_model=dict)
async def get_trade_detail(trade_id: str):
    """
    Get a single trade by ID.
    
    Args:
        trade_id: Trade UUID
    
    Returns:
        Trade details or 404
    """
    from nexus2.db.warrior_db import get_trade_by_id
    
    trade = get_trade_by_id(trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")
    
    return {"trade": trade}


# =============================================================================
# INCLUDE SUB-ROUTERS
# =============================================================================

# Import and include sub-routers (extracted from this file)
from .warrior_sim_routes import sim_router
from .warrior_broker_routes import broker_router
from .warrior_positions import positions_router

router.include_router(sim_router)
router.include_router(broker_router)
router.include_router(positions_router)
