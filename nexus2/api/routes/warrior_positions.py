"""
Warrior Positions Routes

Position management, watchlist, diagnostics, and manual exit endpoints.
"""

import asyncio
import logging
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from nexus2.utils.time_utils import now_utc, format_iso_utc

logger = logging.getLogger(__name__)
# =============================================================================
# ROUTER
# =============================================================================

positions_router = APIRouter()  # No separate tag - inherits from parent 'warrior' router


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
    """Get positions being monitored by Warrior engine with current prices."""
    from .warrior_routes import get_engine
    from nexus2.api.routes.warrior_sim_routes import get_warrior_sim_broker
    
    engine = get_engine()
    positions = engine.monitor.get_positions()
    
    # Get current prices - check sim mode first to avoid live API calls
    current_prices = {}
    mock_broker = get_warrior_sim_broker()
    
    if mock_broker is not None:
        # SIM MODE: Use MockBroker prices (no live API calls)
        for p in positions:
            price = mock_broker.get_price(p.symbol)
            if price and price > 0:
                current_prices[p.symbol] = float(price)
    else:
        # LIVE MODE: Try broker positions, then fetch quotes
        try:
            broker = engine.broker
            if broker:
                alpaca_positions = broker.get_positions()
                for symbol, pos in alpaca_positions.items():
                    if pos.current_price:
                        current_prices[symbol] = float(pos.current_price)
        except Exception:
            pass  # Continue without current prices if broker unavailable
        
        # Fetch quotes for any positions missing current_price
        # Use UnifiedMarketData for fallback (Alpaca -> FMP -> Schwab) + cross-validation
        # IMPORTANT: Use asyncio.to_thread() because UMD->FMP can block on rate limits
        import asyncio
        from nexus2.adapters.market_data.unified import UnifiedMarketData
        umd = UnifiedMarketData()
        for p in positions:
            if p.symbol not in current_prices:
                try:
                    quote = await asyncio.to_thread(umd.get_quote, p.symbol)
                    if quote and quote.price > 0:
                        current_prices[p.symbol] = float(quote.price)
                except Exception:
                    pass  # Continue without this quote
    
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
                "entry_time": format_iso_utc(p.entry_time),
                "current_price": current_prices.get(p.symbol),
            }
            for p in positions
        ],
    }


