"""
Data Explorer Routes

API endpoints for the Data Explorer UI - provides paginated, filterable
access to NAC trades and scan history data.
"""

from datetime import date, datetime
from typing import Optional, List
from fastapi import APIRouter, Query

router = APIRouter(prefix="/data", tags=["data-explorer"])


# =============================================================================
# NAC TRADES ENDPOINT
# =============================================================================

@router.get("/nac-trades")
async def get_nac_trades(
    limit: int = Query(50, ge=1, le=500, description="Maximum records to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    status: Optional[str] = Query(None, description="Filter by status: open, pending_fill, pending_exit, closed"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    sort_by: str = Query("created_at", description="Column to sort by"),
    sort_dir: str = Query("desc", description="Sort direction: asc or desc"),
):
    """
    Get paginated NAC trades with filtering and sorting.
    
    Returns:
        trades: List of trade records
        total: Total count for pagination
        limit: Records per page
        offset: Current offset
    """
    from nexus2.db.nac_db import get_nac_session, NACTradeModel
    from sqlalchemy import desc, asc
    
    with get_nac_session() as db:
        query = db.query(NACTradeModel)
        
        # Apply filters
        if status:
            query = query.filter(NACTradeModel.status == status)
        if symbol:
            query = query.filter(NACTradeModel.symbol == symbol.upper())
        
        # Get total count
        total = query.count()
        
        # Apply sorting
        sort_column = getattr(NACTradeModel, sort_by, NACTradeModel.created_at)
        if sort_dir.lower() == "desc":
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(asc(sort_column))
        
        # Apply pagination
        trades = query.offset(offset).limit(limit).all()
        
        return {
            "trades": [t.to_dict() for t in trades],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


# =============================================================================
# SCAN HISTORY ENDPOINT
# =============================================================================

@router.get("/scan-history")
async def get_scan_history(
    limit: int = Query(50, ge=1, le=500, description="Maximum records to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    source: Optional[str] = Query(None, description="Filter by source: scan or backfill"),
    sort_by: str = Query("logged_at", description="Column to sort by"),
    sort_dir: str = Query("desc", description="Sort direction: asc or desc"),
):
    """
    Get paginated scan history with filtering and sorting.
    
    Returns:
        entries: List of scan history records
        total: Total count for pagination
        limit: Records per page
        offset: Current offset
    """
    from nexus2.domain.lab.scan_history_logger import get_scan_history_logger
    
    history = get_scan_history_logger()
    
    # Flatten history into list with date included
    all_entries = []
    for date_str, entries in history._history.items():
        for entry in entries:
            all_entries.append({
                "date": date_str,
                **entry,
            })
    
    # Apply filters
    if date_from:
        all_entries = [e for e in all_entries if e["date"] >= date_from]
    if date_to:
        all_entries = [e for e in all_entries if e["date"] <= date_to]
    if symbol:
        all_entries = [e for e in all_entries if e["symbol"].upper() == symbol.upper()]
    if source:
        all_entries = [e for e in all_entries if e.get("source", "scan") == source]
    
    # Calculate total before pagination
    total = len(all_entries)
    
    # Apply sorting
    reverse = sort_dir.lower() == "desc"
    all_entries.sort(key=lambda x: x.get(sort_by, ""), reverse=reverse)
    
    # Apply pagination
    entries = all_entries[offset:offset + limit]
    
    return {
        "entries": entries,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
