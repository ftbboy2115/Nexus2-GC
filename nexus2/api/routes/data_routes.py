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
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
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
    from sqlalchemy import desc, asc, cast, Float
    
    # Columns stored as strings that need numeric sorting
    NUMERIC_STRING_COLS = {"entry_price", "exit_price", "stop_price", "target_price", "realized_pnl"}
    
    with get_nac_session() as db:
        query = db.query(NACTradeModel)
        
        # Apply filters
        if status:
            query = query.filter(NACTradeModel.status == status)
        if symbol:
            query = query.filter(NACTradeModel.symbol == symbol.upper())
        if date_from:
            query = query.filter(NACTradeModel.entry_time >= date_from)
        if date_to:
            query = query.filter(NACTradeModel.entry_time <= date_to + "T23:59:59")
        
        # Get total count
        total = query.count()
        
        # Apply sorting - cast string columns to float for numeric sort
        sort_column = getattr(NACTradeModel, sort_by, NACTradeModel.created_at)
        if sort_by in NUMERIC_STRING_COLS:
            sort_column = cast(sort_column, Float)
        
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
    catalyst: Optional[str] = Query(None, description="Filter by catalyst type"),
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
    
    # Flatten history into list with date included, ensuring all have source field
    all_entries = []
    for date_str, entries in history._history.items():
        for entry in entries:
            all_entries.append({
                "date": date_str,
                "source": "scan",  # Default value
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
    if catalyst:
        all_entries = [e for e in all_entries if e.get("catalyst", "") == catalyst]
    
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


# =============================================================================
# TRADE EVENTS ENDPOINT (with sorting/filtering)
# =============================================================================

@router.get("/trade-events")
async def get_trade_events(
    limit: int = Query(50, ge=1, le=500, description="Maximum records to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    strategy: Optional[str] = Query(None, description="Filter by strategy: NAC or WARRIOR"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    sort_by: str = Query("timestamp", description="Column to sort by"),
    sort_dir: str = Query("desc", description="Sort direction: asc or desc"),
):
    """
    Get paginated trade events with filtering and sorting.
    """
    from nexus2.domain.automation.trade_event_service import trade_event_service
    
    # Get all events (service returns dicts)
    all_events = trade_event_service.get_recent_events(strategy, limit=500)
    
    # Apply additional filters
    if symbol:
        all_events = [e for e in all_events if e.get("symbol", "").upper() == symbol.upper()]
    if event_type:
        all_events = [e for e in all_events if e.get("event_type") == event_type]
    if date_from:
        all_events = [e for e in all_events if e.get("timestamp", "") >= date_from]
    if date_to:
        all_events = [e for e in all_events if e.get("timestamp", "") <= date_to + "T23:59:59"]
    
    # Get total before pagination
    total = len(all_events)
    
    # Apply sorting
    reverse = sort_dir.lower() == "desc"
    all_events.sort(key=lambda x: x.get(sort_by) or "", reverse=reverse)
    
    # Apply pagination
    events = all_events[offset:offset + limit]
    
    return {
        "events": events,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# =============================================================================
# WARRIOR TRADES ENDPOINT (with sorting/filtering)
# =============================================================================

@router.get("/warrior-trades")
async def get_warrior_trades(
    limit: int = Query(50, ge=1, le=500, description="Maximum records to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    status: Optional[str] = Query(None, description="Filter by status"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    exit_reason: Optional[str] = Query(None, description="Filter by exit reason"),
    trigger_type: Optional[str] = Query(None, description="Filter by trigger type"),
    quote_source: Optional[str] = Query(None, description="Filter by quote source"),
    exit_mode: Optional[str] = Query(None, description="Filter by exit mode"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    sort_by: str = Query("entry_time", description="Column to sort by"),
    sort_dir: str = Query("desc", description="Sort direction: asc or desc"),
):
    """
    Get paginated Warrior trades with filtering and sorting.
    """
    from nexus2.db.warrior_db import get_warrior_session, WarriorTradeModel
    from sqlalchemy import desc, asc
    
    with get_warrior_session() as db:
        query = db.query(WarriorTradeModel)
        
        # Apply filters
        if status:
            query = query.filter(WarriorTradeModel.status == status)
        if symbol:
            query = query.filter(WarriorTradeModel.symbol == symbol.upper())
        if exit_reason:
            query = query.filter(WarriorTradeModel.exit_reason == exit_reason)
        if trigger_type:
            query = query.filter(WarriorTradeModel.trigger_type == trigger_type)
        if quote_source:
            query = query.filter(WarriorTradeModel.quote_source == quote_source)
        if exit_mode:
            query = query.filter(WarriorTradeModel.exit_mode == exit_mode)
        if date_from:
            query = query.filter(WarriorTradeModel.entry_time >= date_from)
        if date_to:
            query = query.filter(WarriorTradeModel.entry_time <= date_to + "T23:59:59")
        
        # Get total count
        total = query.count()
        
        # Apply sorting
        sort_column = getattr(WarriorTradeModel, sort_by, WarriorTradeModel.entry_time)
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