@positions_router.get("/positions/health")
async def get_positions_health():
    """
    Get health indicators for all open positions.
    
    Fetches 1-min candles, aggregates to 5-min, and computes:
    - MACD, 9/20 EMA, VWAP from intraday technicals
    - Stop distance and target progress from position data
    
    Returns traffic light indicators (green/yellow/red) for each position.
    """
    from .warrior_routes import get_engine
    from nexus2.api.routes.warrior_sim_routes import get_warrior_sim_broker
    from nexus2.domain.automation.indicator_service import get_indicator_service
    
    engine = get_engine()
    positions = engine.monitor.get_positions()
    
    if not positions:
        return {"count": 0, "positions": []}
    
    # SIM MODE: Return simplified health data without FMP/Alpaca API calls
    mock_broker = get_warrior_sim_broker()
    if mock_broker is not None:
        indicator_service = get_indicator_service()
        result = []
        for p in positions:
            # Get current price from MockBroker
            current_price = mock_broker.get_price(p.symbol) or float(p.entry_price)
            
            # Compute basic health without live technicals
            health = indicator_service.compute_position_health(
                current_price=float(current_price),
                entry_price=float(p.entry_price),
                stop_price=float(p.current_stop),
                target_price=float(p.profit_target),
            )
            result.append({
                "position_id": p.position_id,
                "symbol": p.symbol,
                "health": health.to_dict(),
            })
        return {"count": len(result), "positions": result}
    
    # LIVE MODE: Full health indicators with Polygon intraday data (unlimited calls)
    from nexus2.adapters.market_data.polygon_adapter import PolygonAdapter
    from nexus2.domain.indicators import get_technical_service
    from nexus2.domain.automation.indicator_service import aggregate_candles_to_timeframe
    
    polygon = PolygonAdapter()
    tech_service = get_technical_service()
    indicator_service = get_indicator_service()
    
    result = []
    for p in positions:
        try:
            # Fetch 1-min candles from Polygon (unlimited calls, faster than FMP)
            # Need 200 bars for MACD (26-period slow EMA) after 5-min aggregation
            candles_1min = await asyncio.to_thread(polygon.get_intraday_bars, p.symbol, "1", 200)
            
            if not candles_1min or len(candles_1min) < 30:
                # Not enough intraday data - use fallback price sources
                # Priority: high_since_entry -> quote API -> entry_price
                current_price = float(p.high_since_entry) if p.high_since_entry else 0
                
                if current_price <= 0:
                    # Try to get a quote from Polygon
                    try:
                        quote = await asyncio.to_thread(polygon.get_quote, p.symbol)
                        if quote and quote.price > 0:
                            current_price = float(quote.price)
                    except Exception:
                        pass
                
                if current_price <= 0:
                    # Ultimate fallback: use entry price (better than 0)
                    current_price = float(p.entry_price)
                
                health = indicator_service.compute_position_health(
                    current_price=current_price,
                    entry_price=float(p.entry_price),
                    stop_price=float(p.current_stop),
                    target_price=float(p.profit_target),
                )
            else:
                # Aggregate to 5-min for smoother EMA/MACD
                candles_5min = aggregate_candles_to_timeframe(
                    [{"open": float(c.open), "high": float(c.high), 
                      "low": float(c.low), "close": float(c.close), 
                      "volume": c.volume} for c in candles_1min],
                    target_minutes=5,
                )
                
                # Get current price from latest candle
                current_price = float(candles_1min[-1].close)
                
                # Compute volume ratio (current bar vs average)
                volumes = [c.volume for c in candles_1min if c.volume > 0]
                volume_ratio = None
                if len(volumes) > 10:
                    avg_vol = sum(volumes[:-1]) / len(volumes[:-1])  # Exclude current bar
                    if avg_vol > 0:
                        volume_ratio = volumes[-1] / avg_vol
                
                # Compute 200 EMA from daily bars (needs ~250 bars for accuracy)
                ema200 = None
                try:
                    daily_bars = await asyncio.to_thread(polygon.get_daily_bars, p.symbol, 250)
                    if daily_bars and len(daily_bars) >= 200:
                        closes = [float(b.close) for b in daily_bars]
                        # Simple EMA calculation
                        multiplier = 2 / (200 + 1)
                        ema = sum(closes[:200]) / 200  # Initial SMA
                        for price in closes[200:]:
                            ema = (price - ema) * multiplier + ema
                        ema200 = ema
                except Exception as e:
                    logger.debug(f"[Health] {p.symbol}: Failed to compute EMA200: {e}")
                
                # Compute technicals from 5-min candles
                tech_snapshot = tech_service.get_snapshot(
                    symbol=p.symbol,
                    candles=candles_5min,
                    current_price=current_price,
                )
                
                # Compute health from technicals
                health = indicator_service.compute_health_from_snapshot(
                    current_price=current_price,
                    entry_price=float(p.entry_price),
                    stop_price=float(p.current_stop),
                    target_price=float(p.profit_target),
                    tech_snapshot=tech_snapshot,
                    volume_ratio=volume_ratio,
                    ema200=ema200,
                )
            
            result.append({
                "position_id": p.position_id,
                "symbol": p.symbol,
                "health": health.to_dict(),
            })
            
        except Exception as e:
            # Log but don't fail entire request
            result.append({
                "position_id": p.position_id,
                "symbol": p.symbol,
                "health": None,
                "error": str(e),
            })
    
    return {"count": len(result), "positions": result}


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
            engine.monitor._recently_exited[symbol] = datetime.now_utc()
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
