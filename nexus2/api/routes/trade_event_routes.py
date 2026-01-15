"""
Trade Event Routes

API endpoints for querying trade management events.
"""

from fastapi import APIRouter, Query
from typing import Optional

from nexus2.domain.automation.trade_event_service import trade_event_service
from nexus2.utils.time_utils import now_utc


router = APIRouter(prefix="/trade-events", tags=["trade-events"])


@router.get("/position/{position_id}")
async def get_position_events(
    position_id: str,
    strategy: Optional[str] = Query(None, description="Filter by strategy (NAC or WARRIOR)"),
):
    """Get all events for a specific position."""
    events = trade_event_service.get_events_for_position(position_id, strategy)
    return {
        "position_id": position_id,
        "strategy": strategy,
        "count": len(events),
        "events": events,
    }


@router.get("/recent")
async def get_recent_events(
    strategy: Optional[str] = Query(None, description="Filter by strategy (NAC or WARRIOR)"),
    limit: int = Query(50, ge=1, le=200, description="Maximum events to return"),
):
    """Get recent trade events across all positions."""
    events = trade_event_service.get_recent_events(strategy, limit)
    return {
        "strategy": strategy,
        "count": len(events),
        "events": events,
    }


@router.get("/symbol/{symbol}")
async def get_symbol_events(
    symbol: str,
    strategy: Optional[str] = Query(None, description="Filter by strategy (NAC or WARRIOR)"),
    limit: int = Query(50, ge=1, le=200, description="Maximum events to return"),
):
    """Get events for a specific symbol across all positions."""
    # Get all recent events and filter by symbol
    all_events = trade_event_service.get_recent_events(strategy, limit=500)
    symbol_events = [e for e in all_events if e["symbol"].upper() == symbol.upper()][:limit]
    return {
        "symbol": symbol.upper(),
        "strategy": strategy,
        "count": len(symbol_events),
        "events": symbol_events,
    }


# =============================================================================
# AI TRADE ANALYSIS
# =============================================================================

@router.post("/analyze/{position_id}")
async def analyze_trade(position_id: str):
    """
    Analyze a completed trade using AI.
    
    Returns grades, summary, lessons learned, and market context impact.
    Uses strategy-specific prompts (Warrior or NAC methodology).
    """
    from nexus2.domain.automation.trade_analysis_service import get_trade_analysis_service
    
    service = get_trade_analysis_service()
    analysis = service.analyze_trade(position_id)
    
    if not analysis:
        return {
            "success": False,
            "error": f"No events found for position {position_id} or analysis failed",
        }
    
    return {
        "success": True,
        "analysis": analysis.to_dict(),
    }


@router.post("/analyze-day")
async def analyze_day_trades(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format (defaults to today)"),
):
    """
    Analyze all closed trades from a specific date using AI.
    
    Returns a consolidated report with individual trade analyses and a session summary.
    """
    from datetime import datetime, date as date_type
    from nexus2.db.warrior_db import get_warrior_trades_by_status
    from nexus2.domain.automation.trade_analysis_service import get_trade_analysis_service
    
    # Determine target date
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            return {"success": False, "error": "Invalid date format. Use YYYY-MM-DD"}
    else:
        target_date = now_utc().date()
    
    # Get all closed trades
    all_closed = get_warrior_trades_by_status("closed")
    
    # Filter to target date
    trades_today = []
    for trade in all_closed:
        exit_time = trade.get("exit_time")
        if exit_time:
            if isinstance(exit_time, str):
                exit_dt = datetime.fromisoformat(exit_time.replace("Z", "+00:00"))
            else:
                exit_dt = exit_time
            if exit_dt.date() == target_date:
                trades_today.append(trade)
    
    if not trades_today:
        return {
            "success": False,
            "error": f"No closed trades found for {target_date}",
            "date": str(target_date),
        }
    
    # Analyze each trade
    service = get_trade_analysis_service()
    analyses = []
    errors = []
    
    for trade in trades_today:
        try:
            analysis = service.analyze_trade(trade["id"])
            if analysis:
                analyses.append({
                    "position_id": trade["id"],
                    "symbol": trade["symbol"],
                    "pnl": trade.get("realized_pnl", "0"),
                    "exit_reason": trade.get("exit_reason"),
                    "analysis": analysis.to_dict(),
                })
            else:
                errors.append(f"{trade['symbol']} ({trade['id'][:8]}): No events found")
        except Exception as e:
            errors.append(f"{trade['symbol']} ({trade['id'][:8]}): {str(e)}")
    
    # Calculate session summary
    total_pnl = sum(float(t.get("realized_pnl", 0) or 0) for t in trades_today)
    winners = len([t for t in trades_today if float(t.get("realized_pnl", 0) or 0) > 0])
    losers = len([t for t in trades_today if float(t.get("realized_pnl", 0) or 0) < 0])
    
    return {
        "success": True,
        "date": str(target_date),
        "summary": {
            "total_trades": len(trades_today),
            "analyzed": len(analyses),
            "errors": len(errors),
            "winners": winners,
            "losers": losers,
            "total_pnl": round(total_pnl, 2),
        },
        "analyses": analyses,
        "error_details": errors if errors else None,
    }

