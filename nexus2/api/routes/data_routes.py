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
    status: Optional[str] = Query(None, description="Filter by status"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    partial_taken: Optional[bool] = Query(None, description="Filter by partial taken"),
    exit_reason: Optional[str] = Query(None, description="Filter by exit reason"),
    setup_type: Optional[str] = Query(None, description="Filter by setup type"),
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
        
        # Apply filters (handle __EMPTY__ for NULL filtering)
        if status:
            if status == '__EMPTY__':
                query = query.filter(NACTradeModel.status == None)
            else:
                query = query.filter(NACTradeModel.status == status)
        if symbol:
            query = query.filter(NACTradeModel.symbol == symbol.upper())
        if partial_taken is not None:
            query = query.filter(NACTradeModel.partial_taken == partial_taken)
        if exit_reason:
            if exit_reason == '__EMPTY__':
                query = query.filter(NACTradeModel.exit_reason == None)
            else:
                query = query.filter(NACTradeModel.exit_reason == exit_reason)
        if setup_type:
            if setup_type == '__EMPTY__':
                query = query.filter(NACTradeModel.setup_type == None)
            else:
                query = query.filter(NACTradeModel.setup_type == setup_type)
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
    sort_by: str = Query("created_at", description="Column to sort by"),
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
    # Date filter uses created_at field (ISO format)
    if date_from:
        all_events = [e for e in all_events if e.get("created_at", "") >= date_from]
    if date_to:
        all_events = [e for e in all_events if e.get("created_at", "") <= date_to + "T23:59:59"]
    
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
    stop_method: Optional[str] = Query(None, description="Filter by stop method"),
    is_sim: Optional[str] = Query(None, description="Filter: 'true'=SIM, 'false'=LIVE, 'null'=Unknown"),
    partial_taken: Optional[str] = Query(None, description="Filter by partial taken: 'true', 'false', or '__EMPTY__' for null"),
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
        
        # Apply filters (handle __EMPTY__ for NULL filtering)
        if status:
            if status == '__EMPTY__':
                query = query.filter(WarriorTradeModel.status == None)
            else:
                query = query.filter(WarriorTradeModel.status == status)
        if symbol:
            query = query.filter(WarriorTradeModel.symbol == symbol.upper())
        if exit_reason:
            if exit_reason == '__EMPTY__':
                query = query.filter(WarriorTradeModel.exit_reason == None)
            else:
                query = query.filter(WarriorTradeModel.exit_reason == exit_reason)
        if trigger_type:
            if trigger_type == '__EMPTY__':
                query = query.filter(WarriorTradeModel.trigger_type == None)
            else:
                query = query.filter(WarriorTradeModel.trigger_type == trigger_type)
        if quote_source:
            if quote_source == '__EMPTY__':
                query = query.filter(WarriorTradeModel.quote_source == None)
            else:
                query = query.filter(WarriorTradeModel.quote_source == quote_source)
        if exit_mode:
            if exit_mode == '__EMPTY__':
                query = query.filter(WarriorTradeModel.exit_mode == None)
            else:
                query = query.filter(WarriorTradeModel.exit_mode == exit_mode)
        if stop_method:
            if stop_method == '__EMPTY__':
                query = query.filter(WarriorTradeModel.stop_method == None)
            else:
                query = query.filter(WarriorTradeModel.stop_method == stop_method)
        if is_sim is not None:
            if is_sim.lower() == 'null' or is_sim == '__EMPTY__':
                query = query.filter(WarriorTradeModel.is_sim == None)
            elif is_sim.lower() == 'true':
                query = query.filter(WarriorTradeModel.is_sim == True)
            elif is_sim.lower() == 'false':
                query = query.filter(WarriorTradeModel.is_sim == False)
        if partial_taken is not None:
            if partial_taken == '__EMPTY__' or partial_taken.lower() == 'null':
                query = query.filter(WarriorTradeModel.partial_taken == None)
            elif partial_taken.lower() == 'true':
                query = query.filter(WarriorTradeModel.partial_taken == True)
            elif partial_taken.lower() == 'false':
                query = query.filter(WarriorTradeModel.partial_taken == False)
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


# =============================================================================
# QUOTE AUDITS ENDPOINT (data fidelity analysis)
# =============================================================================

@router.get("/quote-audits")
async def get_quote_audits(
    limit: int = Query(50, ge=1, le=500, description="Maximum records to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    time_window: Optional[str] = Query(None, description="Filter by time window (premarket_early, regular_hours, etc)"),
    selected_source: Optional[str] = Query(None, description="Filter by selected source (Alpaca, FMP, Schwab)"),
    high_divergence: Optional[bool] = Query(None, description="Filter by high divergence flag"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    sort_by: str = Query("timestamp", description="Column to sort by"),
    sort_dir: str = Query("desc", description="Sort direction: asc or desc"),
):
    """
    Get paginated quote audit records with filtering and sorting.
    
    Useful for analyzing:
    - Quote divergence between providers
    - High divergence events (phantom quotes)
    - Source reliability by time window
    """
    from nexus2.db.models import QuoteAuditModel, get_session
    from sqlalchemy import desc, asc
    
    with get_session() as db:
        query = db.query(QuoteAuditModel)
        
        # Apply filters (handle __EMPTY__ for NULL filtering)
        if symbol:
            if symbol == '__EMPTY__':
                query = query.filter(QuoteAuditModel.symbol == None)
            else:
                query = query.filter(QuoteAuditModel.symbol == symbol.upper())
        if time_window:
            if time_window == '__EMPTY__':
                query = query.filter(QuoteAuditModel.time_window == None)
            else:
                query = query.filter(QuoteAuditModel.time_window == time_window)
        if selected_source:
            if selected_source == '__EMPTY__':
                query = query.filter(QuoteAuditModel.selected_source == None)
            else:
                query = query.filter(QuoteAuditModel.selected_source == selected_source)
        if high_divergence is not None:
            query = query.filter(QuoteAuditModel.high_divergence == high_divergence)
        if date_from:
            query = query.filter(QuoteAuditModel.timestamp >= date_from)
        if date_to:
            query = query.filter(QuoteAuditModel.timestamp <= date_to + "T23:59:59")
        
        # Get total count
        total = query.count()
        
        # Apply sorting
        sort_column = getattr(QuoteAuditModel, sort_by, QuoteAuditModel.timestamp)
        if sort_dir.lower() == "desc":
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(asc(sort_column))
        
        # Apply pagination
        audits = query.offset(offset).limit(limit).all()
        
        return {
            "audits": [a.to_dict() for a in audits],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
