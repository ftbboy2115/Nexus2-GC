"""
Warrior Positions Routes

Position management, watchlist, diagnostics, and manual exit endpoints.
"""

from decimal import Decimal
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field


# =============================================================================
# ROUTER
# =============================================================================

positions_router = APIRouter(tags=["warrior-positions"])


# =============================================================================
# REQUEST MODELS
# =============================================================================

class ManualExitRequest(BaseModel):
    """Request to manually exit a position."""
    symbol: str
    limit_price: float = Field(..., description="Limit price for the sell order")
    shares: Optional[int] = Field(None, description="Shares to sell (default: all)")


# =============================================================================
# POSITIONS & WATCHLIST
# =============================================================================

@positions_router.get("/positions")
async def get_warrior_positions():
    """Get positions being monitored by Warrior engine."""
    from .warrior_routes import get_engine
    
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


@positions_router.get("/positions/count")
async def get_warrior_positions_count():
    """Get count of active Warrior positions."""
    from .warrior_routes import get_engine
    
    engine = get_engine()
    positions = engine.monitor.get_positions()
    
    return {"count": len(positions), "strategy": "Warrior"}


@positions_router.get("/watchlist")
async def get_warrior_watchlist():
    """Get current Warrior watchlist (candidates being watched for entry)."""
    from .warrior_routes import get_engine
    
    engine = get_engine()
    status = engine.get_status()
    
    return {
        "count": status["watchlist_count"],
        "watchlist": status["watchlist"],
    }


# =============================================================================
# DIAGNOSTICS
# =============================================================================

@positions_router.get("/diagnostics")
async def get_warrior_diagnostics():
    """Get detailed diagnostics for Warrior Trading system."""
    from nexus2.domain.automation.rejection_tracker import get_rejection_tracker
    from nexus2.domain.scanner.warrior_scanner_service import get_warrior_scanner_service
    from .warrior_routes import get_engine, get_warrior_scanner_settings, get_warrior_monitor_settings
    
    engine = get_engine()
    scanner = get_warrior_scanner_service()
    tracker = get_rejection_tracker()
    
    warrior_rejections = tracker.get_recent(count=50, scanner="warrior")
    rejection_summary = tracker.get_summary()
    
    return {
        "engine": engine.get_status(),
        "scanner_settings": await get_warrior_scanner_settings(),
        "monitor_settings": await get_warrior_monitor_settings(),
        "rejections": {
            "recent": warrior_rejections[-10:],
            "total_warrior": rejection_summary.get("by_scanner", {}).get("warrior", 0),
            "by_reason": {
                k: v for k, v in rejection_summary.get("by_reason", {}).items()
                if k in ["float_too_high", "rvol_too_low", "no_catalyst", "price_out_of_range"]
            },
        },
    }


# =============================================================================
# MANUAL EXIT
# =============================================================================

@positions_router.post("/manual_exit")
async def manual_exit_position(request: ManualExitRequest):
    """Manually exit a position at specified limit price."""
    import datetime
    from .warrior_routes import get_engine
    from .warrior_broker_routes import get_warrior_alpaca_broker
    
    alpaca = get_warrior_alpaca_broker()
    if alpaca is None:
        raise HTTPException(status_code=400, detail="Warrior broker not enabled")
    
    symbol = request.symbol.upper()
    
    positions = alpaca.get_positions()
    position = None
    for p in positions:
        pos_symbol = p.get("symbol") if isinstance(p, dict) else getattr(p, "symbol", None)
        if pos_symbol == symbol:
            position = p
            break
    
    if position is None:
        raise HTTPException(status_code=404, detail=f"No position found for {symbol}")
    
    if isinstance(position, dict):
        total_shares = int(float(position.get("qty", 0)))
    else:
        total_shares = int(float(getattr(position, "qty", 0)))
    
    shares_to_sell = request.shares if request.shares else total_shares
    
    cancelled = alpaca.cancel_open_orders(symbol, side="sell")
    
    order = alpaca.submit_order(
        client_order_id=uuid4(),
        symbol=symbol,
        quantity=shares_to_sell,
        side="sell",
        order_type="limit",
        limit_price=Decimal(str(request.limit_price)),
        extended_hours=True,
    )
    
    engine = get_engine()
    for pos_id, pos in list(engine.monitor._positions.items()):
        if pos.symbol == symbol:
            engine.monitor.remove_position(pos_id)
            engine.monitor._recently_exited[symbol] = datetime.datetime.utcnow()
            engine.monitor._save_recently_exited()
            break
    
    return {
        "status": "submitted",
        "symbol": symbol,
        "shares": shares_to_sell,
        "limit_price": request.limit_price,
        "cancelled_orders": cancelled,
        "order_id": str(order.client_order_id) if order else None,
    }
