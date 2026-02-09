"""
Shared VWAP Utilities for Warrior Bot

Single source of truth for session VWAP calculation.
Both the pattern detector and entry guard use these functions
to ensure consistent VWAP values.

WHY THIS EXISTS:
- Pattern detector and entry guard were computing VWAP independently
- Pattern used raw 30-candle window → wrong VWAP ($15.83)
- Guard used 50 candles filtered by hour → closer but imprecise
- TradingView session VWAP was $17.64
- Having two different VWAPs caused false triggers and spam

USAGE:
    from nexus2.domain.automation.warrior_vwap_utils import (
        get_session_bar_limit,
        get_session_vwap,
    )
    
    # Get how many 1-min bars since 4 AM
    limit = get_session_bar_limit()  # e.g., 268 at 8:28 AM
    
    # Get session VWAP for a symbol
    vwap = await get_session_vwap(engine, symbol, current_price)
"""

import logging
from decimal import Decimal
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from nexus2.domain.automation.warrior_engine import WarriorEngine

logger = logging.getLogger(__name__)

# Session start hour (4 AM ET for extended hours)
SESSION_START_HOUR = 4
SESSION_START_MINUTE = 0


def get_session_bar_limit() -> int:
    """
    Calculate the exact number of 1-minute bars from 4 AM ET to now.
    
    Uses the sim clock if active (simulation mode), otherwise uses
    real Eastern Time. Adds a small buffer for safety.
    
    Returns:
        Number of 1-minute bars to request (minimum 30, maximum 1000)
    """
    current_hour = None
    current_minute = None
    
    try:
        from nexus2.adapters.simulation.sim_clock import get_simulation_clock
        clock = get_simulation_clock()
        if clock and clock._active:
            time_str = clock.get_time_string()  # "HH:MM"
            parts = time_str.split(':')
            current_hour = int(parts[0])
            current_minute = int(parts[1])
    except Exception:
        pass
    
    if current_hour is None:
        # Not in simulation — use real Eastern Time
        try:
            from nexus2.utils.time_utils import now_et
            et_now = now_et()
            current_hour = et_now.hour
            current_minute = et_now.minute
        except Exception:
            # Fallback: request plenty of bars
            return 500
    
    # Calculate minutes since session start (4:00 AM ET)
    minutes_since_start = (current_hour * 60 + current_minute) - (SESSION_START_HOUR * 60 + SESSION_START_MINUTE)
    
    if minutes_since_start <= 0:
        # Before 4 AM or at exactly 4 AM — minimal bars
        return 30
    
    # Add 10-bar buffer for safety (data gaps, partial bars, etc.)
    bar_limit = minutes_since_start + 10
    
    # Clamp to reasonable range
    return max(30, min(bar_limit, 1000))


async def get_session_vwap(
    engine: "WarriorEngine",
    symbol: str,
    current_price: float,
) -> Optional[Decimal]:
    """
    Get the session VWAP for a symbol using dynamically-sized bar request.
    
    This is the single source of truth for VWAP in the Warrior bot.
    Both the pattern detector and entry guard should use this.
    
    The bar limit is calculated from 4 AM ET to the current time,
    ensuring we get exactly today's session bars without contamination
    from yesterday's data.
    
    Args:
        engine: WarriorEngine instance (has _get_intraday_bars)
        symbol: Stock ticker symbol
        current_price: Current price for snapshot calculation
        
    Returns:
        Session VWAP as Decimal, or None if unavailable
    """
    if not engine._get_intraday_bars:
        return None
    
    try:
        bar_limit = get_session_bar_limit()
        candles = await engine._get_intraday_bars(symbol, "1min", limit=bar_limit)
        
        if not candles or len(candles) < 5:
            return None
        
        from nexus2.domain.indicators import get_technical_service
        tech = get_technical_service()
        
        candle_dicts = [
            {"high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
            for c in candles
        ]
        
        snapshot = tech.get_snapshot(symbol, candle_dicts, float(current_price))
        
        if snapshot and snapshot.vwap:
            return Decimal(str(snapshot.vwap))
        
        return None
        
    except Exception as e:
        logger.debug(f"[Warrior VWAP] {symbol}: Session VWAP fetch failed: {e}")
        return None
