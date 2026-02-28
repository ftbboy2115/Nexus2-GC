"""
Centralized Time Utilities

Single source of truth for all timezone-related operations.
All code should use these functions instead of raw datetime calls.

WHY THIS EXISTS:
- VPS runs on UTC, local dev runs on ET
- datetime.now() returns server's local time (inconsistent)
- Trading logic requires Eastern Time
- Scattered pytz calls led to 7+ timezone bug fixes

USAGE:
    from nexus2.utils.time_utils import now_et, format_et, utc_to_et
    
    # Get current time in ET
    current = now_et()
    
    # Format for display
    timestamp_str = format_et()  # "2026-01-15 06:30:00 ET"
    
    # Convert UTC datetime to ET
    et_time = utc_to_et(some_utc_datetime)

ENFORCEMENT:
    Run `python scripts/migrate_to_time_utils.py` to find and fix violations.
    This script detects datetime.now() and datetime.utcnow() in codebase.
    Use --apply flag to auto-fix. Dry run by default.
"""

from datetime import datetime, time as dt_time
from typing import Optional
import pytz


# Eastern timezone constant - THE source of truth
EASTERN = pytz.timezone('America/New_York')
UTC = pytz.UTC


def now_et() -> datetime:
    """
    Get current time in Eastern timezone.
    
    Use this INSTEAD of datetime.now() everywhere.
    """
    return datetime.now(EASTERN)


def now_utc() -> datetime:
    """
    Get current time in UTC (timezone-aware).
    
    Use this INSTEAD of datetime.utcnow() everywhere.
    """
    return datetime.now(UTC)


def sim_aware_now_utc() -> datetime:
    """Returns sim clock time if in sim context, else real UTC.
    
    Use this INSTEAD of now_utc() in trading logic that must
    respect simulated time (exit logic, grace periods, cooldowns).
    
    In live mode, the ContextVar is unset → falls back to now_utc().
    In sim mode, the ContextVar is set per-case → returns sim time.
    
    DO NOT use this for:
    - DB timestamps (use now_utc())
    - API response timestamps (use now_utc())
    - Dataclass defaults (use now_utc_factory())
    - Logging timestamps (use now_utc())
    """
    from nexus2.adapters.simulation.sim_clock import _sim_clock_ctx
    clock = _sim_clock_ctx.get()
    if clock and clock.current_time:
        return clock.current_time
    return now_utc()


def sim_aware_now_et() -> datetime:
    """Returns sim clock time in ET if in sim context, else real ET.
    
    Same as sim_aware_now_utc() but returns Eastern Time.
    Use for cases where datetime.now(ET) was used directly.
    """
    from nexus2.adapters.simulation.sim_clock import _sim_clock_ctx
    clock = _sim_clock_ctx.get()
    if clock and clock.current_time:
        return clock.current_time.astimezone(EASTERN)
    return now_et()


def now_utc_factory() -> datetime:
    """
    Factory function for dataclass default_factory.
    
    Use this in dataclasses INSTEAD of datetime.now or datetime.utcnow:
    
        # WRONG:
        created_at: datetime = field(default_factory=datetime.now)
        
        # CORRECT:
        created_at: datetime = field(default_factory=now_utc_factory)
    
    Returns timezone-aware UTC datetime.
    """
    return datetime.now(UTC)


def now_et_factory() -> datetime:
    """
    Factory function for dataclass default_factory (Eastern Time).
    
    Use this when you specifically need ET timestamps in dataclasses.
    Most dataclasses should use now_utc_factory() instead.
    """
    return datetime.now(EASTERN)


def format_et(dt: Optional[datetime] = None, include_date: bool = True) -> str:
    """
    Format datetime as Eastern Time string.
    
    Args:
        dt: Datetime to format (defaults to now)
        include_date: If True, includes date. If False, time only.
        
    Returns:
        "2026-01-15 06:30:00 ET" or "06:30:00 ET"
    """
    if dt is None:
        dt = now_et()
    elif dt.tzinfo is None:
        # Naive datetime - assume it's already ET
        dt = EASTERN.localize(dt)
    elif dt.tzinfo != EASTERN:
        # Convert to ET
        dt = dt.astimezone(EASTERN)
    
    if include_date:
        return dt.strftime("%Y-%m-%d %H:%M:%S ET")
    else:
        return dt.strftime("%H:%M:%S ET")


