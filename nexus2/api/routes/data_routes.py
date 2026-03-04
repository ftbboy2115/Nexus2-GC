"""
Data Explorer Routes

API endpoints for the Data Explorer UI - provides paginated, filterable
access to NAC trades and scan history data.
"""

from datetime import date, datetime
from datetime import datetime as dt
from typing import Optional, List
from fastapi import APIRouter, Query
from nexus2.utils.time_utils import et_to_utc, EASTERN

router = APIRouter(prefix="/data", tags=["data-explorer"])


# =============================================================================
# SHARED HELPER FUNCTIONS
# =============================================================================

def _apply_exact_time_filter(entries: List[dict], column: str, filter_value: Optional[str]) -> List[dict]:
    """
    Filter entries by exact timestamp match (supports comma-separated multi-select).
    
    Args:
        entries: List of entry dicts
        column: Column name to filter on (e.g., 'timestamp', 'entry_time', 'created_at')
        filter_value: Comma-separated values to match exactly
    
    Returns:
        Filtered list of entries
    """
    if not filter_value:
        return entries
    value_set = {v.strip() for v in filter_value.split(',')}
    return [e for e in entries if e.get(column, "") in value_set]

def _apply_multi_select(entries: List[dict], column: str, filter_value: Optional[str]) -> List[dict]:
    """Filter in-memory entries by comma-separated multi-select values."""
    if not filter_value:
        return entries
    value_set = {v.strip() for v in filter_value.split(',')}
    has_empty = '(empty)' in value_set
    value_set.discard('(empty)')
    return [
        e for e in entries
        if str(e.get(column) or '') in value_set
        or (has_empty and not e.get(column))
    ]

