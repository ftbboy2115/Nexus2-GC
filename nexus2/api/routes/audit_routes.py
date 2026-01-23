"""
Quote Audit API Routes

Endpoints for querying quote fidelity audit data, provider reliability,
and managing retention cleanup.
"""

from typing import Optional
from fastapi import APIRouter, Query

from nexus2.domain.audit.quote_audit_service import get_quote_audit_service

router = APIRouter()


@router.get("/quotes/recent")
async def get_recent_audits(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    limit: int = Query(100, description="Maximum records to return", ge=1, le=1000),
):
    """Get recent quote audit logs."""
    service = get_quote_audit_service()
    audits = service.get_recent_audits(symbol=symbol, limit=limit)
    return {"audits": audits, "count": len(audits)}


@router.get("/quotes/stats")
async def get_divergence_stats(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    time_window: Optional[str] = Query(None, description="Filter by time window (premarket_early, regular_hours, etc.)"),
    min_divergence: float = Query(20.0, description="Minimum divergence % to include"),
    days: int = Query(7, description="Lookback period in days", ge=1, le=90),
):
    """Get divergence statistics."""
    service = get_quote_audit_service()
    
    # Get all audits for the period
    from datetime import timedelta
    from nexus2.utils.time_utils import now_utc
    from nexus2.db.database import get_session
    from nexus2.db.models import QuoteAuditModel
    
    cutoff = now_utc() - timedelta(days=days)
    
    with get_session() as session:
        query = session.query(QuoteAuditModel).filter(
            QuoteAuditModel.timestamp >= cutoff
        )
        if symbol:
            query = query.filter(QuoteAuditModel.symbol == symbol.upper())
        if time_window:
            query = query.filter(QuoteAuditModel.time_window == time_window)
        
        records = query.all()
    
    # Calculate stats
    total = len(records)
    high_divergence = sum(1 for r in records if r.high_divergence)
    
    # Get worst offenders
    from collections import defaultdict
    symbol_max = defaultdict(float)
    for r in records:
        div = float(r.divergence_pct) if r.divergence_pct else 0
        if div >= min_divergence:
            if div > symbol_max[r.symbol]:
                symbol_max[r.symbol] = div
    
    worst_symbols = sorted(symbol_max.items(), key=lambda x: x[1], reverse=True)[:10]
    
    return {
        "period_days": days,
        "total_audits": total,
        "high_divergence_count": high_divergence,
        "high_divergence_pct": (high_divergence / total * 100) if total > 0 else 0,
        "worst_symbols": [{"symbol": s, "max_divergence": d} for s, d in worst_symbols],
        "provider_reliability": service.get_provider_reliability(time_window=time_window, days=days),
    }


@router.get("/quotes/providers")
async def get_provider_reliability(
    time_window: Optional[str] = Query(None, description="Filter by time window"),
    days: int = Query(7, description="Lookback period in days", ge=1, le=90),
):
    """Get per-provider reliability metrics."""
    service = get_quote_audit_service()
    reliability = service.get_provider_reliability(time_window=time_window, days=days)
    
    return {
        "period_days": days,
        "time_window": time_window or "all",
        "reliability": reliability,
        "note": "Reliability = % of quotes within 5% of selected price",
    }


@router.get("/quotes/symbols/{symbol}")
async def get_symbol_audits(
    symbol: str,
    limit: int = Query(100, description="Maximum records to return", ge=1, le=1000),
):
    """Get audit history for a specific symbol."""
    service = get_quote_audit_service()
    audits = service.get_recent_audits(symbol=symbol.upper(), limit=limit)
    
    # Calculate symbol-specific stats
    if audits:
        divergences = [float(a.get("divergence_pct", 0)) for a in audits]
        avg_divergence = sum(divergences) / len(divergences)
        max_divergence = max(divergences)
        high_div_count = sum(1 for d in divergences if d > 20)
    else:
        avg_divergence = 0
        max_divergence = 0
        high_div_count = 0
    
    return {
        "symbol": symbol.upper(),
        "audit_count": len(audits),
        "avg_divergence": round(avg_divergence, 2),
        "max_divergence": round(max_divergence, 2),
        "high_divergence_count": high_div_count,
        "audits": audits,
    }


@router.get("/quotes/daily-summary")
async def get_daily_summary():
    """Get daily summary report with top divergences and provider stats."""
    service = get_quote_audit_service()
    summary = service.generate_daily_summary()
    return summary


@router.get("/quotes/recommend-source/{time_window}")
async def recommend_source(time_window: str):
    """
    Get recommended source priority for a time window.
    
    Returns ranked list of providers by historical accuracy.
    Returns null if insufficient data (<7 days history).
    """
    service = get_quote_audit_service()
    priority = service.recommend_source_priority(time_window)
    
    return {
        "time_window": time_window,
        "recommended_priority": priority,
        "note": "None means insufficient historical data" if priority is None else "Ranked by accuracy",
    }


@router.post("/quotes/cleanup")
async def trigger_cleanup(
    retention_days: int = Query(90, description="Delete records older than this many days", ge=1, le=365),
):
    """
    Trigger retention cleanup.
    
    Deletes audit records older than the retention period.
    """
    service = get_quote_audit_service()
    deleted = service.cleanup_old_audits(retention_days=retention_days)
    
    return {
        "deleted_count": deleted,
        "retention_days": retention_days,
        "message": f"Deleted {deleted} records older than {retention_days} days",
    }


@router.get("/quotes/status")
async def get_audit_status():
    """Get audit service status."""
    service = get_quote_audit_service()
    return service.get_status()