def utc_to_et(dt: datetime) -> datetime:
    """
    Convert UTC datetime to Eastern Time.
    
    Handles both naive (assumes UTC) and aware datetimes.
    """
    if dt.tzinfo is None:
        # Naive datetime - assume UTC
        dt = UTC.localize(dt)
    return dt.astimezone(EASTERN)


def et_to_utc(dt: datetime) -> datetime:
    """
    Convert Eastern Time datetime to UTC.
    
    Handles both naive (assumes ET) and aware datetimes.
    """
    if dt.tzinfo is None:
        # Naive datetime - assume ET
        dt = EASTERN.localize(dt)
    return dt.astimezone(UTC)


def format_iso_utc(dt: Optional[datetime]) -> Optional[str]:
    """
    Format datetime as ISO 8601 string with Z suffix for API/JSON responses.
    
    This format is compatible with JavaScript's Date() constructor.
    
    Args:
        dt: Datetime to format (any timezone)
        
    Returns:
        "2026-01-15T06:30:00Z" or None if dt is None
    """
    if dt is None:
        return None
    # Guard against non-datetime values (e.g., strings from bad DB data)
    if not isinstance(dt, datetime):
        return str(dt)
    # Convert to UTC if timezone-aware
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def is_market_hours(dt: Optional[datetime] = None) -> bool:
    """
    Check if given time is during regular market hours (9:30 AM - 4:00 PM ET).
    
    Args:
        dt: Datetime to check (defaults to now)
        
    Returns:
        True if during regular market hours
    """
    if dt is None:
        dt = now_et()
    elif dt.tzinfo is None:
        dt = EASTERN.localize(dt)
    elif dt.tzinfo != EASTERN:
        dt = dt.astimezone(EASTERN)
    
    market_open = dt_time(9, 30)
    market_close = dt_time(16, 0)
    current_time = dt.time()
    
    return market_open <= current_time < market_close


def is_premarket(dt: Optional[datetime] = None) -> bool:
    """
    Check if given time is during pre-market hours (4:00 AM - 9:29 AM ET).
    """
    if dt is None:
        dt = now_et()
    elif dt.tzinfo is None:
        dt = EASTERN.localize(dt)
    elif dt.tzinfo != EASTERN:
        dt = dt.astimezone(EASTERN)
    
    premarket_open = dt_time(4, 0)
    market_open = dt_time(9, 30)
    current_time = dt.time()
    
    return premarket_open <= current_time < market_open


def is_afterhours(dt: Optional[datetime] = None) -> bool:
    """
    Check if given time is during after-hours (4:00 PM - 8:00 PM ET).
    """
    if dt is None:
        dt = now_et()
    elif dt.tzinfo is None:
        dt = EASTERN.localize(dt)
    elif dt.tzinfo != EASTERN:
        dt = dt.astimezone(EASTERN)
    
    market_close = dt_time(16, 0)
    afterhours_close = dt_time(20, 0)
    current_time = dt.time()
    
    return market_close <= current_time < afterhours_close


def is_extended_hours(dt: Optional[datetime] = None) -> bool:
    """
    Check if given time is during extended hours (4:00 AM - 8:00 PM ET).
    
    This is the full Warrior trading window.
    """
    if dt is None:
        dt = now_et()
    elif dt.tzinfo is None:
        dt = EASTERN.localize(dt)
    elif dt.tzinfo != EASTERN:
        dt = dt.astimezone(EASTERN)
    
    extended_open = dt_time(4, 0)
    extended_close = dt_time(20, 0)
    current_time = dt.time()
    
    return extended_open <= current_time < extended_close