def apply_generic_filters(query, model, **filters):
    """
    Apply column filters dynamically to a query.
    
    Supports:
    - Equality: "US" → col = 'US'
    - Multi-select: "US,CN" → col IN ('US', 'CN')
    - Range: ">=5" → col >= 5, "<=10" → col <= 10
    - Combined: ">=5,<=10" → col >= 5 AND col <= 10
    - NULL handling: "(empty)" → col IS NULL
    
    Args:
        query: SQLAlchemy query object
        model: SQLAlchemy model class
        **filters: Column name → value pairs
        
    Returns:
        Filtered query
    """
    from sqlalchemy import or_, and_
    import re
    
    RANGE_PATTERN = re.compile(r'^(>=|<=|>|<)(.+)$')
    
    for col_name, value in filters.items():
        if value is None:
            continue
            
        col = getattr(model, col_name, None)
        if col is None:
            continue  # Skip invalid/unknown columns
        
        # Split comma-separated values
        value_list = [v.strip() for v in value.split(',')]
        
        # Separate range operators from equality values
        range_conditions = []
        equality_values = []
        has_empty = False
        
        for val in value_list:
            if val == '(empty)':
                has_empty = True
            elif match := RANGE_PATTERN.match(val):
                op, num = match.groups()
                try:
                    num_val = float(num) if '.' in num else int(num)
                    if op == '>=':
                        range_conditions.append(col >= num_val)
                    elif op == '<=':
                        range_conditions.append(col <= num_val)
                    elif op == '>':
                        range_conditions.append(col > num_val)
                    elif op == '<':
                        range_conditions.append(col < num_val)
                except ValueError:
                    pass  # Skip invalid numbers
            else:
                equality_values.append(val)
        
        # Build filter conditions
        conditions = []
        
        if has_empty:
            conditions.append(col.is_(None))
        
        if equality_values:
            conditions.append(col.in_(equality_values))
        
        if range_conditions:
            # Range conditions are ANDed together (e.g., >=5 AND <=10)
            conditions.append(and_(*range_conditions))
        
        # Combine all conditions with OR (empty OR equality OR range)
        if conditions:
            if len(conditions) == 1:
                query = query.filter(conditions[0])
            else:
                query = query.filter(or_(*conditions))
    
    return query


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
    time_from: Optional[str] = Query(None, description="Start time (HH:MM) in ET"),
    time_to: Optional[str] = Query(None, description="End time (HH:MM) in ET"),
    entry_time: Optional[str] = Query(None, description="Filter by exact entry_time"),
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
        
        # Apply multi-select filters via generic handler
        query = apply_generic_filters(
            query, NACTradeModel,
            status=status,
            symbol=symbol.upper() if symbol else None,
            exit_reason=exit_reason,
            setup_type=setup_type,
        )
        # Boolean column - keep manual handling
        if partial_taken is not None:
            query = query.filter(NACTradeModel.partial_taken == partial_taken)
        if date_from:
            try:
                start_time = f"{time_from}:00" if time_from else "00:00:00"
                et_start = EASTERN.localize(dt.strptime(f"{date_from} {start_time}", "%Y-%m-%d %H:%M:%S"))
                query = query.filter(NACTradeModel.entry_time >= et_to_utc(et_start))
            except ValueError:
                pass
        if date_to:
            try:
                end_time = f"{time_to}:59" if time_to else "23:59:59"
                et_end = EASTERN.localize(dt.strptime(f"{date_to} {end_time}", "%Y-%m-%d %H:%M:%S"))
                query = query.filter(NACTradeModel.entry_time <= et_to_utc(et_end))
            except ValueError:
                pass
        # Exact entry_time filter (supports comma-separated values)
        # Normalize ISO format (2026-02-05T03:18:02Z) to DB format prefix (2026-02-05 03:18:02)
        if entry_time:
            from sqlalchemy import or_
            time_values = []
            for t in entry_time.split(','):
                t = t.strip().replace('T', ' ').rstrip('Z')  # Convert ISO to DB format
                time_values.append(t)
            query = query.filter(or_(*[NACTradeModel.entry_time.like(f"{t}%") for t in time_values]))
        
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
# SCAN HISTORY ENDPOINT (NAC/EP Scans from scan_history.json)
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
    logged_at: Optional[str] = Query(None, description="Filter by exact logged_at timestamp"),
    sort_by: str = Query("logged_at", description="Column to sort by"),
    sort_dir: str = Query("desc", description="Sort direction: asc or desc"),
):
    """
    Get paginated NAC/EP scan history with filtering and sorting.
    
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
    all_entries = _apply_multi_select(all_entries, "symbol", symbol.upper() if symbol else None)
    all_entries = _apply_multi_select(all_entries, "source", source)
    all_entries = _apply_multi_select(all_entries, "catalyst", catalyst)
    all_entries = _apply_exact_time_filter(all_entries, "logged_at", logged_at)
    
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
# WARRIOR SCAN HISTORY ENDPOINT (PASS/FAIL from warrior_scan.log)
# =============================================================================

@router.get("/warrior-scan-history")
async def get_warrior_scan_history(
    limit: int = Query(50, ge=1, le=500, description="Maximum records to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    time_from: Optional[str] = Query(None, description="Start time (HH:MM)"),
    time_to: Optional[str] = Query(None, description="End time (HH:MM)"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    result: Optional[str] = Query(None, description="Filter by result: PASS or FAIL"),
    country: Optional[str] = Query(None, description="Filter by country code (comma-separated)"),
    source: Optional[str] = Query(None, description="Filter by source: SCAN or PILLARS"),
    timestamp: Optional[str] = Query(None, description="Filter by exact timestamp"),
    score: Optional[str] = Query(None, description="Filter by score (comma-separated, use '(empty)' for NULL)"),
    sort_by: str = Query("timestamp", description="Column to sort by"),
    sort_dir: str = Query("desc", description="Sort direction: asc or desc"),
):
    """
    Get paginated Warrior scan history with filtering and sorting.
    
    Queries telemetry.db warrior_scan_results table (migrated from log parsing in Phase 3).
    
    Returns:
        entries: List of scan entries (symbol, result, gap_pct, rvol, score, reason, timestamp)
        total: Total count for pagination
        limit: Records per page
        offset: Current offset
    """
    from nexus2.db.telemetry_db import get_telemetry_session, WarriorScanResult
    from sqlalchemy import desc, asc, cast, Float, func
    from zoneinfo import ZoneInfo
    from datetime import datetime as dt
    
    with get_telemetry_session() as db:
        query = db.query(WarriorScanResult)
        
        # Apply generic column filters (supports equality, multi-select, range)
        query = apply_generic_filters(
            query, WarriorScanResult,
            symbol=symbol,
            result=result,
            country=country,
            score=score,
            source=source,
        )
        
        # Apply date/time filters (timestamps stored as UTC in DB)
        # Convert date_from/date_to from ET to UTC for proper filtering
        utc_tz = ZoneInfo("UTC")
        et_tz = ZoneInfo("America/New_York")
        
        if date_from:
            # Convert ET date+time to UTC datetime
            try:
                start_time = f"{time_from}:00" if time_from else "00:00:00"
                et_start = dt.strptime(f"{date_from} {start_time}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=et_tz)
                utc_start = et_start.astimezone(utc_tz)
                query = query.filter(WarriorScanResult.timestamp >= utc_start)
            except ValueError:
                pass  # Invalid date format, skip filter
        
        if date_to:
            # Convert ET date+time to UTC datetime
            try:
                end_time = f"{time_to}:59" if time_to else "23:59:59"
                et_end = dt.strptime(f"{date_to} {end_time}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=et_tz)
                utc_end = et_end.astimezone(utc_tz)
                query = query.filter(WarriorScanResult.timestamp <= utc_end)
            except ValueError:
                pass  # Invalid date format, skip filter
        
        # Get total count before pagination
        total = query.count()
        
        # Apply sorting
        sort_column_map = {
            "timestamp": WarriorScanResult.timestamp,
            "symbol": WarriorScanResult.symbol,
            "result": WarriorScanResult.result,
            "gap_pct": WarriorScanResult.gap_pct,
            "rvol": WarriorScanResult.rvol,
            "score": WarriorScanResult.score,
            "reason": WarriorScanResult.reason,
        }
        sort_column = sort_column_map.get(sort_by, WarriorScanResult.timestamp)
        
        if sort_dir.lower() == "desc":
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(asc(sort_column))
        
        # Apply pagination
        query = query.offset(offset).limit(limit)
        rows = query.all()
        
        # Convert to dict format matching legacy log-parsing output
        entries = []
        for row in rows:
            entry = row.to_dict()
            # Convert float_shares to readable format for display
            if entry.get("float_shares"):
                float_val = entry["float_shares"]
                if float_val >= 1_000_000_000:
                    entry["float"] = f"{float_val / 1_000_000_000:.1f}B"
                elif float_val >= 1_000_000:
                    entry["float"] = f"{float_val / 1_000_000:.1f}M"
                elif float_val >= 1_000:
                    entry["float"] = f"{float_val / 1_000:.1f}K"
                else:
                    entry["float"] = str(float_val)
            else:
                entry["float"] = None
            # Remove raw float_shares from response (display uses formatted 'float')
            entry.pop("float_shares", None)
            # Rename catalyst_type to catalyst for cleaner display
            if "catalyst_type" in entry:
                entry["catalyst"] = entry.pop("catalyst_type")

            entries.append(entry)
        
        return {
            "entries": entries,
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@router.get("/warrior-scan-history/distinct")
async def get_warrior_scan_history_distinct(
    column: str = Query(..., description="Column to get unique values for"),
):
    """
    Get distinct values for a column in Warrior scan history.
    Used by filter dropdowns to show all available options.
    
    Queries telemetry.db (migrated from log parsing in Phase 3).
    """
    from nexus2.db.telemetry_db import get_telemetry_session, WarriorScanResult
    from sqlalchemy import distinct
    
    with get_telemetry_session() as db:
        # Dynamic column lookup
        col = getattr(WarriorScanResult, column, None)
        if col is None:
            return {"column": column, "values": []}
        
        results = db.query(distinct(col)).all()
        values = [str(r[0]) for r in results if r[0] is not None]
    
    return {"column": column, "values": sorted(values)}


@router.get("/scan-history/distinct")
async def get_nac_scan_history_distinct(
    column: str = Query(..., description="Column to get unique values for"),
):
    """
    Get distinct values for a column in NAC/EP scan history.
    Used by filter dropdowns to show all available options.
    """
    from nexus2.domain.lab.scan_history_logger import get_scan_history_logger
    
    history = get_scan_history_logger()
    
    values = set()
    for date_str, entries in history._history.items():
        for entry in entries:
            full_entry = {"date": date_str, "source": "scan", **entry}
            if column in full_entry:
                val = full_entry[column]
                if val is not None:
                    values.add(str(val))
    
    values.discard("")
    return {"column": column, "values": sorted(list(values))}


# =============================================================================
# CATALYST AUDITS ENDPOINT (queries telemetry.db)
# =============================================================================

@router.get("/catalyst-audits")
async def get_catalyst_audits(
    limit: int = Query(50, ge=1, le=500, description="Maximum records to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    time_from: Optional[str] = Query(None, description="Start time (HH:MM)"),
    time_to: Optional[str] = Query(None, description="End time (HH:MM)"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    result: Optional[str] = Query(None, description="Filter by result: PASS or FAIL"),
    match_type: Optional[str] = Query(None, description="Filter by match type"),
    headline: Optional[str] = Query(None, description="Filter by headline text (case-insensitive)"),
    confidence: Optional[str] = Query(None, description="Filter by confidence score"),
    source: Optional[str] = Query(None, description="Filter by source (FMP, Benzinga, etc.)"),
    timestamp: Optional[str] = Query(None, description="Filter by exact timestamp"),
    sort_by: str = Query("timestamp", description="Column to sort by"),
    sort_dir: str = Query("desc", description="Sort direction: asc or desc"),
):
    """
    Get paginated catalyst audit entries with filtering and sorting.
    
    Queries telemetry.db catalyst_audits table (migrated from log parsing in Phase 6).
    
    Returns:
        entries: List of catalyst audit entries (symbol, result, headline, match_type, confidence)
        total: Total count for pagination
        limit: Records per page
        offset: Current offset
    """
    from nexus2.db.telemetry_db import get_telemetry_session, CatalystAudit
    from sqlalchemy import desc, asc
    from zoneinfo import ZoneInfo
    from datetime import datetime as dt
    
    with get_telemetry_session() as db:
        query = db.query(CatalystAudit)
        
        # Apply generic column filters (supports equality, multi-select, range)
        query = apply_generic_filters(
            query, CatalystAudit,
            symbol=symbol,
            result=result,
            match_type=match_type,
            confidence=confidence,
            source=source,
        )
        
        # Apply headline substring filter (case-insensitive)
        if headline:
            query = query.filter(CatalystAudit.headline.ilike(f"%{headline}%"))
        
        # Apply date/time filters (timestamps stored as UTC in DB)
        utc_tz = ZoneInfo("UTC")
        et_tz = ZoneInfo("America/New_York")
        
        if date_from:
            try:
                start_time = f"{time_from}:00" if time_from else "00:00:00"
                et_start = dt.strptime(f"{date_from} {start_time}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=et_tz)
                utc_start = et_start.astimezone(utc_tz)
                query = query.filter(CatalystAudit.timestamp >= utc_start)
            except ValueError:
                pass
        
        if date_to:
            try:
                end_time = f"{time_to}:59" if time_to else "23:59:59"
                et_end = dt.strptime(f"{date_to} {end_time}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=et_tz)
                utc_end = et_end.astimezone(utc_tz)
                query = query.filter(CatalystAudit.timestamp <= utc_end)
            except ValueError:
                pass
        
        # Get total count before pagination
        total = query.count()
        
        # Apply sorting
        sort_column_map = {
            "timestamp": CatalystAudit.timestamp,
            "symbol": CatalystAudit.symbol,
            "result": CatalystAudit.result,
            "headline": CatalystAudit.headline,
            "match_type": CatalystAudit.match_type,
            "confidence": CatalystAudit.confidence,
            "source": CatalystAudit.source,
        }
        sort_column = sort_column_map.get(sort_by, CatalystAudit.timestamp)
        
        if sort_dir.lower() == "desc":
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(asc(sort_column))
        
        # Apply pagination
        query = query.offset(offset).limit(limit)
        rows = query.all()
        
        # Convert to dict format
        entries = [row.to_dict() for row in rows]
        
        return {
            "entries": entries,
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@router.get("/catalyst-audits/distinct")
async def get_catalyst_audits_distinct(
    column: str = Query(..., description="Column to get unique values for"),
):
    """
    Get distinct values for a column in catalyst audits.
    
    Queries telemetry.db (migrated from log parsing in Phase 6).
    Used by filter dropdowns to show all available filter options.
    """
    from nexus2.db.telemetry_db import get_telemetry_session, CatalystAudit
    from sqlalchemy import distinct
    
    with get_telemetry_session() as db:
        # Dynamic column lookup
        col = getattr(CatalystAudit, column, None)
        if col is None:
            return {"column": column, "values": []}
        
        results = db.query(distinct(col)).all()
        values = [str(r[0]) for r in results if r[0] is not None]
    
    return {"column": column, "values": sorted(values)}


# =============================================================================
# AI COMPARISONS ENDPOINT (queries telemetry.db)
# =============================================================================

@router.get("/ai-comparisons")
async def get_ai_comparisons(
    limit: int = Query(50, ge=1, le=500, description="Maximum records to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    time_from: Optional[str] = Query(None, description="Start time (HH:MM)"),
    time_to: Optional[str] = Query(None, description="End time (HH:MM)"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    flash_result: Optional[str] = Query(None, description="Filter by Flash result"),
    pro_result: Optional[str] = Query(None, description="Filter by Pro result"),
    winner: Optional[str] = Query(None, description="Filter by winner (flash, pro, regex)"),
    timestamp: Optional[str] = Query(None, description="Filter by exact timestamp"),
    sort_by: str = Query("timestamp", description="Column to sort by"),
    sort_dir: str = Query("desc", description="Sort direction: asc or desc"),
):
    """
    Get paginated AI comparison entries showing Regex vs Flash vs Pro.
    
    Queries telemetry.db ai_comparisons table (migrated from JSONL parsing in Phase 6).
    
    Returns:
        entries: List of comparison entries with regex_result, flash_result, pro_result, etc.
        total: Total count for pagination
        limit: Records per page
        offset: Current offset
    """
    from nexus2.db.telemetry_db import get_telemetry_session, AIComparison
    from sqlalchemy import desc, asc
    from zoneinfo import ZoneInfo
    from datetime import datetime as dt
    
    with get_telemetry_session() as db:
        query = db.query(AIComparison)
        
        # Apply generic column filters (supports equality, multi-select, range)
        query = apply_generic_filters(
            query, AIComparison,
            symbol=symbol,
            flash_result=flash_result,
            pro_result=pro_result,
            winner=winner,
        )
        
        # Apply date/time filters (timestamps stored as UTC in DB)
        utc_tz = ZoneInfo("UTC")
        et_tz = ZoneInfo("America/New_York")
        
        if date_from:
            try:
                start_time = f"{time_from}:00" if time_from else "00:00:00"
                et_start = dt.strptime(f"{date_from} {start_time}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=et_tz)
                utc_start = et_start.astimezone(utc_tz)
                query = query.filter(AIComparison.timestamp >= utc_start)
            except ValueError:
                pass
        
        if date_to:
            try:
                end_time = f"{time_to}:59" if time_to else "23:59:59"
                et_end = dt.strptime(f"{date_to} {end_time}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=et_tz)
                utc_end = et_end.astimezone(utc_tz)
                query = query.filter(AIComparison.timestamp <= utc_end)
            except ValueError:
                pass
        
        # Get total count before pagination
        total = query.count()
        
        # Apply sorting
        sort_column_map = {
            "timestamp": AIComparison.timestamp,
            "symbol": AIComparison.symbol,
            "headline": AIComparison.headline,
            "regex_result": AIComparison.regex_result,
            "flash_result": AIComparison.flash_result,
            "pro_result": AIComparison.pro_result,
            "final_result": AIComparison.final_result,
            "winner": AIComparison.winner,
        }
        sort_column = sort_column_map.get(sort_by, AIComparison.timestamp)
        
        if sort_dir.lower() == "desc":
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(asc(sort_column))
        
        # Apply pagination
        query = query.offset(offset).limit(limit)
        rows = query.all()
        
        # Convert to dict format
        entries = [row.to_dict() for row in rows]
        
        return {
            "entries": entries,
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@router.get("/ai-comparisons/distinct")
async def get_ai_comparisons_distinct(
    column: str = Query(..., description="Column to get unique values for"),
):
    """
    Get distinct values for a column in AI comparisons.
    
    Queries telemetry.db (migrated from JSONL parsing in Phase 6).
    """
    from nexus2.db.telemetry_db import get_telemetry_session, AIComparison
    from sqlalchemy import distinct
    
    with get_telemetry_session() as db:
        # Dynamic column lookup
        col = getattr(AIComparison, column, None)
        if col is None:
            return {"column": column, "values": []}
        
        results = db.query(distinct(col)).all()
        values = [str(r[0]) for r in results if r[0] is not None]
    
    return {"column": column, "values": sorted(values)}


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
    reason: Optional[str] = Query(None, description="Filter by reason"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    time_from: Optional[str] = Query(None, description="Start time (HH:MM)"),
    time_to: Optional[str] = Query(None, description="End time (HH:MM)"),
    created_at: Optional[str] = Query(None, description="Filter by exact created_at timestamp"),
    sort_by: str = Query("created_at", description="Column to sort by"),
    sort_dir: str = Query("desc", description="Sort direction: asc or desc"),
):
    """
    Get paginated trade events with filtering and sorting.
    """
    from nexus2.domain.automation.trade_event_service import trade_event_service
    
    # Get all events (service returns dicts)
    all_events = trade_event_service.get_recent_events(strategy, limit=500)
    
    # Apply multi-select filters
    all_events = _apply_multi_select(all_events, "symbol", symbol.upper() if symbol else None)
    all_events = _apply_multi_select(all_events, "event_type", event_type)
    all_events = _apply_multi_select(all_events, "reason", reason)
    # Date and time filter uses created_at field (stored as UTC, filters are ET)
    if date_from or date_to or time_from or time_to:
        from zoneinfo import ZoneInfo
        utc_tz = ZoneInfo("UTC")
        et_tz = ZoneInfo("America/New_York")
        filtered = []
        for e in all_events:
            created = e.get("created_at", "")
            if len(created) >= 16:
                try:
                    # Parse UTC timestamp and convert to ET for comparison
                    utc_str = created.replace("T", " ").rstrip("Z")[:19]
                    utc_dt = dt.strptime(utc_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=utc_tz)
                    et_dt = utc_dt.astimezone(et_tz)
                    entry_date = et_dt.strftime("%Y-%m-%d")
                    entry_time = et_dt.strftime("%H:%M")
                except (ValueError, IndexError):
                    entry_date = created[:10]
                    entry_time = created[11:16]
                if date_from and entry_date < date_from:
                    continue
                if date_to and entry_date > date_to:
                    continue
                if time_from and entry_time < time_from:
                    continue
                if time_to and entry_time > time_to:
                    continue
            filtered.append(e)
        all_events = filtered
    all_events = _apply_exact_time_filter(all_events, "created_at", created_at)
    
    # Get total before pagination
    total = len(all_events)
    
    # Apply sorting
    reverse = sort_dir.lower() == "desc"
    all_events.sort(key=lambda x: x.get(sort_by) or "", reverse=reverse)
    
    # Apply pagination
    events = all_events[offset:offset + limit]
    
    # Extract shares from metadata for display as column
    for event in events:
        meta = event.get("metadata") or {}
        if isinstance(meta, str):
            import json
            try:
                meta = json.loads(meta)
            except:
                meta = {}
        event["shares"] = meta.get("shares") or meta.get("shares_added") or meta.get("shares_sold") or ""

        # Round numeric display values to 2 decimal places
        for field in ("new_value", "old_value"):
            val = event.get(field)
            if val:
                try:
                    event[field] = f"{float(val):.2f}"
                except (ValueError, TypeError):
                    pass
    
    return {
        "events": events,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/trade-events/distinct")
async def get_trade_events_distinct(
    column: str = Query(..., description="Column to get unique values for"),
):
    """
    Get distinct values for a column in trade events.
    Used by filter dropdowns to show all available options.
    """
    from nexus2.domain.automation.trade_event_service import trade_event_service
    
    all_events = trade_event_service.get_recent_events(None, limit=1000)
    
    values = set()
    for event in all_events:
        if column in event:
            val = event[column]
            if val is not None:
                values.add(str(val))
    
    values.discard("")
    return {"column": column, "values": sorted(list(values))}


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
    time_from: Optional[str] = Query(None, description="Start time (HH:MM) in ET"),
    time_to: Optional[str] = Query(None, description="End time (HH:MM) in ET"),
    entry_time: Optional[str] = Query(None, description="Filter by exact entry_time"),
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
        
        # Apply multi-select filters via generic handler
        query = apply_generic_filters(
            query, WarriorTradeModel,
            status=status,
            symbol=symbol.upper() if symbol else None,
            exit_reason=exit_reason,
            trigger_type=trigger_type,
            quote_source=quote_source,
            exit_mode=exit_mode,
            stop_method=stop_method,
        )
        # Boolean columns need special handling (not string-based)
        if is_sim is not None:
            if is_sim.lower() in ('null', '(empty)'):
                query = query.filter(WarriorTradeModel.is_sim == None)
            elif is_sim.lower() == 'true':
                query = query.filter(WarriorTradeModel.is_sim == True)
            elif is_sim.lower() == 'false':
                query = query.filter(WarriorTradeModel.is_sim == False)
        if partial_taken is not None:
            if partial_taken.lower() in ('null', '(empty)'):
                query = query.filter(WarriorTradeModel.partial_taken == None)
            elif partial_taken.lower() == 'true':
                query = query.filter(WarriorTradeModel.partial_taken == True)
            elif partial_taken.lower() == 'false':
                query = query.filter(WarriorTradeModel.partial_taken == False)
        if date_from:
            try:
                start_time = f"{time_from}:00" if time_from else "00:00:00"
                et_start = EASTERN.localize(dt.strptime(f"{date_from} {start_time}", "%Y-%m-%d %H:%M:%S"))
                query = query.filter(WarriorTradeModel.entry_time >= et_to_utc(et_start))
            except ValueError:
                pass
        if date_to:
            try:
                end_time = f"{time_to}:59" if time_to else "23:59:59"
                et_end = EASTERN.localize(dt.strptime(f"{date_to} {end_time}", "%Y-%m-%d %H:%M:%S"))
                query = query.filter(WarriorTradeModel.entry_time <= et_to_utc(et_end))
            except ValueError:
                pass
        # Exact entry_time filter (supports comma-separated values)
        # Normalize ISO format (2026-02-05T03:18:02Z) to DB format prefix (2026-02-05 03:18:02)
        if entry_time:
            from sqlalchemy import or_
            time_values = []
            for t in entry_time.split(','):
                t = t.strip().replace('T', ' ').rstrip('Z')  # Convert ISO to DB format
                time_values.append(t)
            query = query.filter(or_(*[WarriorTradeModel.entry_time.like(f"{t}%") for t in time_values]))
        
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


@router.get("/warrior-trades/distinct")
async def get_warrior_trades_distinct(
    column: str = Query(..., description="Column to get unique values for"),
):
    """
    Get distinct values for a column in Warrior trades.
    Used by filter dropdowns to show all available options.
    """
    from nexus2.db.warrior_db import get_warrior_session, WarriorTradeModel
    from sqlalchemy import distinct
    
    with get_warrior_session() as db:
        # Get distinct values from the specified column
        col = getattr(WarriorTradeModel, column, None)
        if col is None:
            return {"column": column, "values": []}
        
        results = db.query(distinct(col)).all()
        values = [str(r[0]) for r in results if r[0] is not None]
    
    return {"column": column, "values": sorted(values)}


@router.get("/nac-trades/distinct")
async def get_nac_trades_distinct(
    column: str = Query(..., description="Column to get unique values for"),
):
    """
    Get distinct values for a column in NAC trades.
    Used by filter dropdowns to show all available options.
    """
    from nexus2.db.nac_db import get_nac_session, NACTradeModel
    from sqlalchemy import distinct
    
    with get_nac_session() as db:
        col = getattr(NACTradeModel, column, None)
        if col is None:
            return {"column": column, "values": []}
        
        results = db.query(distinct(col)).all()
        values = [str(r[0]) for r in results if r[0] is not None]
    
    return {"column": column, "values": sorted(values)}


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
    time_from: Optional[str] = Query(None, description="Start time (HH:MM) in ET"),
    time_to: Optional[str] = Query(None, description="End time (HH:MM) in ET"),
    timestamp: Optional[str] = Query(None, description="Filter by exact timestamp"),
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
    from nexus2.db.models import QuoteAuditModel
    from nexus2.db.database import get_session
    from sqlalchemy import desc, asc
    
    with get_session() as db:
        query = db.query(QuoteAuditModel)
        
        # Apply multi-select filters via generic handler
        query = apply_generic_filters(
            query, QuoteAuditModel,
            symbol=symbol.upper() if symbol else None,
            time_window=time_window,
            selected_source=selected_source,
        )
        # Boolean column - keep manual handling
        if high_divergence is not None:
            query = query.filter(QuoteAuditModel.high_divergence == high_divergence)
        if date_from:
            try:
                start_time = f"{time_from}:00" if time_from else "00:00:00"
                et_start = EASTERN.localize(dt.strptime(f"{date_from} {start_time}", "%Y-%m-%d %H:%M:%S"))
                query = query.filter(QuoteAuditModel.timestamp >= et_to_utc(et_start))
            except ValueError:
                pass
        if date_to:
            try:
                end_time = f"{time_to}:59" if time_to else "23:59:59"
                et_end = EASTERN.localize(dt.strptime(f"{date_to} {end_time}", "%Y-%m-%d %H:%M:%S"))
                query = query.filter(QuoteAuditModel.timestamp <= et_to_utc(et_end))
            except ValueError:
                pass
        # Exact timestamp filter (supports comma-separated values)
        # Normalize ISO format (2026-02-05T03:18:02Z) to DB format prefix (2026-02-05 03:18:02)
        if timestamp:
            from sqlalchemy import or_
            time_values = []
            for t in timestamp.split(','):
                t = t.strip().replace('T', ' ').rstrip('Z')  # Convert ISO to DB format
                time_values.append(t)
            query = query.filter(or_(*[QuoteAuditModel.timestamp.like(f"{t}%") for t in time_values]))
        
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


@router.get("/quote-audits/distinct")
async def get_quote_audits_distinct(
    column: str = Query(..., description="Column to get unique values for"),
):
    """
    Get distinct values for a column in quote audits.
    Used by filter dropdowns to show all available options.
    """
    from nexus2.db.models import QuoteAuditModel
    from nexus2.db.database import get_session
    from sqlalchemy import distinct
    
    with get_session() as db:
        col = getattr(QuoteAuditModel, column, None)
        if col is None:
            return {"column": column, "values": []}
        
        results = db.query(distinct(col)).all()
        values = [str(r[0]) for r in results if r[0] is not None]
    
    return {"column": column, "values": sorted(values)}


# =============================================================================
# ENTRY VALIDATION LOG ENDPOINT
# =============================================================================

@router.get("/validation-log")
async def get_validation_log(
    limit: int = Query(50, ge=1, le=500, description="Maximum records to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    entry_trigger: Optional[str] = Query(None, description="Filter by entry trigger (abcd, pmh_break, etc)"),
    target_hit: Optional[str] = Query(None, description="Filter by target hit: 'true', 'false', or '__EMPTY__'"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    time_from: Optional[str] = Query(None, description="Start time (HH:MM) in ET"),
    time_to: Optional[str] = Query(None, description="End time (HH:MM) in ET"),
    created_at: Optional[str] = Query(None, description="Filter by exact created_at timestamp"),
    sort_by: str = Query("created_at", description="Column to sort by"),
    sort_dir: str = Query("desc", description="Sort direction: asc or desc"),
):
    """
    Get paginated entry validation logs for auditing.
    
    Tracks:
    - Entry intent (expected_target, expected_stop, confidence)
    - Ross comparison (ross_entry, entry_delta)
    - Outcome (MFE, MAE, target_hit, realized_pnl)
    """
    from nexus2.db.warrior_db import get_warrior_session, EntryValidationLogModel
    from sqlalchemy import desc, asc
    
    with get_warrior_session() as db:
        query = db.query(EntryValidationLogModel)
        
        # Apply multi-select filters via generic handler
        query = apply_generic_filters(
            query, EntryValidationLogModel,
            symbol=symbol.upper() if symbol else None,
            entry_trigger=entry_trigger,
        )
        # Boolean column - keep manual handling
        if target_hit is not None:
            if target_hit.lower() in ('(empty)', 'null'):
                query = query.filter(EntryValidationLogModel.target_hit == None)
            elif target_hit.lower() == 'true':
                query = query.filter(EntryValidationLogModel.target_hit == True)
            elif target_hit.lower() == 'false':
                query = query.filter(EntryValidationLogModel.target_hit == False)
        # Date/time range filter (timestamps stored as UTC, filters in ET)
        if date_from:
            try:
                start_time = f"{time_from}:00" if time_from else "00:00:00"
                et_start = EASTERN.localize(dt.strptime(f"{date_from} {start_time}", "%Y-%m-%d %H:%M:%S"))
                query = query.filter(EntryValidationLogModel.created_at >= et_to_utc(et_start))
            except ValueError:
                pass
        if date_to:
            try:
                end_time = f"{time_to}:59" if time_to else "23:59:59"
                et_end = EASTERN.localize(dt.strptime(f"{date_to} {end_time}", "%Y-%m-%d %H:%M:%S"))
                query = query.filter(EntryValidationLogModel.created_at <= et_to_utc(et_end))
            except ValueError:
                pass
        # Exact created_at filter (supports comma-separated values)
        # Normalize ISO format (2026-02-05T03:18:02Z) to DB format prefix (2026-02-05 03:18:02)
        if created_at:
            from sqlalchemy import or_
            time_values = []
            for t in created_at.split(','):
                t = t.strip().replace('T', ' ').rstrip('Z')  # Convert ISO to DB format
                time_values.append(t)
            query = query.filter(or_(*[EntryValidationLogModel.created_at.like(f"{t}%") for t in time_values]))
        
        # Get total count
        total = query.count()
        
        # Apply sorting
        sort_column = getattr(EntryValidationLogModel, sort_by, EntryValidationLogModel.created_at)
        if sort_dir.lower() == "desc":
            query = query.order_by(desc(sort_column))
        else:
            query = query.order_by(asc(sort_column))
        
        # Apply pagination
        logs = query.offset(offset).limit(limit).all()
        
        return {
            "entries": [log.to_dict() for log in logs],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@router.get("/validation-log/distinct")
async def get_validation_log_distinct(
    column: str = Query(..., description="Column to get unique values for"),
):
    """
    Get distinct values for a column in entry validation logs.
    Used by filter dropdowns to show all available options.
    """
    from nexus2.db.warrior_db import get_warrior_session, EntryValidationLogModel
    from sqlalchemy import distinct
    
    with get_warrior_session() as db:
        col = getattr(EntryValidationLogModel, column, None)
        if col is None:
            return {"column": column, "values": []}
        
        results = db.query(distinct(col)).all()
        values = [str(r[0]) for r in results if r[0] is not None]
    
    return {"column": column, "values": sorted(values)}


# =============================================================================
# TEST ENDPOINT FOR CATALYST AUDIT VERIFICATION
# =============================================================================

@router.post("/test-catalyst-pass")
async def test_catalyst_pass():
    """
    Write a test PASS entry to catalyst_audit.log for verification.
    Entry will be clearly marked as TEST to distinguish from real data.
    """
    from nexus2.domain.automation.catalyst_classifier import log_headline_evaluation
    
    test_symbol = "TEST"
    test_headlines = ["[TEST] Verification of PASS logging - ignore this entry"]
    
    log_headline_evaluation(test_symbol, test_headlines, "PASS", "test_catalyst")
    
    return {
        "status": "ok",
        "message": "Test PASS entry written to catalyst_audit.log",
        "symbol": test_symbol,
        "catalyst_type": "test_catalyst"
    }
