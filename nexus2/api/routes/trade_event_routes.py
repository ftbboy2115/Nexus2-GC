"""
Trade Event Routes

API endpoints for querying trade management events.
"""

from fastapi import APIRouter, Query
from typing import Optional

from nexus2.domain.automation.trade_event_service import trade_event_service


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
