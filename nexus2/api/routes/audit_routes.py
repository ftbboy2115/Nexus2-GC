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


# =========================================================================
# Pending Approvals Endpoints
# =========================================================================

@router.get("/pending")
async def get_pending_approvals():
    """Get all pending quote divergence approvals."""
    from nexus2.domain.audit.pending_approvals import get_pending_queue
    
    queue = get_pending_queue()
    pending = queue.get_all_pending()
    
    return {
        "pending": [
            {
                "symbol": a.symbol,
                "time_window": a.time_window,
                "alpaca_price": a.alpaca_price,
                "fmp_price": a.fmp_price,
                "divergence_pct": a.divergence_pct,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "expires_at": a.expires_at.isoformat() if a.expires_at else None,
                "status": a.status.value,
            }
            for a in pending
        ],
        "count": len(pending),
    }


@router.post("/approve/{symbol}/fmp")
async def approve_fmp(symbol: str):
    """Approve FMP as source for symbol."""
    from nexus2.domain.audit.pending_approvals import get_pending_queue, ApprovalStatus
    
    queue = get_pending_queue()
    approval = queue.resolve(symbol, ApprovalStatus.APPROVED_FMP, selected_source="FMP")
    
    if approval:
        return {"approved": True, "symbol": symbol, "source": "FMP"}
    return {"approved": False, "error": "No pending approval for symbol"}


@router.post("/approve/{symbol}/alpaca")
async def approve_alpaca(symbol: str):
    """Approve Alpaca as source for symbol."""
    from nexus2.domain.audit.pending_approvals import get_pending_queue, ApprovalStatus
    
    queue = get_pending_queue()
    approval = queue.resolve(symbol, ApprovalStatus.APPROVED_ALPACA, selected_source="Alpaca")
    
    if approval:
        return {"approved": True, "symbol": symbol, "source": "Alpaca"}
    return {"approved": False, "error": "No pending approval for symbol"}


# =========================================================================
# Blacklist Endpoints
# =========================================================================

@router.get("/blacklist")
async def get_blacklist():
    """Get current symbol blacklist."""
    from nexus2.domain.audit.symbol_blacklist import get_symbol_blacklist
    
    blacklist = get_symbol_blacklist()
    entries = blacklist.get_all()
    
    return {
        "entries": [e.to_dict() for e in entries],
        "count": len(entries),
    }


@router.post("/blacklist/{symbol}")
async def add_to_blacklist(
    symbol: str,
    duration: str = Query("1hour", description="Duration: 10min, 30min, 1hour, 2hours, 3hours, 4hours, today"),
    reason: str = Query("manual", description="Reason for blacklisting"),
):
    """Add symbol to blacklist."""
    from nexus2.domain.audit.symbol_blacklist import get_symbol_blacklist, SKIP_DURATIONS
    
    if duration not in SKIP_DURATIONS:
        return {"error": f"Invalid duration. Valid: {list(SKIP_DURATIONS.keys())}"}
    
    blacklist = get_symbol_blacklist()
    entry = blacklist.add(symbol=symbol, duration_key=duration, reason=reason)
    
    return {
        "added": True,
        "symbol": symbol.upper(),
        "duration": duration,
        "expires_at": entry.expires_at.isoformat() if entry.expires_at else None,
    }


@router.delete("/blacklist/{symbol}")
async def remove_from_blacklist(symbol: str):
    """Remove symbol from blacklist."""
    from nexus2.domain.audit.symbol_blacklist import get_symbol_blacklist
    
    blacklist = get_symbol_blacklist()
    removed = blacklist.remove(symbol)
    
    return {"removed": removed, "symbol": symbol.upper()}

