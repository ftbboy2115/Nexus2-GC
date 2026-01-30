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
    source: Optional[str] = Query(None, description="Filter by source: SCAN or PILLARS"),
    sort_by: str = Query("timestamp", description="Column to sort by"),
    sort_dir: str = Query("desc", description="Sort direction: asc or desc"),
):
    """
    Get paginated Warrior scan history with filtering and sorting.
    
    Parses warrior_scan.log to extract individual PASS/FAIL entries as flat rows.
    
    Returns:
        entries: List of scan entries (symbol, result, gap_pct, rvol, score, reason, timestamp)
        total: Total count for pagination
        limit: Records per page
        offset: Current offset
    """
    from pathlib import Path
    import re
    
    # Find log directory
    log_dir = Path("data")
    if not log_dir.exists():
        log_dir = Path.home() / "Nexus2" / "data"
    
    if not log_dir.exists():
        return {"entries": [], "total": 0, "limit": limit, "offset": offset}
    
    # Read all rotated log files (warrior_scan.log, .1, .2, ... .7)
    all_lines = []
    base_log = log_dir / "warrior_scan.log"
    
    # Read main log file first
    if base_log.exists():
        try:
            with open(base_log, "r", encoding="utf-8") as f:
                all_lines.extend(f.readlines())
        except Exception:
            pass
    
    # Read rotated logs (.1 through .7)
    for i in range(1, 8):
        rotated_log = log_dir / f"warrior_scan.log.{i}"
        if rotated_log.exists():
            try:
                with open(rotated_log, "r", encoding="utf-8") as f:
                    all_lines.extend(f.readlines())
            except Exception:
                pass
    
    if not all_lines:
        return {"entries": [], "total": 0, "limit": limit, "offset": offset}
    
    # Patterns for parsing
    # NEW consolidated format: [PILLARS] PASS | SYMBOL | Gap:X% | Score: Y | Catalyst: Z | Float: N | RVOL: Mx
    pass_pattern_pillars_consolidated = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| \[PILLARS\] PASS \| (\w+) \| Gap:([0-9.]+)% \| Score: (\d+)[^|]* \| Catalyst: (\w+) \| Float: ([^|]+) \| RVOL: ([0-9.]+)x")
    # Legacy PILLARS format (no Gap%)
    pass_pattern_pillars_legacy = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| \[PILLARS\] PASS \| (\w+) \| Score: (\d+)[^|]* \| Catalyst: (\w+) \| Float: ([^|]+) \| RVOL: ([0-9.]+)x")
    # Legacy [SCAN] format (Gap/RVOL/Score)
    pass_pattern_scan = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| \[SCAN\] PASS \| (\w+) \| Gap:([0-9.]+)% \| RVOL:([0-9.]+)x \| Score:(\d+)")
    # Legacy format without label
    pass_pattern = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| PASS \| (\w+) \| Gap:([0-9.]+)% \| RVOL:([0-9.]+)x \| Score:(\d+)")
    # New FAIL format: includes Gap% and RVOL before Reason
    fail_pattern_new = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| FAIL \| (\w+) \| Gap:([0-9.-]+)% \| RVOL:([0-9.]+)x \| Reason: (.+)")
    # Old FAIL format: just Reason (for parsing historical logs)
    fail_pattern_old = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| FAIL \| (\w+) \| Gap:([0-9.-]+)% \| Reason: (.+)")
    # Legacy format: no metrics at all
    fail_pattern_legacy = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| FAIL \| (\w+) \| Reason: (.+)")
    
    all_entries = []
    
    for line in all_lines:
        line = line.strip()
        if not line:
            continue
        
        # Check NEW consolidated PILLARS format first (Gap + Score + Catalyst + Float + RVOL)
        match = pass_pattern_pillars_consolidated.match(line)
        if match:
            all_entries.append({
                "timestamp": match.group(1),
                "source": "PILLARS",
                "symbol": match.group(2),
                "result": "PASS",
                "gap_pct": float(match.group(3)),
                "score": int(match.group(4)),
                "catalyst": match.group(5),
                "float": match.group(6),
                "rvol": float(match.group(7)),
                "reason": None,
            })
            continue
        
        # Check legacy PILLARS format (no Gap%)
        match = pass_pattern_pillars_legacy.match(line)
        if match:
            all_entries.append({
                "timestamp": match.group(1),
                "source": "PILLARS",
                "symbol": match.group(2),
                "result": "PASS",
                "gap_pct": None,  # Not in legacy PILLARS format
                "score": int(match.group(3)),
                "catalyst": match.group(4),
                "float": match.group(5),
                "rvol": float(match.group(6)),
                "reason": None,
            })
            continue
        
        # Check legacy [SCAN] format (for old logs)
        match = pass_pattern_scan.match(line)
        if match:
            all_entries.append({
                "timestamp": match.group(1),
                "source": "SCAN",
                "symbol": match.group(2),
                "result": "PASS",
                "gap_pct": float(match.group(3)),
                "rvol": float(match.group(4)),
                "score": int(match.group(5)),
                "reason": None,
            })
            continue
        
        # Check legacy PASS (without label)
        match = pass_pattern.match(line)
        if match:
            all_entries.append({
                "timestamp": match.group(1),
                "source": None,  # No label
                "symbol": match.group(2),
                "result": "PASS",
                "gap_pct": float(match.group(3)),
                "rvol": float(match.group(4)),
                "score": int(match.group(5)),
                "reason": None,
            })
            continue
        
        # Check FAIL (new format with Gap + RVOL)
        match = fail_pattern_new.match(line)
        if match:
            all_entries.append({
                "timestamp": match.group(1),
                "symbol": match.group(2),
                "result": "FAIL",
                "gap_pct": float(match.group(3)),
                "rvol": float(match.group(4)),
                "score": None,
                "reason": match.group(5),
            })
            continue
        
        # Check FAIL (old format with Gap only)
        match = fail_pattern_old.match(line)
        if match:
            all_entries.append({
                "timestamp": match.group(1),
                "symbol": match.group(2),
                "result": "FAIL",
                "gap_pct": float(match.group(3)),
                "rvol": None,
                "score": None,
                "reason": match.group(4),
            })
            continue
        
        # Check FAIL (legacy format - no metrics)
        match = fail_pattern_legacy.match(line)
        if match:
            all_entries.append({
                "timestamp": match.group(1),
                "symbol": match.group(2),
                "result": "FAIL",
                "gap_pct": None,
                "rvol": None,
                "score": None,
                "reason": match.group(3),
            })
            continue
    
    # Apply filters
    # Note: Log timestamps are in UTC. Convert to ET for date/time comparison.
    from zoneinfo import ZoneInfo
    from datetime import datetime as dt
    utc_tz = ZoneInfo("UTC")
    et_tz = ZoneInfo("America/New_York")
    
    def get_local_datetime(ts_str: str) -> tuple[str, str]:
        """Convert UTC timestamp string to ET date and time strings."""
        try:
            utc_dt = dt.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=utc_tz)
            local_dt = utc_dt.astimezone(et_tz)
            return local_dt.strftime("%Y-%m-%d"), local_dt.strftime("%H:%M")
        except:
            return ts_str[:10], ts_str[11:16]  # Fallback to raw date/time
    
    if date_from or date_to or time_from or time_to:
        filtered = []
        for e in all_entries:
            local_date, local_time = get_local_datetime(e["timestamp"])
            # Date filter
            if date_from and local_date < date_from:
                continue
            if date_to and local_date > date_to:
                continue
            # Time filter (within the date range)
            if time_from and local_time < time_from:
                continue
            if time_to and local_time > time_to:
                continue
            filtered.append(e)
        all_entries = filtered
    
    if symbol:
        all_entries = [e for e in all_entries if e["symbol"].upper() == symbol.upper()]
    if result:
        all_entries = [e for e in all_entries if e["result"] == result.upper()]
    if source:
        all_entries = [e for e in all_entries if (e.get("source") or "").upper() == source.upper()]
    
    # Calculate total before pagination
    total = len(all_entries)
    
    # Apply sorting (handle mixed types - numeric fields need special handling)
    reverse = sort_dir.lower() == "desc"
    numeric_fields = {"gap_pct", "rvol", "score"}
    if sort_by in numeric_fields:
        # For numeric fields, use 0 as default and ensure float comparison
        all_entries.sort(key=lambda x: float(x.get(sort_by) or 0), reverse=reverse)
    else:
        all_entries.sort(key=lambda x: str(x.get(sort_by) or ""), reverse=reverse)
    
    # Apply pagination
    entries = all_entries[offset:offset + limit]
    
    return {
        "entries": entries,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# =============================================================================
# CATALYST AUDITS ENDPOINT (parses catalyst_audit.log)
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
    from pathlib import Path
    import re
    
    # Find log directory
    log_dir = Path("data")
    if not log_dir.exists():
        log_dir = Path.home() / "Nexus2" / "data"
    
    if not log_dir.exists():
        return {"entries": [], "total": 0, "limit": limit, "offset": offset}
    
    # Read all rotated log files
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
    
    if not all_lines:
        return {"entries": [], "total": 0, "limit": limit, "offset": offset}
    
    # Patterns for parsing
    # Header: 2026-01-30 13:41:00 | === CATX | Result: FAIL | Type: none ===
    header_pattern = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| === (\w+) \| Result: (PASS|FAIL) \| Type: (\w+) ===")
    # Headline: 2026-01-30 13:41:00 |   [1] ✗ no_match (conf=0.00): headline text
    headline_pattern = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \|   \[(\d+)\] ([✓✗]) (\w+) \(conf=([0-9.]+)\): (.+)")
    
    all_entries = []
    current_header = None
    
    for line in all_lines:
        line = line.strip()
        if not line:
            continue
        
        # Check for header line
        match = header_pattern.match(line)
        if match:
            current_header = {
                "timestamp": match.group(1),
                "symbol": match.group(2),
                "result": match.group(3),
                "catalyst_type": match.group(4),
            }
            continue
        
        # Check for headline line
        match = headline_pattern.match(line)
        if match and current_header:
            all_entries.append({
                "timestamp": match.group(1),
                "symbol": current_header["symbol"],
                "result": current_header["result"],
                "headline_num": int(match.group(2)),
                "passed": match.group(3) == "✓",
                "match_type": match.group(4),
                "confidence": float(match.group(5)),
                "headline": match.group(6),
            })
    
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
        all_entries = [e for e in all_entries if e["symbol"].upper() == symbol.upper()]
    if result:
        all_entries = [e for e in all_entries if e["result"] == result.upper()]
    if match_type:
        all_entries = [e for e in all_entries if e["match_type"] == match_type]
    
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
    has_tiebreaker: Optional[bool] = Query(None, description="Filter entries that used Pro tiebreaker"),
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
                        "regex_type": regex_info.get("type"),
                        "regex_conf": regex_info.get("conf", 0),
                        "flash_valid": flash_result.get("valid"),
                        "flash_type": flash_result.get("type"),
                        "flash_reason": flash_result.get("reason", "")[:40],
                        "flash_ms": flash_result.get("latency_ms", 0),
                        "pro_valid": pro_result.get("valid") if pro_result else None,
                        "pro_type": pro_result.get("type") if pro_result else None,
                        "pro_reason": pro_result.get("reason", "")[:40] if pro_result else None,
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
        all_entries = [e for e in all_entries if e["symbol"] and e["symbol"].upper() == symbol.upper()]
    if flash_valid is not None:
        all_entries = [e for e in all_entries if e["flash_valid"] == flash_valid]
    if has_tiebreaker is not None:
        all_entries = [e for e in all_entries if e["used_tiebreaker"] == has_tiebreaker]
    
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
