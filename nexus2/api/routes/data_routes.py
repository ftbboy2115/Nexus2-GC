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
    if symbol:
        all_entries = [e for e in all_entries if e["symbol"].upper() == symbol.upper()]
    if source:
        all_entries = [e for e in all_entries if e.get("source", "scan") == source]
    if catalyst:
        all_entries = [e for e in all_entries if e.get("catalyst", "") == catalyst]
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
        
        # Apply symbol filter (supports comma-separated multi-select)
        if symbol:
            from sqlalchemy import or_
            symbol_list = [s.strip().upper() for s in symbol.split(',')]
            query = query.filter(WarriorScanResult.symbol.in_(symbol_list))
        
        # Apply result filter (PASS/FAIL, supports comma-separated)
        if result:
            result_list = [r.strip().upper() for r in result.split(',')]
            query = query.filter(WarriorScanResult.result.in_(result_list))
        
        # Apply country filter (supports comma-separated)
        if country:
            country_list = [c.strip().upper() for c in country.split(',')]
            query = query.filter(WarriorScanResult.country.in_(country_list))
        
        # Apply score filter (supports comma-separated, handles (empty) for NULL)
        if score:
            from sqlalchemy import or_
            score_list = [s.strip() for s in score.split(',')]
            conditions = []
            for val in score_list:
                if val == '(empty)':
                    conditions.append(WarriorScanResult.score.is_(None))
                else:
                    try:
                        conditions.append(WarriorScanResult.score == int(val))
                    except ValueError:
                        pass  # Skip invalid
            if conditions:
                query = query.filter(or_(*conditions))
        
        # Apply date/time filters (timestamps stored as UTC in DB)
        # Convert date_from/date_to from ET to UTC for proper filtering
        utc_tz = ZoneInfo("UTC")
        et_tz = ZoneInfo("America/New_York")
        
        if date_from:
            # Convert ET date to UTC datetime at start of day
            try:
                et_start = dt.strptime(f"{date_from} 00:00:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=et_tz)
                utc_start = et_start.astimezone(utc_tz)
                query = query.filter(WarriorScanResult.timestamp >= utc_start)
            except ValueError:
                pass  # Invalid date format, skip filter
        
        if date_to:
            # Convert ET date to UTC datetime at end of day
            try:
                et_end = dt.strptime(f"{date_to} 23:59:59", "%Y-%m-%d %H:%M:%S").replace(tzinfo=et_tz)
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
# CATALYST AUDITS ENDPOINT (parses catalyst_audit.log)
# =============================================================================

# Shared patterns and parsing for catalyst audit logs
import re
from pathlib import Path
from typing import List, Dict, Any

CATALYST_HEADER_PATTERN = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| === (\w+) \| Result: (PASS|FAIL) \| Type: (\w+) ==="
)
CATALYST_HEADLINE_PATTERN = re.compile(
    r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \|   \[(\d+)\] ([✓✗]) (\w+) \(conf=([0-9.]+)\): (.+)"
)


def _read_catalyst_audit_logs() -> List[str]:
    """Read all catalyst audit log lines (including rotated logs)."""
    log_dir = Path("data")
    if not log_dir.exists():
        log_dir = Path.home() / "Nexus2" / "data"
    
    all_lines = []
    base_log = log_dir / "catalyst_audit.log"
    
    if base_log.exists():
        try:
            with open(base_log, "r", encoding="utf-8") as f:
                all_lines.extend(f.readlines())
        except Exception:
            pass
    
    # Read rotated logs
    for i in range(1, 8):
        rotated_log = log_dir / f"catalyst_audit.log.{i}"
        if rotated_log.exists():
            try:
                with open(rotated_log, "r", encoding="utf-8") as f:
                    all_lines.extend(f.readlines())
            except Exception:
                pass
    
    return all_lines


