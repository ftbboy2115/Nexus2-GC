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
    partial_exit_fraction: Optional[float] = Field(None, description="Partial exit % (default 0.5)")


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
