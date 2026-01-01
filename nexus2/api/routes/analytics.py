"""
Analytics API Routes

Endpoints for trading performance analytics.
"""

from datetime import date
from typing import Optional, List
from fastapi import APIRouter, Query, Depends

from nexus2.domain.analytics import AnalyticsService, get_analytics_service
from nexus2.domain.positions.position_service import PositionService

router = APIRouter(prefix="/analytics", tags=["analytics"])


def get_position_service() -> PositionService:
    """Get singleton position service."""
    from nexus2.domain.positions.position_service import get_position_service
    return get_position_service()


@router.get("/summary")
async def get_summary(
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
    analytics: AnalyticsService = Depends(get_analytics_service),
    positions: PositionService = Depends(get_position_service),
):
    """
    Get overall trading statistics.
    
    Returns win rate, expectancy, R-multiple, drawdown, etc.
    """
    # Get all trades from position service
    trades = positions.get_all_trades()
    
    stats = analytics.calculate_stats(
        trades=trades,
        start_date=start_date,
        end_date=end_date,
    )
    
    return {
        "status": "success",
        "stats": stats.to_dict(),
    }


@router.get("/by-setup")
async def get_by_setup(
    analytics: AnalyticsService = Depends(get_analytics_service),
    positions: PositionService = Depends(get_position_service),
):
    """
    Get stats grouped by setup type (EP, breakout, flag, etc).
    """
    trades = positions.get_all_trades()
    setup_stats = analytics.calculate_by_setup(trades)
    
    return {
        "status": "success",
        "by_setup": [
            {
                "setup_type": ss.setup_type,
                "stats": ss.stats.to_dict(),
            }
            for ss in setup_stats
        ],
    }


@router.get("/kk-comparison")
async def get_kk_comparison(
    analytics: AnalyticsService = Depends(get_analytics_service),
    positions: PositionService = Depends(get_position_service),
):
    """
    Compare KK-style trades (single stop) vs non-KK (dual-stop).
    
    Uses use_dual_stops field on trades to differentiate.
    """
    trades = positions.get_all_trades()
    comparison = analytics.compare_kk_vs_non_kk(trades)
    
    return {
        "status": "success",
        "kk_style": {
            "description": "Single LOD stop (pure KK methodology)",
            "stats": comparison.kk_style.to_dict(),
        },
        "non_kk_style": {
            "description": "Dual-stop with invalidation level (experimental)",
            "stats": comparison.non_kk_style.to_dict(),
        },
    }


@router.get("/quick-stats")
async def get_quick_stats(
    positions: PositionService = Depends(get_position_service),
):
    """
    Get quick stats for dashboard display.
    
    Returns only key metrics for fast rendering.
    """
    trades = positions.get_all_trades()
    closed = [t for t in trades if t.status in ("closed", "stopped_out")]
    
    if not closed:
        return {
            "total_trades": 0,
            "win_rate": 0,
            "net_profit": 0,
            "avg_r": 0,
        }
    
    winners = len([t for t in closed if t.realized_pnl > 0])
    total = len(closed)
    net_pnl = sum(t.realized_pnl for t in closed)
    
    # Calculate avg R
    r_values = []
    for t in closed:
        if t.initial_risk_dollars and t.initial_risk_dollars > 0:
            r_values.append(t.realized_pnl / t.initial_risk_dollars)
    avg_r = sum(r_values) / len(r_values) if r_values else 0
    
    return {
        "total_trades": total,
        "win_rate": round(winners / total * 100, 1) if total > 0 else 0,
        "net_profit": float(net_pnl),
        "avg_r": round(float(avg_r), 2),
    }
