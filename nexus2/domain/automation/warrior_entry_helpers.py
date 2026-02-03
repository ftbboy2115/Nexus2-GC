"""
Warrior Entry Helpers

Shared helper functions for warrior entry logic.
Extracted to break circular import between warrior_engine_entry.py and warrior_entry_patterns.py.

These are PURE UTILITY FUNCTIONS that don't depend on engine internals.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    from nexus2.domain.automation.warrior_engine import WarriorEngine
    from nexus2.domain.automation.warrior_engine_types import WatchedCandidate

logger = logging.getLogger(__name__)


# =============================================================================
# VOLUME HELPER FUNCTIONS
# =============================================================================


def check_volume_confirmed(candles: list, lookback: int = 10) -> Tuple[bool, int, float]:
    """
    Check if current bar has volume expansion.
    
    Ross Cameron requires volume confirmation on breakouts:
    - Current bar volume > average of recent bars
    - Current bar volume > prior bar
    
    Args:
        candles: List of candle objects with .volume attribute
        lookback: Number of bars to average (default 10)
    
    Returns:
        (is_confirmed, current_volume, avg_volume)
    """
    if not candles or len(candles) < 2:
        return False, 0, 0.0
    
    current_vol = candles[-1].volume if hasattr(candles[-1], 'volume') else 0
    prior_vol = candles[-2].volume if hasattr(candles[-2], 'volume') else 0
    
    # Calculate average volume over lookback period
    if len(candles) >= lookback:
        avg_vol = sum(c.volume for c in candles[-lookback:]) / lookback
    else:
        avg_vol = sum(c.volume for c in candles) / len(candles)
    
    # Confirmed if: current > average OR current > prior
    is_confirmed = current_vol >= avg_vol or current_vol > prior_vol
    
    return is_confirmed, current_vol, avg_vol


def check_volume_expansion(
    candles: list,
    min_expansion: float = 3.0,
    lookback: int = 10
) -> Tuple[bool, float, str]:
    """
    Check if current bar has volume expansion vs recent average.
    
    Ross Cameron requires volume EXPLOSION on entries - not just "some volume".
    Validated on LRHC: 06:40 had 2.6x (blocked), 07:27 had 16.3x (passed).
    
    Args:
        candles: List of candle objects with .volume attribute
        min_expansion: Minimum volume ratio required (default 3.0x)
        lookback: Number of bars to use for average (default 10)
    
    Returns:
        (passes, ratio, reason_if_blocked)
    """
    if not candles or len(candles) < lookback:
        return False, 0.0, f"Need {lookback} bars (got {len(candles) if candles else 0})"
    
    # Use previous (lookback-1) bars for average, current bar for comparison
    prev_vols = [c.volume for c in candles[-(lookback):-1] if hasattr(c, 'volume')]
    if not prev_vols:
        return False, 0.0, "No volume data in candles"
    
    avg_vol = sum(prev_vols) / len(prev_vols)
    current_vol = candles[-1].volume if hasattr(candles[-1], 'volume') else 0
    ratio = current_vol / avg_vol if avg_vol > 0 else 0
    
    if ratio < min_expansion:
        return False, ratio, f"{ratio:.1f}x < {min_expansion}x required"
    
    return True, ratio, ""


def check_high_volume_red_candle(candles: list, volume_multiplier: float = 1.5) -> Tuple[bool, int, float]:
    """
    Check if current bar is a high-volume red candle (distribution signal).
    
    Ross Cameron (Jul 2024 Volume Tutorial): "this highest volume candle being 
    red that is a red flag literally" - indicates selling pressure/distribution.
    
    Args:
        candles: List of candle objects with .open, .close, .volume attributes
        volume_multiplier: How much above average to be "high volume" (default 1.5x)
    
    Returns:
        (is_red_flag, current_volume, avg_volume)
    """
    if not candles or len(candles) < 5:
        return False, 0, 0.0
    
    current = candles[-1]
    
    # Check if candle is red (close < open)
    has_open = hasattr(current, 'open') and current.open is not None
    has_close = hasattr(current, 'close') and current.close is not None
    
    if not has_open or not has_close:
        return False, 0, 0.0
    
    is_red = float(current.close) < float(current.open)
    
    if not is_red:
        return False, 0, 0.0  # Green candle, no red flag
    
    # Check if volume is significantly above average
    current_vol = current.volume if hasattr(current, 'volume') else 0
    lookback = min(10, len(candles) - 1)
    avg_vol = sum(c.volume for c in candles[-lookback-1:-1]) / lookback if lookback > 0 else 0
    
    is_high_volume = current_vol >= avg_vol * volume_multiplier
    
    if is_red and is_high_volume:
        return True, current_vol, avg_vol
    
    return False, current_vol, avg_vol


# =============================================================================
# MARKET ACTIVITY HELPER FUNCTIONS
# =============================================================================


def check_active_market(
    candles: list, 
    min_bars: int = 5, 
    min_volume_per_bar: int = 1000,
    max_time_gap_minutes: int = 15,
) -> Tuple[bool, str]:
    """
    Check if there's active trading happening (not dead premarket).
    
    A trader looks at a chart and sees "nothing is happening" when:
    - Bars are sparse (hour+ gaps between them)  
    - Volume is tiny (250-300 shares)
    - No price action
    
    Active market requires:
    - At least min_bars in recent history
    - Average volume per bar above threshold
    - No huge gaps between bars (indicating dead market)
    
    Args:
        candles: List of candle objects with .time and .volume
        min_bars: Minimum number of bars required (default 5)
        min_volume_per_bar: Minimum average volume per bar (default 1000)
        max_time_gap_minutes: Max gap between bars to be "active" (default 15)
    
    Returns:
        (is_active, reason_if_inactive)
    """
    if not candles or len(candles) < min_bars:
        return False, f"Only {len(candles) if candles else 0} bars (need {min_bars})"
    
    # Check average volume per bar
    total_vol = sum(c.volume for c in candles if hasattr(c, 'volume'))
    avg_vol = total_vol / len(candles)
    
    if avg_vol < min_volume_per_bar:
        return False, f"Low volume ({int(avg_vol)} avg vs {min_volume_per_bar} min)"
    
    # Check for large time gaps (dead market)
    # Parse time strings like "04:54", "05:54" and check gaps
    if len(candles) >= 2:
        last_gap_minutes = 0
        for i in range(1, min(5, len(candles))):  # Check last 5 bars
            try:
                curr_time = candles[-i].time if hasattr(candles[-i], 'time') else None
                prev_time = candles[-i-1].time if hasattr(candles[-i-1], 'time') else None
                
                if curr_time and prev_time:
                    # Parse "HH:MM" format
                    curr_parts = curr_time.split(":")
                    prev_parts = prev_time.split(":")
                    
                    if len(curr_parts) == 2 and len(prev_parts) == 2:
                        curr_mins = int(curr_parts[0]) * 60 + int(curr_parts[1])
                        prev_mins = int(prev_parts[0]) * 60 + int(prev_parts[1])
                        gap = curr_mins - prev_mins
                        
                        if gap > last_gap_minutes:
                            last_gap_minutes = gap
            except (ValueError, AttributeError, IndexError):
                pass
        
        if last_gap_minutes > max_time_gap_minutes:
            return False, f"Large gap ({last_gap_minutes}min between bars)"
    
    return True, ""


def check_falling_knife(
    current_price: Decimal, 
    snapshot, 
    min_candles: int = 20
) -> Tuple[bool, str]:
    """
    Check if stock is in a falling knife pattern (avoid entry).
    
    Falling knife = below 20 EMA AND MACD negative
    PODC case: dropped from $3.30 to $2.50, VWAP break was death
    
    Args:
        current_price: Current stock price
        snapshot: Technical snapshot with ema_20 and is_macd_bullish
        min_candles: Minimum candles required for reliable check
    
    Returns:
        (is_falling_knife, reason_string)
    """
    if not snapshot:
        return False, ""
    
    is_above_20_ema = (
        snapshot.ema_20 and 
        current_price > Decimal(str(snapshot.ema_20))
    )
    macd_ok = snapshot.is_macd_bullish
    
    # Falling knife: below 20 EMA AND MACD negative
    if not is_above_20_ema and not macd_ok:
        ema_str = f"${snapshot.ema_20:.2f}" if snapshot.ema_20 else "N/A"
        reason = f"below 20 EMA {ema_str}, MACD negative"
        return True, reason
    
    return False, ""


# =============================================================================
# TECHNICAL UPDATE HELPER FUNCTIONS
# =============================================================================


async def update_candidate_technicals(
    engine: "WarriorEngine",
    watched: "WatchedCandidate",
    current_price: Decimal,
) -> None:
    """
    Update VWAP/EMA tracking for dynamic_score (TOP_PICK_ONLY uses this).
    
    CRITICAL FIX (Feb 1 2026): Dual calculation approach
    - MACD/EMA need ALL bars (including continuity) for warm-up at market open
    - VWAP should only use TODAY's session bars (resets daily)
    
    Args:
        engine: WarriorEngine instance with _get_intraday_bars
        watched: WatchedCandidate to update with technicals
        current_price: Current stock price
    """
    symbol = watched.candidate.symbol
    watched.current_price = current_price
    
    if not engine._get_intraday_bars:
        logger.info(f"[Warrior Entry] {symbol}: _get_intraday_bars not set")
        return
    
    try:
        candles = await engine._get_intraday_bars(symbol, "1min", limit=30)
        if not candles or len(candles) < 10:
            candle_count = len(candles) if candles else 0
            logger.info(f"[Warrior Entry] {symbol}: Not enough candles for technicals ({candle_count} < 10)")
            return
        
        from nexus2.domain.indicators import get_technical_service
        tech = get_technical_service()
        
        # Get current simulation time to determine session phase
        current_hour = None
        try:
            from nexus2.adapters.simulation.sim_clock import get_sim_clock
            clock = get_sim_clock()
            if clock.is_active():
                time_str = clock.get_time_string()  # "HH:MM"
                current_hour = int(time_str.split(':')[0])
        except Exception:
            pass
        
        # Filter for TODAY's session bars only
        # Premarket: hours 4-9 (exclude afternoon continuity bars 15-16 from yesterday)
        # Regular hours: hours 9-16
        today_candles = []
        for c in candles:
            bar_time = getattr(c, 'time', '') or ''
            if not bar_time:
                # LIVE MODE FIX: Bars from Alpaca don't have .time attribute
                # Default to including them since Alpaca returns today's bars
                today_candles.append(c)
                continue
            try:
                hour = int(bar_time.split(':')[0])
                
                # If we know current sim hour, filter appropriately
                if current_hour is not None:
                    if current_hour < 10:  # Premarket (04:00-09:59)
                        # Only include premarket bars (4-9), exclude afternoon (10+)
                        if 4 <= hour < 10:
                            today_candles.append(c)
                    else:  # Regular hours (10:00+)
                        # Include all today's bars up to current hour
                        if 4 <= hour <= current_hour:
                            today_candles.append(c)
                else:
                    # LIVE MODE: Include all today's session bars (4 AM - 8 PM)
                    if 4 <= hour <= 20:
                        today_candles.append(c)
            except (ValueError, IndexError):
                today_candles.append(c)
        
        # ALL candles for MACD/EMA (includes continuity)
        all_candle_dicts = [
            {"high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
            for c in candles
        ]
        
        # TODAY's candles only for VWAP
        today_candle_dicts = [
            {"high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
            for c in today_candles
        ]
        
        # Get MACD/EMA from full history
        snapshot = tech.get_snapshot(symbol, all_candle_dicts, float(current_price))
        
        # Update EMA from full snapshot
        if snapshot.ema_9:
            watched.current_ema_9 = Decimal(str(snapshot.ema_9))
            watched.is_above_ema_9 = current_price > watched.current_ema_9
        watched.trend_updated_at = datetime.now(timezone.utc)
        
        # Calculate VWAP separately from today's bars only
        if len(today_candle_dicts) >= 5:
            vwap_snapshot = tech.get_snapshot(symbol, today_candle_dicts, float(current_price))
            if vwap_snapshot.vwap:
                watched.current_vwap = Decimal(str(vwap_snapshot.vwap))
                watched.is_above_vwap = current_price > watched.current_vwap
                logger.debug(
                    f"[Warrior Entry] {symbol}: VWAP=${vwap_snapshot.vwap:.2f} (from {len(today_candles)} today bars), "
                    f"price=${current_price:.2f}, above={watched.is_above_vwap}"
                )
            else:
                logger.info(f"[Warrior Entry] {symbol}: No VWAP in snapshot (today_candles={len(today_candles)})")
        else:
            logger.info(f"[Warrior Entry] {symbol}: Not enough today's candles for VWAP ({len(today_candles)} < 5)")
    except Exception as e:
        logger.warning(f"[Warrior Entry] {symbol}: Trend update failed: {e}")