def _parse_catalyst_audit_entries(all_lines: List[str]) -> List[Dict[str, Any]]:
    """Parse catalyst audit log lines into structured entries."""
    entries = []
    current_header = None
    
    for line in all_lines:
        line = line.strip()
        if not line:
            continue
        
        match = CATALYST_HEADER_PATTERN.match(line)
        if match:
            current_header = {
                "timestamp": match.group(1),
                "symbol": match.group(2),
                "result": match.group(3),
                "catalyst_type": match.group(4),
            }
            continue
        
        match = CATALYST_HEADLINE_PATTERN.match(line)
        if match and current_header:
            entries.append({
                "timestamp": match.group(1),
                "symbol": current_header["symbol"],
                "regex_result": current_header["result"],
                "headline_index": int(match.group(2)),
                "passed": match.group(3) == "✓",
                "regex_match_type": match.group(4),
                "confidence": float(match.group(5)),
                "headline": match.group(6),
            })
    
    return entries

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
    regex_result: Optional[str] = Query(None, description="Alias for result filter"),
    match_type: Optional[str] = Query(None, description="Filter by match type"),
    regex_match_type: Optional[str] = Query(None, description="Alias for match_type filter"),
    headline: Optional[str] = Query(None, description="Filter by headline text (case-insensitive)"),
    confidence: Optional[str] = Query(None, description="Filter by confidence score"),
    headline_index: Optional[str] = Query(None, description="Filter by headline index"),
    timestamp: Optional[str] = Query(None, description="Filter by exact timestamp"),
    sort_by: str = Query("timestamp", description="Column to sort by"),
    sort_dir: str = Query("desc", description="Sort direction: asc or desc"),
):
    """
    Get paginated catalyst audit entries with filtering and sorting.
    
    Parses catalyst_audit.log to show headline evaluations for debugging.
    
    Returns:
        entries: List of catalyst audit entries (symbol, result, headline, match_type, confidence)
        total: Total count for pagination
        limit: Records per page
        offset: Current offset
    """
    # Use shared helpers for reading and parsing logs
    all_lines = _read_catalyst_audit_logs()
    if not all_lines:
        return {"entries": [], "total": 0, "limit": limit, "offset": offset}
    
    all_entries = _parse_catalyst_audit_entries(all_lines)
    
    # Convert timestamps from UTC to ET for display
    from zoneinfo import ZoneInfo
    from datetime import datetime as dt
    utc_tz = ZoneInfo("UTC")
    et_tz = ZoneInfo("America/New_York")
    
    for entry in all_entries:
        try:
            utc_dt = dt.strptime(entry["timestamp"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=utc_tz)
            local_dt = utc_dt.astimezone(et_tz)
            entry["timestamp"] = local_dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            pass  # Keep original on parse failure
    
    # Apply filters with time support
    if date_from or date_to or time_from or time_to:
        filtered = []
        for e in all_entries:
            ts = e["timestamp"]
            entry_date = ts[:10]
            entry_time = ts[11:16]
            if date_from and entry_date < date_from:
                continue
            if date_to and entry_date > date_to:
                continue
            if time_from and entry_time < time_from:
                continue
            if time_to and entry_time > time_to:
                continue
            filtered.append(e)
        all_entries = filtered
    if symbol:
        # Support multi-select: comma-separated values mean "include any of these"
        symbol_set = {s.strip().upper() for s in symbol.split(',')}
        all_entries = [e for e in all_entries if e["symbol"].upper() in symbol_set]
    # Handle result filter (support both 'result' and 'regex_result' param names)
    actual_result = result or regex_result
    if actual_result:
        result_set = {r.strip().upper() for r in actual_result.split(',')}
        all_entries = [e for e in all_entries if e["regex_result"] in result_set]
    # Handle match_type filter (support both 'match_type' and 'regex_match_type' param names)
    actual_match_type = match_type or regex_match_type
    if actual_match_type:
        match_type_set = {m.strip() for m in actual_match_type.split(',')}
        all_entries = [e for e in all_entries if e["regex_match_type"] in match_type_set]
    if headline:
        headline_lower = headline.lower()
        all_entries = [e for e in all_entries if headline_lower in e.get("headline", "").lower()]
    if confidence:
        conf_set = {c.strip() for c in confidence.split(',')}
        all_entries = [e for e in all_entries if str(e.get("confidence", "")) in conf_set]
    if headline_index:
        idx_set = {i.strip() for i in headline_index.split(',')}
        all_entries = [e for e in all_entries if str(e.get("headline_index", "")) in idx_set]
    all_entries = _apply_exact_time_filter(all_entries, "timestamp", timestamp)
    
    # Calculate total before pagination
    total = len(all_entries)
    
    # Apply sorting
    reverse = sort_dir.lower() == "desc"
    all_entries.sort(key=lambda x: x.get(sort_by) or "", reverse=reverse)
    
    # Apply pagination
    entries = all_entries[offset:offset + limit]
    
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
    
    Used by filter dropdowns to show all available filter options,
    not just values on the current page.
    """
    # Use shared helper for reading and parsing logs
    all_lines = _read_catalyst_audit_logs()
    if not all_lines:
        return {"column": column, "values": []}
    
    all_entries = _parse_catalyst_audit_entries(all_lines)
    
    # Extract distinct values for the requested column
    values = set()
    for entry in all_entries:
        if column in entry:
            val = entry[column]
            if val is not None:
                values.add(str(val))
    
    return {"column": column, "values": sorted(list(values))}


# =============================================================================
# AI COMPARISONS ENDPOINT (parses catalyst_comparison.jsonl)
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
    flash_valid: Optional[bool] = Query(None, description="Filter by Flash-Lite result"),
    used_tiebreaker: Optional[bool] = Query(None, description="Filter entries that used Pro tiebreaker"),
    timestamp: Optional[str] = Query(None, description="Filter by exact timestamp"),
    sort_by: str = Query("timestamp", description="Column to sort by"),
    sort_dir: str = Query("desc", description="Sort direction: asc or desc"),
):
    """
    Get paginated AI comparison entries showing Regex vs Flash-Lite vs Pro.
    
    Parses catalyst_comparison.jsonl to show the multi-model validation pipeline.
    
    Returns:
        entries: List of comparison entries with regex_conf, flash_valid, pro_valid, etc.
        total: Total count for pagination
        limit: Records per page
        offset: Current offset
    """
    from pathlib import Path
    import json
    
    # Find log directory
    log_dir = Path("data")
    if not log_dir.exists():
        log_dir = Path.home() / "Nexus2" / "data"
    
    log_path = log_dir / "catalyst_comparison.jsonl"
    if not log_path.exists():
        return {"entries": [], "total": 0, "limit": limit, "offset": offset}
    
    # Read JSONL file
    all_entries = []
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    
                    # Flatten the nested structure for table display
                    flash_result = data.get("models", {}).get("flash_lite", {})
                    pro_result = data.get("models", {}).get("pro", {})
                    regex_info = data.get("regex", {})
                    
                    entry = {
                        "timestamp": data.get("timestamp", "")[:19],  # Trim timezone
                        "symbol": data.get("symbol"),
                        "headline": data.get("headline", "")[:80],
                        "url": data.get("article_url"),
                        "regex_type": regex_info.get("type"),
                        "regex_conf": regex_info.get("conf", 0),
                        "flash_valid": flash_result.get("valid"),
                        "flash_type": flash_result.get("type"),
                        "flash_reason": flash_result.get("reason", "")[:40],
                        "flash_ms": flash_result.get("latency_ms", 0),
                        "pro_valid": pro_result.get("valid") if pro_result else None,
                        "pro_type": pro_result.get("type") if pro_result else None,
                        "pro_reason": (pro_result.get("reason") or "")[:40] if pro_result else None,
                        "used_tiebreaker": bool(pro_result),
                    }
                    all_entries.append(entry)
                except json.JSONDecodeError:
                    continue
    except Exception:
        return {"entries": [], "total": 0, "limit": limit, "offset": offset}
    
    # Apply filters with time support
    if date_from or date_to or time_from or time_to:
        filtered = []
        for e in all_entries:
            ts = e["timestamp"]
            entry_date = ts[:10]
            entry_time = ts[11:16]
            if date_from and entry_date < date_from:
                continue
            if date_to and entry_date > date_to:
                continue
            if time_from and entry_time < time_from:
                continue
            if time_to and entry_time > time_to:
                continue
            filtered.append(e)
        all_entries = filtered
    if symbol:
        # Support multi-select: comma-separated values mean "include any of these"
        symbol_set = {s.strip().upper() for s in symbol.split(',')}
        all_entries = [e for e in all_entries if e["symbol"] and e["symbol"].upper() in symbol_set]
    if flash_valid is not None:
        all_entries = [e for e in all_entries if e["flash_valid"] == flash_valid]
    if used_tiebreaker is not None:
        all_entries = [e for e in all_entries if e["used_tiebreaker"] == used_tiebreaker]
    all_entries = _apply_exact_time_filter(all_entries, "timestamp", timestamp)
    
    # Calculate total before pagination
    total = len(all_entries)
    
    # Apply sorting (handle mixed types by converting to strings)
    reverse = sort_dir.lower() == "desc"
    def sort_key(x):
        val = x.get(sort_by)
        if val is None:
            return ""
        if isinstance(val, bool):
            return str(val).lower()  # "false" < "true" alphabetically
        return str(val)
    all_entries.sort(key=sort_key, reverse=reverse)
    
    # Apply pagination
    entries = all_entries[offset:offset + limit]
    
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
    """
    from pathlib import Path
    import json
    
    log_dir = Path("data")
    if not log_dir.exists():
        log_dir = Path.home() / "Nexus2" / "data"
    
    log_path = log_dir / "catalyst_comparison.jsonl"
    if not log_path.exists():
        return {"column": column, "values": []}
    
    values = set()
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    flash_result = data.get("models", {}).get("flash_lite", {})
                    pro_result = data.get("models", {}).get("pro", {})
                    regex_info = data.get("regex", {})
                    
                    if column == "symbol":
                        values.add(data.get("symbol", ""))
                    elif column == "regex_type":
                        values.add(regex_info.get("type", ""))
                    elif column == "regex_conf":
                        values.add(str(regex_info.get("conf", 0)))
                    elif column == "flash_valid":
                        values.add(str(flash_result.get("valid", "")))
                    elif column == "flash_type":
                        values.add(flash_result.get("type", ""))
                    elif column == "pro_valid":
                        if pro_result:
                            values.add(str(pro_result.get("valid", "")))
                    elif column == "used_tiebreaker":
                        values.add(str(bool(pro_result)))
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    
    # Remove empty strings
    values.discard("")
    return {"column": column, "values": sorted(list(values))}


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
    
    # Apply additional filters
    if symbol:
        all_events = [e for e in all_events if e.get("symbol", "").upper() == symbol.upper()]
    if event_type:
        all_events = [e for e in all_events if e.get("event_type") == event_type]
    # Date and time filter uses created_at field (ISO format)
    if date_from or date_to or time_from or time_to:
        filtered = []
        for e in all_events:
            created = e.get("created_at", "")
            if len(created) >= 16:
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
        event["shares"] = meta.get("shares", "")
    
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
        
        # Apply filters
        if symbol:
            query = query.filter(EntryValidationLogModel.symbol == symbol.upper())
        if entry_trigger:
            query = query.filter(EntryValidationLogModel.entry_trigger == entry_trigger)
        if target_hit is not None:
            if target_hit == '__EMPTY__':
                query = query.filter(EntryValidationLogModel.target_hit == None)
            elif target_hit.lower() == 'true':
                query = query.filter(EntryValidationLogModel.target_hit == True)
            elif target_hit.lower() == 'false':
                query = query.filter(EntryValidationLogModel.target_hit == False)
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
