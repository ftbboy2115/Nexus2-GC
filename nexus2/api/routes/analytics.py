"""
Analytics API Routes

Endpoints for trading performance analytics.
Now queries database directly instead of in-memory PositionService.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from fastapi import APIRouter, Query, Depends

from nexus2.db import SessionLocal, PositionRepository

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _get_positions_from_db(source: Optional[str] = None, status: Optional[str] = None) -> List[dict]:
    """
    Get positions from database with optional filters.
    
    Args:
        source: 'nac', 'manual', 'external', or None for all
        status: 'open', 'closed', or None for all
        
    Returns:
        List of position dicts with calculated P&L
    """
    db = SessionLocal()
    try:
        repo = PositionRepository(db)
        positions = repo.get_by_source(source=source, status=status)
        
        # Convert to dicts and calculate P&L
        result = []
        for p in positions:
            data = p.to_dict()
            
            # Calculate realized P&L if we have exit price
            if p.exit_price and p.entry_price:
                try:
                    entry = Decimal(p.entry_price)
                    exit = Decimal(p.exit_price)
                    shares = p.shares or 0
                    pnl = (exit - entry) * shares
                    data["calculated_pnl"] = float(pnl)
                except:
                    data["calculated_pnl"] = 0
            else:
                data["calculated_pnl"] = float(Decimal(p.realized_pnl or "0"))
            
            result.append(data)
        
        return result
    finally:
        db.close()


@router.get("/summary")
async def get_summary(
    source: Optional[str] = Query(None, description="Filter by source: nac, manual, external, or all (default)"),
    start_date: Optional[date] = Query(None, description="Start date filter"),
    end_date: Optional[date] = Query(None, description="End date filter"),
):
    """
    Get overall trading statistics.
    
    Now queries database directly with source filtering.
    """
    positions = _get_positions_from_db(source=source, status="closed")
    
    # Filter by date if specified
    if start_date:
        positions = [p for p in positions if p.get("opened_at") and p["opened_at"][:10] >= str(start_date)]
    if end_date:
        positions = [p for p in positions if p.get("opened_at") and p["opened_at"][:10] <= str(end_date)]
    
    if not positions:
        return {
            "status": "success",
            "stats": {
                "total_trades": 0,
                "win_rate": 0,
                "net_profit": 0,
                "avg_profit": 0,
                "avg_loss": 0,
                "expectancy": 0,
            },
            "filter": {"source": source or "all"},
        }
    
    # Calculate stats
    total = len(positions)
    winners = [p for p in positions if p["calculated_pnl"] > 0]
    losers = [p for p in positions if p["calculated_pnl"] < 0]
    
    win_rate = len(winners) / total * 100 if total > 0 else 0
    net_profit = sum(p["calculated_pnl"] for p in positions)
    avg_profit = sum(p["calculated_pnl"] for p in winners) / len(winners) if winners else 0
    avg_loss = sum(p["calculated_pnl"] for p in losers) / len(losers) if losers else 0
    expectancy = (win_rate/100 * avg_profit) + ((1 - win_rate/100) * avg_loss)
    
    return {
        "status": "success",
        "stats": {
            "total_trades": total,
            "win_count": len(winners),
            "loss_count": len(losers),
            "win_rate": round(win_rate, 1),
            "net_profit": round(net_profit, 2),
            "avg_profit": round(avg_profit, 2),
            "avg_loss": round(avg_loss, 2),
            "expectancy": round(expectancy, 2),
        },
        "filter": {"source": source or "all"},
    }


@router.get("/by-setup")
async def get_by_setup(
    source: Optional[str] = Query(None, description="Filter by source: nac, manual, external"),
):
    """
    Get stats grouped by setup type (EP, breakout, flag, etc).
    """
    positions = _get_positions_from_db(source=source, status="closed")
    
    if not positions:
        return {"status": "success", "by_setup": [], "filter": {"source": source or "all"}}
    
    # Group by setup type
    setup_groups = {}
    for p in positions:
        setup = p.get("setup_type") or "unknown"
        if setup not in setup_groups:
            setup_groups[setup] = []
        setup_groups[setup].append(p)
    
    # Calculate stats per setup
    by_setup = []
    for setup_type, trades in setup_groups.items():
        total = len(trades)
        winners = [t for t in trades if t["calculated_pnl"] > 0]
        net_pnl = sum(t["calculated_pnl"] for t in trades)
        
        by_setup.append({
            "setup_type": setup_type,
            "count": total,
            "win_rate": round(len(winners) / total * 100, 1) if total > 0 else 0,
            "net_profit": round(net_pnl, 2),
        })
    
    # Sort by count descending
    by_setup.sort(key=lambda x: x["count"], reverse=True)
    
    return {
        "status": "success",
        "by_setup": by_setup,
        "filter": {"source": source or "all"},
    }


@router.get("/quick-stats")
async def get_quick_stats(
    source: Optional[str] = Query(None, description="Filter by source: nac, manual, external"),
):
    """
    Get quick stats for dashboard display.
    
    Returns only key metrics for fast rendering.
    """
    positions = _get_positions_from_db(source=source, status="closed")
    
    if not positions:
        return {
            "total_trades": 0,
            "win_rate": 0,
            "net_profit": 0,
            "avg_r": 0,
            "source": source or "all",
        }
    
    total = len(positions)
    winners = [p for p in positions if p["calculated_pnl"] > 0]
    net_pnl = sum(p["calculated_pnl"] for p in positions)
    
    return {
        "total_trades": total,
        "win_rate": round(len(winners) / total * 100, 1) if total > 0 else 0,
        "net_profit": round(net_pnl, 2),
        "avg_r": 0,  # TODO: Calculate R-multiple when risk data available
        "source": source or "all",
    }


@router.get("/trades")
async def get_trade_history(
    source: Optional[str] = Query(None, description="Filter by source: nac, manual, external"),
    status: Optional[str] = Query(None, description="Filter by status: open, closed"),
    limit: int = Query(100, description="Max results"),
):
    """
    Get trade history with P&L data.
    
    New endpoint for browsing individual trades.
    """
    db = SessionLocal()
    try:
        repo = PositionRepository(db)
        positions = repo.get_by_source(source=source, status=status, limit=limit)
        
        trades = []
        for p in positions:
            # Calculate P&L
            pnl = 0
            if p.exit_price and p.entry_price:
                try:
                    entry = Decimal(p.entry_price)
                    exit = Decimal(p.exit_price)
                    pnl = float((exit - entry) * (p.shares or 0))
                except:
                    pass
            else:
                pnl = float(Decimal(p.realized_pnl or "0"))
            
            trades.append({
                "id": p.id,
                "symbol": p.symbol,
                "setup_type": p.setup_type,
                "source": p.source,
                "status": p.status,
                "entry_price": p.entry_price,
                "exit_price": p.exit_price,
                "shares": p.shares,
                "pnl": round(pnl, 2),
                "opened_at": p.opened_at.isoformat() if p.opened_at else None,
                "closed_at": p.closed_at.isoformat() if p.closed_at else None,
                "exit_date": p.exit_date.isoformat() if p.exit_date else None,
                "quality_score": p.quality_score,
                "tier": p.tier,
            })
        
        return {
            "status": "success",
            "trades": trades,
            "count": len(trades),
            "filter": {"source": source or "all", "status": status or "all"},
        }
    finally:
        db.close()
