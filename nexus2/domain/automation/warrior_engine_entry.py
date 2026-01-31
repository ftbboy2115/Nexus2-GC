"""
Warrior Engine Entry Logic

Extracted entry trigger detection and position entry execution
from warrior_engine.py for maintainability.

Functions take the WarriorEngine instance as the first parameter.
"""

from __future__ import annotations

import logging
from datetime import time as dt_time
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from nexus2.domain.automation.warrior_engine_types import (
    EntryTriggerType,
    WatchedCandidate,
)
from nexus2.utils.time_utils import now_utc

if TYPE_CHECKING:
    from nexus2.domain.automation.warrior_engine import WarriorEngine


logger = logging.getLogger(__name__)


# =============================================================================
# ENTRY QUALITY FILTERS (MODULAR)
# =============================================================================


def check_volume_confirmed(candles: list, lookback: int = 10) -> tuple[bool, int, float]:
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


def check_active_market(
    candles: list, 
    min_bars: int = 5, 
    min_volume_per_bar: int = 1000,
    max_time_gap_minutes: int = 15,
) -> tuple[bool, str]:
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
) -> tuple[bool, str]:
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


def check_high_volume_red_candle(candles: list, volume_multiplier: float = 1.5) -> tuple[bool, int, float]:
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
# ENTRY TRIGGER DETECTION
# =============================================================================


async def check_entry_triggers(engine: "WarriorEngine") -> None:
    """
    Check all watched candidates for entry triggers.
    
    Evaluates each candidate in the watchlist for:
    - DIP-FOR-LEVEL pattern (below PMH, near psychological level)
    - PMH breakout
    - ORB breakout
    - Pullback pattern (above PMH, pullback from HOD)
    
    Args:
        engine: The WarriorEngine instance
    """
    if not engine._get_quote:
        return
    
    for symbol, watched in list(engine._watchlist.items()):
        try:
            current_price = await engine._get_quote(symbol)
            if not current_price:
                continue
            
            current_price = Decimal(str(current_price))
            
            # SANITY CHECK: Validate quote against last candle close
            # Catches phantom inflated quotes (e.g., BATL $5.14 vs actual $4.80)
            # that cause bad limit prices and immediate losses
            if engine._get_intraday_bars:
                try:
                    sanity_candles = await engine._get_intraday_bars(symbol, "1min", limit=2)
                    if sanity_candles and len(sanity_candles) >= 1:
                        last_close = Decimal(str(sanity_candles[-1].close))
                        if last_close > 0:
                            deviation_pct = abs((current_price - last_close) / last_close * 100)
                            if deviation_pct > 5:
                                logger.warning(
                                    f"[Warrior Entry] {symbol}: PHANTOM QUOTE DETECTED! "
                                    f"Quote ${current_price:.2f} vs candle close ${last_close:.2f} "
                                    f"({deviation_pct:.1f}% deviation) - using candle close"
                                )
                                current_price = last_close
                except Exception as e:
                    logger.debug(f"[Warrior Entry] {symbol}: Candle sanity check failed: {e}")
            
            # Track intraday high for pullback detection
            if watched.recent_high is None or current_price > watched.recent_high:
                watched.recent_high = current_price
            
            # UPDATE VWAP/EMA TRACKING for dynamic_score (TOP_PICK_ONLY uses this)
            # Calculate once per cycle, reuse for entry guard later
            watched.current_price = current_price
            if engine._get_intraday_bars:
                try:
                    candles = await engine._get_intraday_bars(symbol, "1min", limit=30)
                    if candles and len(candles) >= 10:
                        from nexus2.domain.indicators import get_technical_service
                        from datetime import datetime, timezone
                        tech = get_technical_service()
                        candle_dicts = [
                            {"high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
                            for c in candles
                        ]
                        snapshot = tech.get_snapshot(symbol, candle_dicts, float(current_price))
                        
                        # Store trend data on watched candidate
                        if snapshot.vwap:
                            watched.current_vwap = Decimal(str(snapshot.vwap))
                            watched.is_above_vwap = current_price > watched.current_vwap
                            logger.debug(
                                f"[Warrior Entry] {symbol}: VWAP=${snapshot.vwap:.2f}, "
                                f"price=${current_price:.2f}, above={watched.is_above_vwap}"
                            )
                        else:
                            logger.info(f"[Warrior Entry] {symbol}: No VWAP in snapshot (candles={len(candles)})")
                        if snapshot.ema_9:
                            watched.current_ema_9 = Decimal(str(snapshot.ema_9))
                            watched.is_above_ema_9 = current_price > watched.current_ema_9
                        watched.trend_updated_at = datetime.now(timezone.utc)
                    else:
                        candle_count = len(candles) if candles else 0
                        logger.info(f"[Warrior Entry] {symbol}: Not enough candles for VWAP ({candle_count} < 10)")
                except Exception as e:
                    logger.warning(f"[Warrior Entry] {symbol}: Trend update failed: {e}")
            else:
                logger.info(f"[Warrior Entry] {symbol}: _get_intraday_bars not set")
            
            # EXTENDED STOCK DETECTION: Use micro-pullback for stocks already up >100%
            # Ross methodology: Don't wait for PMH break on highly extended stocks
            # Example: VERO at 375% gap - enter on swing high break, not PMH
            gap_percent = float(getattr(watched.candidate, 'gap_percent', 0) or 0)
            is_extended = gap_percent > engine.config.extension_threshold
            
            if is_extended and engine.config.micro_pullback_enabled:
                logger.info(
                    f"[Warrior Entry] {symbol}: EXTENDED STOCK detected ({gap_percent:.0f}% gap > "
                    f"{engine.config.extension_threshold}% threshold) - routing to MICRO_PULLBACK"
                )
                await check_micro_pullback_entry(engine, watched, current_price)
                continue  # Skip PMH break logic for extended stocks
            
            # ROSS RE-ENTRY LOGIC: Track when price drops below PMH
            # This enables "curl back up" pattern detection for re-entries
            if current_price < watched.pmh:
                if watched.entry_triggered and not watched.last_below_pmh:
                    logger.info(
                        f"[Warrior Entry] {symbol}: Price below PMH "
                        f"(${current_price:.2f} < ${watched.pmh:.2f}) - ready for re-entry"
                    )
                watched.last_below_pmh = True
                
                # Track pullback depth for dip-for-level detection
                if watched.recent_high:
                    watched.dip_from_high_pct = float(
                        (watched.recent_high - current_price) / watched.recent_high * 100
                    )
                
                # DIP-FOR-LEVEL PATTERN: Ross buys dips near psychological levels
                # Example: TNMG at $3.93, target $4.00 level
                if engine.config.dip_for_level_enabled and not watched.entry_triggered:
                    # FALLING KNIFE FILTER: Block dip-for-level in sustained downtrends
                    # PAVM case: stock dropped from $24 to $13 over 3 hours — not a dip, it's death
                    # Check: must be above 20 EMA OR MACD positive (momentum recovering)
                    is_falling_knife = False
                    if engine._get_intraday_bars:
                        try:
                            candles = await engine._get_intraday_bars(symbol, "1min", limit=30)
                            if candles and len(candles) >= 20:
                                from nexus2.domain.indicators import get_technical_service
                                tech = get_technical_service()
                                candle_dicts = [
                                    {"high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
                                    for c in candles
                                ]
                                snapshot = tech.get_snapshot(symbol, candle_dicts, float(current_price))
                                
                                # Check trend conditions
                                is_above_20_ema = snapshot.ema_20 and current_price > Decimal(str(snapshot.ema_20))
                                macd_ok = snapshot.is_macd_bullish
                                
                                # FALLING KNIFE: Below 20 EMA AND MACD negative
                                if not is_above_20_ema and not macd_ok:
                                    is_falling_knife = True
                                    logger.info(
                                        f"[Warrior Entry] {symbol}: FALLING KNIFE - blocked dip entry "
                                        f"(below 20 EMA ${snapshot.ema_20:.2f if snapshot.ema_20 else 'N/A'}, "
                                        f"MACD negative)"
                                    )
                        except Exception as e:
                            logger.debug(f"[Warrior Entry] {symbol}: Falling knife check failed: {e}")
                    
                    # Skip entry if falling knife detected
                    if is_falling_knife:
                        continue
                    
                    levels = engine._get_key_levels(current_price)
                    levels_above = [l for l in levels if l > current_price]
                    if levels_above:
                        nearest_level = min(levels_above)
                        distance_cents = int((nearest_level - current_price) * 100)
                        
                        if distance_cents <= engine.config.level_proximity_cents:
                            watched.target_level = nearest_level
                            logger.info(
                                f"[Warrior Entry] {symbol}: DIP-FOR-LEVEL pattern "
                                f"(${current_price:.2f} near ${nearest_level}, "
                                f"dip {watched.dip_from_high_pct:.1f}%)"
                            )
                            await enter_position(
                                engine,
                                watched,
                                current_price,
                                EntryTriggerType.DIP_FOR_LEVEL
                            )
                continue  # Skip PMH/ORB checks when below PMH
            
            # Price is above PMH - check if this is a fresh breakout after pullback
            if watched.entry_triggered and watched.last_below_pmh:
                # This is a RE-ENTRY attempt after price curled back up (Ross pattern)
                watched.last_below_pmh = False
                watched.entry_triggered = False  # Reset to allow new entry attempt
                watched.entry_attempt_count += 1
                logger.info(
                    f"[Warrior Entry] {symbol}: Fresh breakout after pullback "
                    f"(re-entry attempt #{watched.entry_attempt_count})"
                )
            
            if watched.entry_triggered:
                # PULLBACK PATTERN (above PMH): Ross's "break through high after dip"
                # When price has run above PMH, then pulls back from HOD
                # Re-entry on "first candle to make new high" after pullback
                if engine.config.pullback_enabled and watched.recent_high:
                    pullback_pct = float(
                        (watched.recent_high - current_price) / watched.recent_high * 100
                    )
                    watched.dip_from_high_pct = pullback_pct
                    
                    # Trigger if 2-10% pullback from HOD and near a level (or VWAP)
                    if 2.0 <= pullback_pct <= 10.0:
                        # Get levels including VWAP
                        levels = engine._get_key_levels(current_price)
                        
                        # Fetch VWAP from technical service
                        vwap = None
                        if engine._get_intraday_bars:
                            try:
                                candles = await engine._get_intraday_bars(symbol, "1min", limit=30)
                                if candles and len(candles) >= 5:
                                    from nexus2.domain.indicators import get_technical_service
                                    tech = get_technical_service()
                                    candle_dicts = [
                                        {"high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
                                        for c in candles
                                    ]
                                    snapshot = tech.get_snapshot(symbol, candle_dicts, float(current_price))
                                    if snapshot.vwap:
                                        vwap = snapshot.vwap
                                        levels.append(vwap)
                            except Exception as e:
                                logger.debug(f"[Warrior Entry] {symbol}: VWAP fetch failed: {e}")
                        
                        # Check for entry near levels OR at VWAP support
                        should_enter = False
                        entry_reason = None
                        
                        # Pattern 1: VWAP BOUNCE - price sitting at/near VWAP support
                        # Ross: "VWAP bounce on stock meeting 5 pillars"
                        if vwap and current_price >= vwap:
                            distance_above_vwap = int((current_price - vwap) * 100)
                            if distance_above_vwap <= 15:  # Within 15c above VWAP
                                should_enter = True
                                entry_reason = f"VWAP bounce (${vwap:.2f})"
                        
                        # Pattern 2: Near round-number level above
                        if not should_enter:
                            levels_above = [l for l in levels if l > current_price]
                            if levels_above:
                                nearest_level = min(levels_above)
                                distance_cents = int((nearest_level - current_price) * 100)
                                vwap_proximity = 15 if vwap and nearest_level == vwap else engine.config.level_proximity_cents
                                
                                if distance_cents <= vwap_proximity:
                                    should_enter = True
                                    entry_reason = f"${nearest_level}" if nearest_level != vwap else "VWAP"
                                    watched.target_level = nearest_level
                        
                        if should_enter:
                            watched.entry_triggered = False  # Reset to allow re-entry
                            watched.entry_attempt_count += 1
                            logger.info(
                                f"[Warrior Entry] {symbol}: PULLBACK pattern "
                                f"(HOD=${watched.recent_high:.2f}, dip {pullback_pct:.1f}%, "
                                f"target {entry_reason})"
                            )
                            await enter_position(
                                engine,
                                watched,
                                current_price,
                                EntryTriggerType.PULLBACK
                            )
                continue  # Already entered this breakout
            
            # ORB trigger at 9:30
            if engine.config.orb_enabled and not watched.orb_established:
                await check_orb_setup(engine, watched, current_price)
            
            # PMH breakout with CANDLE CONFIRMATION (Ross: "Candle Over Candle")
            # Pattern: First candle exceeds PMH = "control candle"
            #          Entry triggers when NEXT candle breaks control candle's high
            # This naturally filters rejection wicks (LCFY 08:01 had high $7.26 but close $6.20)
            if engine.config.pmh_enabled and not watched.entry_triggered:
                trigger_price = watched.pmh + engine.config.pmh_buffer_cents / 100
                
                # Get current candle info for confirmation logic
                current_candle_high = None
                current_candle_time = None
                if engine._get_intraday_bars:
                    try:
                        candles = await engine._get_intraday_bars(symbol, "1min", limit=2)
                        if candles and len(candles) >= 1:
                            current_candle = candles[-1]
                            current_candle_high = Decimal(str(current_candle.high))
                            # Get time from candle if available
                            if hasattr(current_candle, 'timestamp') and current_candle.timestamp:
                                current_candle_time = current_candle.timestamp.strftime("%H:%M") if hasattr(current_candle.timestamp, 'strftime') else str(current_candle.timestamp)
                            else:
                                # Use sim clock time as fallback
                                try:
                                    from nexus2.adapters.simulation import get_simulation_clock
                                    sim_clock = get_simulation_clock()
                                    current_candle_time = sim_clock.get_time_string()
                                except Exception:
                                    current_candle_time = "unknown"
                    except Exception as e:
                        logger.debug(f"[Warrior Entry] {symbol}: Candle fetch for confirmation failed: {e}")
                
                # ACTIVE MARKET GATE: Only consider PMH break if market is actually active
                # This prevents entering on dead premarket with sparse, low-volume bars
                # (GRI 04:54 entry was on 250 vol with hour gaps between bars)
                if current_price >= trigger_price:
                    # Check if market is active enough to trade
                    market_active = True
                    inactive_reason = ""
                    
                    if engine._get_intraday_bars:
                        try:
                            activity_candles = await engine._get_intraday_bars(symbol, "1min", limit=10)
                            logger.info(
                                f"[Warrior Entry] {symbol}: Active market check - got {len(activity_candles) if activity_candles else 0} candles"
                            )
                            if activity_candles:
                                market_active, inactive_reason = check_active_market(
                                    activity_candles,
                                    min_bars=5,  # Require at least 5 bars
                                    min_volume_per_bar=1000,  # Require 1000+ avg volume
                                    max_time_gap_minutes=15,  # Max 15 min between bars
                                )
                                logger.info(
                                    f"[Warrior Entry] {symbol}: Active market result: active={market_active}, reason='{inactive_reason}'"
                                )
                        except Exception as e:
                            logger.warning(f"[Warrior Entry] {symbol}: Active market check FAILED: {e}")
                    
                    if not market_active:
                        logger.info(
                            f"[Warrior Entry] {symbol}: PMH break BLOCKED - market not active "
                            f"({inactive_reason}). Waiting for more activity..."
                        )
                    else:
                        # STAGE 1: Set control candle if not already set
                        if watched.control_candle_high is None:
                            watched.control_candle_high = current_candle_high if current_candle_high else current_price
                            watched.control_candle_time = current_candle_time if current_candle_time else "N/A"
                            logger.info(
                                f"[Warrior Entry] {symbol}: PMH break detected at {watched.control_candle_time}, "
                                f"control candle high=${watched.control_candle_high:.2f} - waiting for confirmation"
                            )
                        # STAGE 2: Check if CURRENT candle is DIFFERENT from control candle and breaks control high
                        elif current_candle_time and current_candle_time != watched.control_candle_time:
                            if current_price > watched.control_candle_high:
                                logger.info(
                                    f"[Warrior Entry] {symbol}: CANDLE CONFIRMATION - "
                                    f"${current_price:.2f} breaks control high ${watched.control_candle_high:.2f} "
                                    f"(control set at {watched.control_candle_time})"
                                )
                                await enter_position(
                                    engine, 
                                    watched, 
                                    current_price, 
                                    EntryTriggerType.PMH_BREAK
                                )
                            else:
                                logger.debug(
                                    f"[Warrior Entry] {symbol}: Waiting for break of control high "
                                    f"${watched.control_candle_high:.2f} (current=${current_price:.2f})"
                                )
            
            # ORB breakout (after ORB established)
            if watched.orb_established and watched.orb_high:
                if current_price > watched.orb_high:
                    logger.info(f"[Warrior Entry] {symbol}: ORB BREAKOUT at ${current_price}")
                    await enter_position(
                        engine,
                        watched,
                        current_price,
                        EntryTriggerType.ORB
                    )
            
            # BULL FLAG - Ross Cameron: "First green after pullback"
            # Pattern: 2+ consecutive red candles (pullback), then first green candle
            # breaks above the previous candle's high
            if engine.config.bull_flag_enabled and not watched.entry_triggered:
                if engine._get_intraday_bars:
                    try:
                        candles = await engine._get_intraday_bars(symbol, "1min", limit=10)
                        if candles and len(candles) >= 3:
                            # Analyze recent candles for bull flag pattern
                            # candles[-1] = current, candles[-2] = previous, etc.
                            current_candle = candles[-1]
                            prev_candle = candles[-2]
                            
                            # Determine candle colors (green = close > open)
                            current_is_green = current_candle.close > current_candle.open
                            prev_is_green = prev_candle.close > prev_candle.open
                            
                            # Track consecutive red candles
                            if not prev_is_green:
                                # Count how many red candles in a row before this
                                red_count = 0
                                for i in range(len(candles) - 2, -1, -1):  # Walk back from prev
                                    c = candles[i]
                                    if c.close < c.open:  # Red candle
                                        red_count += 1
                                    else:
                                        break  # Hit a green, stop counting
                                watched.consecutive_red_candles = red_count
                            
                            # Bull flag trigger: First green after 2+ red candles,
                            # AND current price > previous candle high (breakout)
                            if (current_is_green and 
                                watched.consecutive_red_candles >= 2 and
                                current_price > Decimal(str(prev_candle.high))):
                                
                                logger.info(
                                    f"[Warrior Entry] {symbol}: BULL FLAG at ${current_price:.2f} "
                                    f"(first green after {watched.consecutive_red_candles} red candles, "
                                    f"break of prev high ${prev_candle.high:.2f})"
                                )
                                watched.consecutive_red_candles = 0  # Reset for next detection
                                await enter_position(
                                    engine,
                                    watched,
                                    current_price,
                                    EntryTriggerType.BULL_FLAG
                                )
                            
                            # Update tracking for next iteration
                            watched.last_candle_was_green = current_is_green
                    except Exception as e:
                        logger.debug(f"[Warrior Entry] {symbol}: Bull flag check failed: {e}")
            
            # VWAP BREAK - Ross Cameron (Jan 20 2026): "I took this trade for the break through VWAP"
            # Pattern: Stock pulls back below VWAP, consolidates, then breaks back above
            # This is distinct from VWAP_RECLAIM (which is reclaiming after losing VWAP)
            if engine.config.vwap_break_enabled and not watched.entry_triggered:
                # Get current VWAP
                vwap = None
                if engine._get_intraday_bars:
                    try:
                        candles = await engine._get_intraday_bars(symbol, "1min", limit=30)
                        if candles and len(candles) >= 5:
                            from nexus2.domain.indicators import get_technical_service
                            tech = get_technical_service()
                            candle_dicts = [
                                {"high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
                                for c in candles
                            ]
                            snapshot = tech.get_snapshot(symbol, candle_dicts, float(current_price))
                            if snapshot.vwap:
                                vwap = Decimal(str(snapshot.vwap))
                    except Exception as e:
                        logger.debug(f"[Warrior Entry] {symbol}: VWAP fetch failed: {e}")
                
                if vwap:
                    # Track when price is below VWAP (setup for break)
                    if current_price < vwap:
                        if not watched.last_below_vwap:
                            logger.debug(f"[Warrior Entry] {symbol}: Below VWAP ${vwap:.2f} - ready for break")
                        watched.last_below_vwap = True
                    
                    # VWAP BREAK: Price crosses above VWAP after being below
                    elif current_price >= vwap and watched.last_below_vwap:
                        # Require price to be at least 5c above VWAP for confirmation
                        buffer_above_vwap = Decimal("0.05")
                        if current_price >= vwap + buffer_above_vwap:
                            # FALLING KNIFE FILTER: Block on fading/weak stocks
                            if candles and len(candles) >= 20:
                                is_falling, reason = check_falling_knife(current_price, snapshot)
                                if is_falling:
                                    logger.info(
                                        f"[Warrior Entry] {symbol}: VWAP BREAK blocked (FALLING KNIFE) - {reason}"
                                    )
                                    watched.last_below_vwap = False
                                    continue
                            
                            # VOLUME CONFIRMATION: Break bar must have volume expansion
                            vol_confirmed, curr_vol, avg_vol = check_volume_confirmed(candles)
                            if not vol_confirmed:
                                logger.info(
                                    f"[Warrior Entry] {symbol}: VWAP BREAK blocked (LOW VOLUME) - "
                                    f"bar vol {curr_vol:,} < avg {avg_vol:,.0f}"
                                )
                                # Don't reset last_below_vwap - wait for volume on next bar
                                continue
                            
                            # HIGH VOLUME RED CANDLE FILTER: Block on distribution bars
                            # Ross Cameron: "high volume red candle is a red flag literally"
                            is_red_flag, red_vol, red_avg = check_high_volume_red_candle(candles)
                            if is_red_flag:
                                logger.info(
                                    f"[Warrior Entry] {symbol}: VWAP BREAK blocked (HIGH VOL RED) - "
                                    f"red bar vol {red_vol:,} >= 1.5x avg {red_avg:,.0f}"
                                )
                                watched.last_below_vwap = False
                                continue
                            
                            logger.info(
                                f"[Warrior Entry] {symbol}: VWAP BREAK at ${current_price:.2f} "
                                f"(VWAP=${vwap:.2f}, vol={curr_vol:,})"
                            )
                            watched.last_below_vwap = False  # Reset for next break
                            await enter_position(
                                engine,
                                watched,
                                current_price,
                                EntryTriggerType.VWAP_BREAK
                            )
            
            # INVERTED HEAD & SHOULDERS - Ross Cameron (Jan 28 2026): SXTP for +$1,900
            # Pattern: Left Shoulder → Head (lowest) → Right Shoulder → Neckline break
            # Entry: When price breaks above neckline with volume confirmation
            if engine.config.inverted_hs_enabled and not watched.entry_triggered:
                if engine._get_intraday_bars:
                    try:
                        candles = await engine._get_intraday_bars(symbol, "1min", limit=30)
                        if candles and len(candles) >= 15:
                            from nexus2.domain.indicators.pattern_service import get_pattern_service
                            pattern_svc = get_pattern_service()
                            
                            candle_dicts = [
                                {"high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
                                for c in candles
                            ]
                            
                            # Detect pattern
                            pattern = pattern_svc.detect_inverted_hs(candle_dicts, lookback=20)
                            
                            if pattern:
                                watched.inverted_hs_pattern = pattern
                                from datetime import datetime, timezone
                                watched.inverted_hs_detected_at = datetime.now(timezone.utc)
                                
                                # Check for neckline breakout with volume
                                if pattern.is_breakout(current_price, buffer_cents=5):
                                    # Volume confirmation: current bar should have higher volume
                                    current_bar_vol = candles[-1].volume if candles else 0
                                    prior_bar_vol = candles[-2].volume if len(candles) >= 2 else 0
                                    avg_vol = sum(c.volume for c in candles[-10:]) / 10 if len(candles) >= 10 else prior_bar_vol
                                    
                                    # Require volume above average or higher than prior bar
                                    vol_confirmed = current_bar_vol >= avg_vol or current_bar_vol > prior_bar_vol
                                    
                                    if vol_confirmed:
                                        logger.info(
                                            f"[Warrior Entry] {symbol}: INVERTED H&S BREAKOUT at ${current_price:.2f} "
                                            f"(neckline=${pattern.neckline:.2f}, head=${pattern.head_low:.2f}, "
                                            f"confidence={pattern.confidence:.2f}, vol={current_bar_vol:,})"
                                        )
                                        await enter_position(
                                            engine,
                                            watched,
                                            current_price,
                                            EntryTriggerType.INVERTED_HS
                                        )
                                    else:
                                        logger.debug(
                                            f"[Warrior Entry] {symbol}: Inverted H&S neckline break "
                                            f"but volume not confirmed ({current_bar_vol:,} < avg {avg_vol:,.0f})"
                                        )
                    except Exception as e:
                        logger.debug(f"[Warrior Entry] {symbol}: Inverted H&S check failed: {e}")
            
            # ABCD PATTERN - Ross Cameron (Jan 29 2026): DCX for +$6,268
            # Cold-day strategy: A (low) → B (rally high) → C (higher low) → D (break B)
            # Entry: When price breaks above B high (D point) with volume
            # Stop: Below C low
            # Target: Measured move (AB distance from C)
            if engine.config.abcd_enabled and not watched.entry_triggered:
                if engine._get_intraday_bars:
                    try:
                        candles = await engine._get_intraday_bars(symbol, "1min", limit=40)
                        if candles and len(candles) >= 15:
                            from nexus2.domain.indicators.pattern_service import get_pattern_service
                            pattern_svc = get_pattern_service()
                            
                            candle_dicts = [
                                {"high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
                                for c in candles
                            ]
                            
                            # Detect ABCD pattern
                            pattern = pattern_svc.detect_abcd(candle_dicts, lookback=30)
                            
                            if pattern:
                                watched.abcd_pattern = pattern
                                from datetime import datetime, timezone
                                watched.abcd_detected_at = datetime.now(timezone.utc)
                                
                                # Check for D breakout (price breaks above B high)
                                if pattern.is_breakout(current_price, buffer_cents=5):
                                    # Volume confirmation: current bar should have higher volume
                                    current_bar_vol = candles[-1].volume if candles else 0
                                    avg_vol = sum(c.volume for c in candles[-10:]) / 10 if len(candles) >= 10 else 0
                                    
                                    # Require volume above average
                                    vol_confirmed = current_bar_vol >= avg_vol * 0.8  # 80% of avg is acceptable
                                    
                                    if vol_confirmed:
                                        logger.info(
                                            f"[Warrior Entry] {symbol}: ABCD BREAKOUT at ${current_price:.2f} "
                                            f"(A=${pattern.a_low:.2f}, B=${pattern.b_high:.2f}, C=${pattern.c_low:.2f}, "
                                            f"stop=${pattern.stop_price:.2f}, target=${pattern.target_price:.2f}, "
                                            f"R:R={pattern.risk_reward:.1f}, conf={pattern.confidence:.2f})"
                                        )
                                        await enter_position(
                                            engine,
                                            watched,
                                            current_price,
                                            EntryTriggerType.ABCD
                                        )
                                    else:
                                        logger.debug(
                                            f"[Warrior Entry] {symbol}: ABCD breakout "
                                            f"but volume not confirmed ({current_bar_vol:,} < avg {avg_vol:,.0f})"
                                        )
                    except Exception as e:
                        logger.debug(f"[Warrior Entry] {symbol}: ABCD check failed: {e}")
            
            # CUP & HANDLE VWAP BREAK - Ross Cameron (Jan 30 2026): LRHC for +$3,686
            # Consolidation pattern that breaks through resistance (often VWAP):
            # Left rim → Cup low → Right rim → Handle pullback → Breakout
            # Entry: When price breaks above handle high through VWAP
            if engine.config.cup_handle_enabled and not watched.entry_triggered:
                if engine._get_intraday_bars:
                    try:
                        candles = await engine._get_intraday_bars(symbol, "1min", limit=50)
                        if candles and len(candles) >= 20:
                            from nexus2.domain.indicators.pattern_service import get_pattern_service, CupHandlePattern
                            from nexus2.domain.indicators import get_technical_service
                            pattern_svc = get_pattern_service()
                            
                            candle_dicts = [
                                {"high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
                                for c in candles
                            ]
                            
                            # Get VWAP for context (Cup & Handle VWAP Break)
                            vwap = None
                            try:
                                tech = get_technical_service()
                                snapshot = tech.get_snapshot(symbol, candle_dicts, float(current_price))
                                if snapshot.vwap:
                                    vwap = Decimal(str(snapshot.vwap))
                            except:
                                pass
                            
                            # Detect Cup & Handle pattern
                            pattern = pattern_svc.detect_cup_handle(candle_dicts, vwap=vwap, lookback=40)
                            
                            if pattern:
                                watched.cup_handle_pattern = pattern
                                from datetime import datetime, timezone
                                watched.cup_handle_detected_at = datetime.now(timezone.utc)
                                
                                # Check for breakout (price breaks above handle high)
                                if pattern.is_breakout(current_price, buffer_cents=5):
                                    # Volume confirmation
                                    current_bar_vol = candles[-1].volume if candles else 0
                                    avg_vol = sum(c.volume for c in candles[-10:]) / 10 if len(candles) >= 10 else 0
                                    vol_confirmed = current_bar_vol >= avg_vol * 0.8
                                    
                                    if vol_confirmed:
                                        vwap_info = f", VWAP=${vwap:.2f}" if vwap else ""
                                        logger.info(
                                            f"[Warrior Entry] {symbol}: CUP & HANDLE BREAKOUT at ${current_price:.2f} "
                                            f"(cup low=${pattern.cup_low:.2f}, breakout=${pattern.breakout_level:.2f}{vwap_info}, "
                                            f"stop=${pattern.stop_price:.2f}, target=${pattern.target_price:.2f}, "
                                            f"conf={pattern.confidence:.2f})"
                                        )
                                        await enter_position(
                                            engine,
                                            watched,
                                            current_price,
                                            EntryTriggerType.CUP_HANDLE
                                        )
                                    else:
                                        logger.debug(
                                            f"[Warrior Entry] {symbol}: Cup & Handle breakout "
                                            f"but volume not confirmed ({current_bar_vol:,} < avg {avg_vol:,.0f})"
                                        )
                    except Exception as e:
                        logger.debug(f"[Warrior Entry] {symbol}: Cup & Handle check failed: {e}")
                    
        except Exception as e:
            logger.error(f"[Warrior Watch] Error checking {symbol}: {e}")


async def check_orb_setup(
    engine: "WarriorEngine",
    watched: WatchedCandidate,
    current_price: Decimal,
) -> None:
    """
    Check for Opening Range Breakout setup.
    
    Establishes the ORB high/low from the first 1-minute candle after 9:30 AM ET.
    
    Args:
        engine: The WarriorEngine instance
        watched: The watched candidate to check
        current_price: Current price of the symbol
    """
    from datetime import datetime, timezone
    
    # Get first 1-minute candle
    et_now = engine._get_eastern_time()
    
    # Only establish ORB after market opens (9:30 AM)
    if et_now.time() > dt_time(9, 30):
        if engine._get_intraday_bars:
            # Fetch multiple bars to find the 9:30 opening bar
            # The 9:30 bar should be in the history
            bars = await engine._get_intraday_bars(
                watched.candidate.symbol, 
                timeframe="1min",
                limit=30  # Fetch enough bars to find the 9:30 bar
            )
            if bars and len(bars) > 0:
                # Find the 9:30 bar specifically
                orb_bar = None
                for bar in bars:
                    bar_time = getattr(bar, 'timestamp', None) or getattr(bar, 't', None)
                    if bar_time:
                        # Handle both datetime and string formats
                        if isinstance(bar_time, str):
                            bar_time = datetime.fromisoformat(bar_time.replace('Z', '+00:00'))
                        # Convert to ET for comparison
                        from zoneinfo import ZoneInfo
                        if bar_time.tzinfo is None:
                            bar_time = bar_time.replace(tzinfo=timezone.utc)
                        bar_time_et = bar_time.astimezone(ZoneInfo("America/New_York"))
                        
                        # The 9:30 bar represents the 9:30:00 - 9:30:59 range
                        if bar_time_et.hour == 9 and bar_time_et.minute == 30:
                            orb_bar = bar
                            break
                
                if orb_bar:
                    watched.orb_high = Decimal(str(orb_bar.high))
                    watched.orb_low = Decimal(str(orb_bar.low))
                    watched.orb_established = True
                    logger.info(
                        f"[Warrior ORB] {watched.candidate.symbol}: "
                        f"High=${watched.orb_high}, Low=${watched.orb_low}"
                    )
                else:
                    # 9:30 bar not found yet - may be data delay
                    logger.debug(
                        f"[Warrior ORB] {watched.candidate.symbol}: "
                        f"9:30 bar not found in {len(bars)} bars - waiting for data"
                    )


async def check_micro_pullback_entry(
    engine: "WarriorEngine",
    watched: WatchedCandidate,
    current_price: Decimal,
) -> None:
    """
    MICRO-PULLBACK ENTRY for extended stocks (>100% gap).
    
    Pattern (Ross Cameron methodology):
    1. Stock making higher highs (uptrend), above VWAP
    2. Small dip occurs on LIGHT volume (healthy pullback)
    3. Entry when price breaks prior swing high on HIGHER volume
    4. MACD must be positive ("green light" system)
    
    Example: VERO at $5.92 - break of swing high, not PMH
    """
    from datetime import datetime, timezone
    
    symbol = watched.candidate.symbol
    
    # NOTE: VWAP check removed for micro-pullback entries
    # Ross doesn't explicitly require above-VWAP for extended stock scalps
    # He focuses on: micro-pullback pattern, volume confirmation, MACD positive
    
    # REQUIREMENT 2: Get MACD and volume data
    current_bar_volume = 0
    prior_bar_volume = 0
    is_macd_bullish = False
    macd_val = 0  # Initialize before use
    macd_debug_info = ""
    
    if engine._get_intraday_bars:
        try:
            candles = await engine._get_intraday_bars(symbol, "1min", limit=30)
            if not candles or len(candles) < 20:
                logger.info(f"[Warrior Entry] {symbol}: MICRO_PULLBACK skip - not enough candles ({len(candles) if candles else 0} < 20)")
                return
            if True:  # candles check passed
                from nexus2.domain.indicators import get_technical_service
                tech = get_technical_service()
                candle_dicts = [
                    {"high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
                    for c in candles
                ]
                snapshot = tech.get_snapshot(symbol, candle_dicts, float(current_price))
                is_macd_bullish = snapshot.is_macd_bullish
                
                # DEBUG: Log MACD details
                first_time = getattr(candles[0], 'timestamp', getattr(candles[0], 't', 'N/A'))
                last_time = getattr(candles[-1], 'timestamp', getattr(candles[-1], 't', 'N/A'))
                macd_val = snapshot.macd_line if snapshot.macd_line else 0
                signal_val = snapshot.macd_signal if snapshot.macd_signal else 0
                macd_debug_info = (
                    f"candles={len(candles)}, range={first_time}->{last_time}, "
                    f"MACD={macd_val:.4f}, signal={signal_val:.4f}, bullish={is_macd_bullish}"
                )
                
                # Get volume for current and prior bar
                current_bar_volume = candles[-1].volume if candles else 0
                prior_bar_volume = candles[-2].volume if len(candles) >= 2 else 0
        except Exception as e:
            logger.info(f"[Warrior Entry] {symbol}: MICRO_PULLBACK skip - MACD/volume error: {e}")
            return
    
    # MACD check (Ross relaxes for scalps - allow near-zero)
    # Ross enters extended stock scalps when MACD is near zero, not strictly positive
    macd_tolerance = engine.config.micro_pullback_macd_tolerance
    macd_ok = is_macd_bullish or (macd_val >= macd_tolerance)
    
    if engine.config.require_macd_positive and not macd_ok:
        logger.info(
            f"[Warrior Entry] {symbol}: MICRO_PULLBACK skip - MACD too negative "
            f"({macd_val:.4f} < {macd_tolerance}, {macd_debug_info})"
        )
        return
    
    # TRACK SWING HIGHS
    # DEBUG: Log current state
    logger.info(
        f"[Warrior Entry] {symbol}: MICRO state - swing_high=${watched.swing_high}, "
        f"pullback_low=${watched.pullback_low}, ready={watched.micro_pullback_ready}, price=${current_price}"
    )
    
    # ENTRY TRIGGER: Check FIRST - if ready and price breaks above swing high, ENTER
    # This must happen BEFORE the "new swing high" check below
    if watched.micro_pullback_ready and watched.swing_high and current_price > watched.swing_high:
        # VOLUME CONFIRMATION: Break bar must have higher volume than prior bar
        if current_bar_volume <= prior_bar_volume:
            logger.info(
                f"[Warrior Entry] {symbol}: MICRO_PULLBACK skip - volume not confirming "
                f"({current_bar_volume:,} <= {prior_bar_volume:,})"
            )
            # Reset for next setup
            watched.swing_high = current_price
            watched.micro_pullback_ready = False
            return
        
        logger.info(
            f"[Warrior Entry] {symbol}: MICRO_PULLBACK ENTRY "
            f"(${current_price:.2f} breaks ${watched.swing_high:.2f}, "
            f"vol {current_bar_volume:,} > {prior_bar_volume:,})"
        )
        await enter_position(
            engine, watched, current_price, EntryTriggerType.MICRO_PULLBACK
        )
        # Reset state after entry
        watched.swing_high = current_price
        watched.micro_pullback_ready = False
        return
    
    # TRACK SWING HIGHS (only if not ready or first high)
    if watched.swing_high is None or current_price > watched.swing_high:
        watched.swing_high = current_price
        watched.swing_high_time = datetime.now(timezone.utc).strftime("%H:%M")
        watched.pullback_low = None
        watched.micro_pullback_ready = False
        logger.info(f"[Warrior Entry] {symbol}: New swing high ${watched.swing_high:.2f}")
        return
    
    # DETECT PULLBACK (price dips from swing high)
    if current_price < watched.swing_high:
        pullback_pct = float((watched.swing_high - current_price) / watched.swing_high * 100)
        
        if watched.pullback_low is None or current_price < watched.pullback_low:
            watched.pullback_low = current_price
        
        min_dip = engine.config.micro_pullback_min_dip
        max_dip = engine.config.micro_pullback_max_dip
        
        # VALID MICRO-PULLBACK: within configured dip range
        if min_dip <= pullback_pct <= max_dip:
            watched.micro_pullback_ready = True
            logger.info(
                f"[Warrior Entry] {symbol}: MICRO_PULLBACK detected "
                f"(swing high ${watched.swing_high:.2f}, dip {pullback_pct:.1f}%)"
            )
        elif pullback_pct > 10.0:
            # Too deep - this is a reversal, not a micro-pullback
            watched.swing_high = None
            watched.micro_pullback_ready = False
            logger.info(f"[Warrior Entry] {symbol}: Pullback too deep ({pullback_pct:.1f}%) - reset")
        return
    
    # If we reach here, price == swing_high (rare edge case, do nothing)


# =============================================================================
# SCALING INTO EXISTING POSITION (MICRO-PULLBACK RE-ENTRIES)
# =============================================================================


async def _scale_into_existing_position(
    engine: "WarriorEngine",
    watched: WatchedCandidate,
    entry_price: Decimal,
    trigger_type: EntryTriggerType,
) -> None:
    """
    Scale into an existing position (Ross Cameron averaging-in methodology).
    
    Called when micro-pullback triggers on a symbol we already hold.
    Uses the monitor's scaling infrastructure for proper DB tracking.
    
    Args:
        engine: The WarriorEngine instance
        watched: The watched candidate triggering the scale
        entry_price: Price to add at
        trigger_type: Entry trigger type (for logging)
    """
    symbol = watched.candidate.symbol
    
    # Get the existing position from monitor
    existing_position = None
    for pos_id, pos in engine.monitor._positions.items():
        if pos.symbol == symbol:
            existing_position = pos
            break
    
    if not existing_position:
        logger.warning(
            f"[Warrior Entry] {symbol}: Scale requested but no position in monitor - "
            f"trying DB lookup"
        )
        # Try DB lookup as fallback
        from nexus2.db.warrior_db import get_warrior_trade_by_symbol
        trade = get_warrior_trade_by_symbol(symbol)
        if not trade:
            logger.error(f"[Warrior Entry] {symbol}: No position found in DB either, cannot scale")
            return
        # Position exists in DB but not in monitor's memory - skip for now
        logger.warning(f"[Warrior Entry] {symbol}: Position in DB but not monitor, skipping scale")
        return
    
    # Calculate add shares (same sizing as initial entry)
    add_shares = engine.config.position_size
    
    # Create scale signal matching what warrior_monitor_scale expects
    scale_signal = {
        "position_id": existing_position.position_id,
        "symbol": symbol,
        "add_shares": add_shares,
        "price": float(entry_price),
        "support": float(existing_position.current_stop or existing_position.mental_stop or 0),
        "scale_count": existing_position.scale_count + 1,
    }
    
    logger.info(
        f"[Warrior Entry] {symbol}: MICRO_PULLBACK SCALE - adding {add_shares} shares "
        f"@ ${entry_price:.2f} to existing position "
        f"(entry=${existing_position.entry_price:.2f}, shares={existing_position.shares})"
    )
    
    # Use monitor's execute_scale_in for proper DB tracking
    from nexus2.domain.automation.warrior_monitor_scale import execute_scale_in
    success = await execute_scale_in(engine.monitor, existing_position, scale_signal)
    
    if success:
        # Calculate new average entry price
        old_shares = existing_position.shares - add_shares  # shares before add
        old_cost = float(existing_position.entry_price) * old_shares
        new_cost = float(entry_price) * add_shares
        new_avg = (old_cost + new_cost) / existing_position.shares
        
        logger.info(
            f"[Warrior Entry] {symbol}: Scale complete - "
            f"now {existing_position.shares} shares, avg=${new_avg:.2f}"
        )
    else:
        logger.warning(f"[Warrior Entry] {symbol}: Scale-in failed")


# =============================================================================
# ENTRY EXECUTION
# =============================================================================


async def enter_position(
    engine: "WarriorEngine",
    watched: WatchedCandidate,
    entry_price: Decimal,
    trigger_type: EntryTriggerType,
) -> None:
    """
    Execute entry for a candidate.
    
    Performs all entry guards, calculates position size, submits order,
    and integrates with the monitor.
    
    Args:
        engine: The WarriorEngine instance
        watched: The watched candidate to enter
        entry_price: Price to enter at
        trigger_type: Type of entry trigger (ORB, PMH_BREAK, etc.)
    """
    symbol = watched.candidate.symbol
    
    # =========================================================================
    # ENTRY GUARDS
    # =========================================================================
    
    # TOP X PICKS - Ross Cameron (Jan 20 2026): "TWWG was the ONLY trade I took today"
    # Only enter the top X highest-scoring candidates, skip the rest
    # Uses dynamic_score which includes VWAP/EMA trend bonus (trending > fading)
    # top_x_picks=0 means no limit, top_x_picks=1 is Ross-style single pick
    if engine.config.top_x_picks > 0:
        # Get all watched candidates sorted by dynamic score (highest first)
        all_watched = sorted(
            engine._watchlist.values(), 
            key=lambda w: w.dynamic_score, 
            reverse=True
        )
        if all_watched:
            # Check if this candidate is in the top X
            top_x_symbols = {w.candidate.symbol for w in all_watched[:engine.config.top_x_picks]}
            if watched.candidate.symbol not in top_x_symbols:
                # Not in top X - mark as triggered to prevent log spam
                top_pick = all_watched[0]
                our_dynamic = watched.dynamic_score
                our_static = getattr(watched.candidate, 'quality_score', 0) or 0
                top_dynamic = top_pick.dynamic_score
                top_static = getattr(top_pick.candidate, 'quality_score', 0) or 0
                our_rank = next((i+1 for i, w in enumerate(all_watched) if w.candidate.symbol == symbol), len(all_watched))
                logger.info(
                    f"[Warrior Entry] {symbol}: TOP_{engine.config.top_x_picks}_ONLY - blocked (rank={our_rank}, "
                    f"dynamic={our_dynamic}, static={our_static}) "
                    f"top pick is {top_pick.candidate.symbol} (dynamic={top_dynamic}, static={top_static})"
                )
                watched.entry_triggered = True
                return
    
    # MIN SCORE CHECK - Require minimum quality score for entry
    candidate_score = getattr(watched.candidate, 'quality_score', 0) or 0
    if candidate_score < engine.config.min_entry_score:
        logger.info(
            f"[Warrior Entry] {symbol}: Score {candidate_score} < min {engine.config.min_entry_score}, skipping"
        )
        watched.entry_triggered = True  # Mark to prevent log spam
        return
    
    # Check blacklist (static config + dynamic from broker rejections)
    if symbol in engine.config.static_blacklist or symbol in engine._blacklist:
        logger.info(f"[Warrior Entry] {symbol}: Blacklisted, skipping")
        watched.entry_triggered = True  # Mark to prevent retries
        return
    
    # Per-symbol fail limit: block entry if symbol has hit max failures today
    symbol_fails = engine._symbol_fails.get(symbol, 0)
    if symbol_fails >= engine._max_fails_per_symbol:
        logger.info(
            f"[Warrior Entry] {symbol}: Max fails hit - {symbol_fails} stops today, "
            f"skipping (max={engine._max_fails_per_symbol})"
        )
        watched.entry_triggered = True  # Mark to prevent retries
        return
    
    # ROSS MACD GATE: Block ALL entries when MACD is negative
    # Per Ross Cameron: "Red light, green light - MACD negative = don't trade"
    # Applies to ALL entries (first and re-entries alike)
    if engine._get_intraday_bars:
        try:
            candles = await engine._get_intraday_bars(symbol, "1min", limit=30)
            if candles and len(candles) >= 10:
                from nexus2.domain.indicators import get_technical_service
                tech = get_technical_service()
                candle_dicts = [
                    {"high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
                    for c in candles
                ]
                snapshot = tech.get_snapshot(symbol, candle_dicts, entry_price)
                
                if not snapshot.is_macd_bullish:
                    logger.info(
                        f"[Warrior Entry] {symbol}: MACD GATE - blocking entry "
                        f"(histogram={snapshot.macd_histogram:.4f if snapshot.macd_histogram else 'N/A'}, "
                        f"crossover={snapshot.macd_crossover}) - Ross rule: no entry when MACD negative"
                    )
                    watched.entry_triggered = True  # Block this attempt
                    return
                else:
                    logger.info(
                        f"[Warrior Entry] {symbol}: MACD OK for entry "
                        f"(histogram={snapshot.macd_histogram:.4f if snapshot.macd_histogram else 'N/A'})"
                    )
        except Exception as e:
            logger.debug(f"[Warrior Entry] {symbol}: MACD check failed: {e} - proceeding without gate")
    
    # Check if we already hold this symbol
    # - For regular entries: Block re-entry (prevents double-buying)
    # - For MICRO_PULLBACK: Scale into existing position (Ross averaging-in methodology)
    
    # FIRST: Check MONITOR positions for max_scale enforcement
    # This prevents submitting orders that would be rejected by add_position()
    from nexus2.domain.automation.warrior_monitor import get_warrior_monitor
    monitor = get_warrior_monitor()
    for pos in monitor.get_positions():
        if pos.symbol == symbol:
            max_scales = monitor.settings.max_scale_count
            if pos.scale_count >= max_scales:
                logger.warning(
                    f"[Warrior Entry] {symbol}: BLOCKED - already at max scale #{pos.scale_count} "
                    f"(limit={max_scales})"
                )
                watched.entry_triggered = True
                return
            # Allow if under max_scale (will consolidate in add_position)
            break
    
    # SECOND: Check BROKER positions for double-buy prevention
    if engine._get_positions:
        try:
            positions = await engine._get_positions()
            held_symbols = {p.get("symbol") or p.symbol for p in positions if p}
            if symbol in held_symbols:
                # MICRO_PULLBACK: Scale into existing position instead of blocking
                if trigger_type == EntryTriggerType.MICRO_PULLBACK:
                    logger.info(
                        f"[Warrior Entry] {symbol}: Already holding - triggering SCALE-IN "
                        f"(micro-pullback re-entry at ${entry_price:.2f})"
                    )
                    await _scale_into_existing_position(
                        engine, watched, entry_price, trigger_type
                    )
                    watched.entry_triggered = True
                    return
                else:
                    # Regular entry: block (prevents double-buying after restart)
                    logger.info(f"[Warrior Entry] {symbol}: Already holding position, skipping")
                    watched.entry_triggered = True  # Mark as triggered to prevent retries
                    return
        except Exception as e:
            logger.warning(f"[Warrior Entry] {symbol}: Position check failed: {e}")
    
    # Check for pending entry orders (unfilled buy orders) - prevents duplicates
    if symbol in engine._pending_entries:
        logger.info(f"[Warrior Entry] {symbol}: Pending buy order exists, skipping")
        watched.entry_triggered = True  # Mark as triggered to prevent retries
        return
    
    # Check re-entry cooldown: block entry if symbol was recently exited
    # This prevents immediately buying back after exit (e.g., after spread exit or stop)
    # SKIP in sim_mode: cooldown uses wall-clock time, not simulation time
    if not engine.monitor.sim_mode and symbol in engine.monitor._recently_exited:
        exit_time = engine.monitor._recently_exited[symbol]
        seconds_ago = (now_utc() - exit_time).total_seconds()
        cooldown = engine.monitor._recovery_cooldown_seconds
        if seconds_ago < cooldown:
            logger.info(
                f"[Warrior Entry] {symbol}: Re-entry cooldown - exited {seconds_ago:.0f}s ago "
                f"(waiting {cooldown}s), skipping"
            )
            watched.entry_triggered = True  # Mark as triggered to prevent retries
            return
    
    # Entry Spread Filter: reject stocks with wide bid-ask spreads
    # Wide spreads cause unpredictable fills and difficult exits (e.g., SOGP 46% spread)
    # Also capture current ask for limit price calculation
    current_ask = None  # Will be set if we get valid quote data
    if engine._get_quote_with_spread and engine.config.max_entry_spread_percent > 0:
        try:
            spread_data = await engine._get_quote_with_spread(symbol)
            if spread_data:
                bid = spread_data.get("bid", 0)
                ask = spread_data.get("ask", 0)
                
                if bid > 0 and ask > 0:
                    current_ask = Decimal(str(ask))  # Store for limit price
                    spread_percent = ((ask - bid) / bid) * 100
                    
                    if spread_percent > engine.config.max_entry_spread_percent:
                        logger.warning(
                            f"[Warrior Entry] {symbol}: REJECTED - spread {spread_percent:.1f}% > "
                            f"{engine.config.max_entry_spread_percent}% threshold "
                            f"(bid=${bid:.2f}, ask=${ask:.2f})"
                        )
                        watched.entry_triggered = True  # Mark to prevent retries
                        return
                    else:
                        logger.debug(
                            f"[Warrior Entry] {symbol}: Spread OK {spread_percent:.1f}% "
                            f"(max={engine.config.max_entry_spread_percent}%)"
                        )
                elif bid <= 0 or ask <= 0:
                    logger.warning(
                        f"[Warrior Entry] {symbol}: No valid bid/ask data "
                        f"(bid=${bid}, ask=${ask}) - proceeding with caution"
                    )
        except Exception as e:
            logger.warning(f"[Warrior Entry] {symbol}: Spread check failed: {e} - proceeding")
    
    # =========================================================================
    # TECHNICAL VALIDATION
    # =========================================================================
    
    # Technical Validation: Check VWAP/EMA alignment per Ross Cameron
    # Entry should be above VWAP and near 9 EMA support
    if engine._get_intraday_bars:
        try:
            candles = await engine._get_intraday_bars(symbol, "1min", limit=50)
            if candles and len(candles) >= 10:
                from nexus2.domain.indicators import get_technical_service
                tech = get_technical_service()
                
                # Convert candles to dict format for pandas-ta
                candle_dicts = [
                    {"high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
                    for c in candles
                ]
                snapshot = tech.get_snapshot(symbol, candle_dicts, entry_price)
                
                # Check: price should be above VWAP (Ross Cameron rule)
                if snapshot.vwap and entry_price < snapshot.vwap:
                    logger.warning(
                        f"[Warrior Entry] {symbol}: REJECTED - below VWAP "
                        f"(${entry_price:.2f} < VWAP ${snapshot.vwap:.2f})"
                    )
                    watched.entry_triggered = True
                    return
                
                # Check: price should be above 9 EMA (within 1% tolerance)
                if snapshot.ema_9 and entry_price < snapshot.ema_9 * Decimal("0.99"):
                    logger.warning(
                        f"[Warrior Entry] {symbol}: REJECTED - below 9 EMA "
                        f"(${entry_price:.2f} < 9EMA ${snapshot.ema_9:.2f})"
                    )
                    watched.entry_triggered = True
                    return
                
                # Log technical confirmation
                logger.info(
                    f"[Warrior Entry] {symbol}: Technical OK - "
                    f"VWAP=${snapshot.vwap:.2f if snapshot.vwap else 'N/A'}, "
                    f"9EMA=${snapshot.ema_9:.2f if snapshot.ema_9 else 'N/A'}, "
                    f"MACD={snapshot.macd_crossover}"
                )
        except Exception as e:
            logger.debug(f"[Warrior Entry] {symbol}: Technical check failed: {e} - proceeding")
    
    # Check if we can open new position (max positions, daily loss)
    if not await engine._can_open_position():
        logger.info(f"[Warrior Entry] {symbol}: Cannot open (max positions or daily loss)")
        return
    
    # =========================================================================
    # POSITION SIZING
    # =========================================================================
    
    # Mark as triggered
    watched.entry_triggered = True
    engine.stats.entries_triggered += 1
    
    # Calculate position size
    # Use entry candle low (Ross Cameron's actual method) per ROSS_RULES_EXTRACTION.md
    # "Max loss per trade = Low of entry candle"
    # Falls back to 15 cents if candle data unavailable
    mental_stop = None
    stop_method = "fallback_15c"
    calculated_candle_low = None  # Track for passing to add_position
    
    if engine._get_intraday_bars:
        try:
            candles = await engine._get_intraday_bars(symbol, "1min", limit=5)
            if candles and len(candles) >= 1:
                # Ross method: Use low of the current/entry candle with 2¢ buffer
                entry_candle = candles[-1]  # Most recent candle (entry candle)
                calculated_candle_low = Decimal(str(entry_candle.low))
                
                # Add 2¢ buffer below the low
                mental_stop = calculated_candle_low - Decimal("0.02")
                stop_method = "candle_low"
                
                logger.info(
                    f"[Warrior Entry] {symbol}: Stop ${mental_stop:.2f} via {stop_method} "
                    f"(candle low=${calculated_candle_low:.2f} - 2¢)"
                )
        except Exception as e:
            logger.debug(f"[Warrior Entry] {symbol}: Entry candle stop calc failed: {e}")
    
    if mental_stop is None:
        # BLOCK TRADE: Cannot make informed decision without candle data
        # Per audit: "If I didn't have data to make informed decisions, I wouldn't trade"
        logger.warning(
            f"[Warrior Entry] {symbol}: TRADE BLOCKED - Unable to fetch entry candle data for stop calculation. "
            f"This indicates a data problem that needs investigation."
        )
        watched.entry_triggered = False  # Reset so we can retry
        engine.stats.entries_triggered -= 1  # Undo the increment
        return

    
    # Ensure Decimal arithmetic for risk calculation
    entry_decimal = Decimal(str(entry_price)) if not isinstance(entry_price, Decimal) else entry_price
    mental_stop_decimal = Decimal(str(mental_stop)) if not isinstance(mental_stop, Decimal) else mental_stop
    risk_per_share = entry_decimal - mental_stop_decimal
    
    if risk_per_share <= 0:
        logger.warning(f"[Warrior Entry] {symbol}: Invalid risk calculation")
        return
    
    shares = int(engine.config.risk_per_trade / risk_per_share)
    
    # Cap by max capital
    max_shares = int(engine.config.max_capital / entry_decimal)
    shares = min(shares, max_shares)
    
    # Apply testing limits
    if engine.config.max_shares_per_trade is not None:
        shares = min(shares, engine.config.max_shares_per_trade)
    if engine.config.max_value_per_trade is not None:
        max_by_value = int(engine.config.max_value_per_trade / entry_decimal)
        shares = min(shares, max_by_value)
    
    # ICEBREAKER: 50% size for high-score Chinese stocks
    # (Ross Cameron, Jan 20 TWWG: "breaking the ice with smaller positions")
    if getattr(watched.candidate, 'is_icebreaker', False):
        original_shares = shares
        shares = max(1, int(shares * 0.5))  # 50% reduction
        logger.info(
            f"[Warrior Entry] {symbol}: ICEBREAKER 50% size ({original_shares} -> {shares} shares)"
        )
    
    if shares < 1:
        logger.info(f"[Warrior Entry] {symbol}: Position too small")
        return
    
    # =========================================================================
    # ORDER SUBMISSION
    # =========================================================================
    
    # Submit order - Ross uses limit order with offset above ask
    # Use current ask if available, otherwise fall back to percentage offset
    limit_offset = Decimal("0.05")  # 5 cents offset when ask is available
    if current_ask and current_ask > 0:
        # Use current ask price (more accurate for fast movers)
        limit_price = (current_ask + limit_offset).quantize(Decimal("0.01"))
        logger.info(f"[Warrior Entry] {symbol}: Limit based on ask ${current_ask:.2f} + ${limit_offset} = ${limit_price:.2f}")
    else:
        # Fallback: 1.5% above entry price (scales better for runners)
        # This handles pre-market when Alpaca doesn't provide bid/ask
        fallback_multiplier = Decimal("1.015")  # 1.5% above entry
        limit_price = (entry_decimal * fallback_multiplier).quantize(Decimal("0.01"))
        logger.info(f"[Warrior Entry] {symbol}: Limit based on entry ${entry_decimal:.2f} x 1.015 = ${limit_price:.2f} (no bid/ask)")
    
    # Mark pending entry BEFORE submitting order (prevents duplicate entries on restart)
    engine._pending_entries[symbol] = now_utc()
    engine._save_pending_entries()
    logger.info(f"[Warrior Entry] {symbol}: Marked pending entry")
    
    if engine._submit_order:
        try:
            # Calculate exit mode BEFORE order submission (for MockBroker GUI display)
            quality_score = getattr(watched.candidate, 'quality_score', 0) or 0
            gap_percent = float(watched.candidate.gap_percent or 0)
            high_quality_threshold = 10  # TODO: Pull from scanner settings
            extension_threshold = engine.config.extension_threshold  # Use config value (was hardcoded 100)
            
            # EXTENSION-BASED EXIT MODE SELECTION:
            # Per Ross's pattern: extended stocks (e.g., VERO at 375%) get quick scalps
            # "Felt like missed the bulk of it" = don't try for home run on extended moves
            if gap_percent > extension_threshold:
                selected_exit_mode = "base_hit"
                logger.info(
                    f"[Warrior Entry] {symbol}: exit_mode=base_hit "
                    f"(EXTENDED: gap={gap_percent:.0f}% > {extension_threshold}% threshold)"
                )
            elif quality_score >= high_quality_threshold:
                selected_exit_mode = "home_run"
                logger.info(
                    f"[Warrior Entry] {symbol}: exit_mode=home_run "
                    f"(quality_score={quality_score} >= {high_quality_threshold})"
                )
            else:
                selected_exit_mode = "base_hit"
                logger.info(
                    f"[Warrior Entry] {symbol}: exit_mode=base_hit "
                    f"(quality_score={quality_score} < {high_quality_threshold})"
                )
            
            order_result = await engine._submit_order(
                symbol=symbol,
                shares=shares,
                side="buy",
                order_type="limit",  # Limit order, not market
                limit_price=float(limit_price),  # offset above ask
                stop_loss=None,  # Mental stop, not broker stop
                exit_mode=selected_exit_mode,  # Pass to MockBroker for GUI display
                entry_trigger=trigger_type.value,  # Pass trigger type for debugging
            )
            
            # Check for blacklist response from broker
            if isinstance(order_result, dict) and order_result.get("blacklist"):
                engine._blacklist.add(symbol)
                logger.warning(f"[Warrior Entry] {symbol}: Added to blacklist - {order_result.get('error')}")
                watched.entry_triggered = True
                return
            
            if order_result is None:
                logger.warning(f"[Warrior Entry] {symbol}: Order returned None")
                return
            
            engine.stats.orders_submitted += 1
            watched.position_opened = True  # Mark as actually entered (for UI "Entered" status)
            
            # Add to monitor
            support_level = watched.orb_low or watched.candidate.session_low or entry_price * Decimal("0.95")
            
            # Handle both dict and object return types
            if hasattr(order_result, 'client_order_id'):
                order_id = str(order_result.client_order_id)
            elif isinstance(order_result, dict):
                order_id = order_result.get("order_id", symbol)
            else:
                order_id = symbol
            
            # Check if order is filled (not just submitted)
            order_status = None
            filled_qty = 0
            if hasattr(order_result, 'status'):
                # Handle enum status (BrokerOrderStatus.FILLED -> "filled")
                status_val = order_result.status
                order_status = status_val.value if hasattr(status_val, 'value') else str(status_val)
                filled_qty = getattr(order_result, 'filled_qty', 0) or 0
            elif isinstance(order_result, dict):
                order_status = order_result.get("status")
                filled_qty = order_result.get("filled_qty", 0) or 0
            
            # =================================================================
            # INTENT LOGGING: Write to DB BEFORE fill check to preserve trigger_type
            # This fixes the data loss bug where pending orders weren't logged,
            # causing sync to create duplicate records with trigger_type='synced'
            # =================================================================
            # Use calculated candle low if available, otherwise fall back to ORB low
            # This ensures stop matches what was logged in entry
            if calculated_candle_low:
                support_level = calculated_candle_low  # Use calculated low for correct stop
            else:
                support_level_raw = watched.orb_low or watched.candidate.session_low or float(entry_decimal) * 0.95
                support_level = Decimal(str(support_level_raw))
            
            # NOTE: exit_mode already calculated above and passed to _submit_order
            
            try:
                from nexus2.db.warrior_db import log_warrior_entry, set_entry_order_id
                mental_stop_cents = Decimal(str(engine.monitor.settings.mental_stop_cents))
                profit_target_r = Decimal(str(engine.monitor.settings.profit_target_r))
                target = entry_decimal + (mental_stop_cents / 100 * profit_target_r)
                log_warrior_entry(
                    trade_id=order_id,
                    symbol=symbol,
                    entry_price=float(entry_price),  # Intended price (update on fill)
                    quantity=shares,
                    stop_price=float(mental_stop),
                    target_price=float(target),
                    trigger_type=trigger_type.value,  # CRITICAL: Preserve the real trigger
                    support_level=float(support_level),
                    stop_method=stop_method,
                    # Quote tracking for phantom quote detection
                    quote_price=float(entry_price),  # Price from quote at decision time
                    limit_price=float(limit_price),  # Limit sent to broker
                    quote_source="unified",  # TODO: Pass actual source from quote
                    exit_mode=selected_exit_mode,  # Auto-selected based on quality score
                    is_sim=engine.monitor.sim_mode,  # Track SIM vs LIVE
                )
                set_entry_order_id(order_id, order_id)
                logger.info(
                    f"[Warrior Entry] {symbol}: Intent logged to DB "
                    f"(trigger={trigger_type.value}, order_id={order_id[:8]}...)"
                )
            except Exception as e:
                logger.warning(f"[Warrior Entry] {symbol}: DB intent log failed: {e}")
            
            # =================================================================
            # FILL CONFIRMATION: Poll for actual fill price before proceeding
            # Most orders fill quickly but response has status="accepted" not "filled"
            # =================================================================
            actual_fill_price = entry_price  # Default to quote price
            broker_order_id = None
            
            # Get broker order ID for polling
            if hasattr(order_result, 'id'):
                broker_order_id = str(order_result.id)
            elif hasattr(order_result, 'broker_order_id'):
                broker_order_id = order_result.broker_order_id
            elif isinstance(order_result, dict):
                broker_order_id = order_result.get("id") or order_result.get("broker_order_id")
            
            # Poll for fill (up to 2.5 seconds) - most fills happen in <1s
            logger.info(
                f"[Warrior Entry] {symbol}: Poll setup - broker_order_id={broker_order_id}, "
                f"has_get_order_status={engine._get_order_status is not None}"
            )
            if broker_order_id and engine._get_order_status:
                import asyncio
                for attempt in range(5):  # 5 attempts x 500ms = 2.5s
                    await asyncio.sleep(0.5)
                    try:
                        order_detail = await engine._get_order_status(broker_order_id)
                        if order_detail:
                            status = getattr(order_detail, 'status', None)
                            if status:
                                status_str = status.value if hasattr(status, 'value') else str(status)
                                if status_str.lower() in ("filled", "partially_filled"):
                                    fill_price = getattr(order_detail, 'filled_avg_price', None)
                                    if fill_price and float(fill_price) > 0:
                                        actual_fill_price = Decimal(str(fill_price))
                                        filled_qty = getattr(order_detail, 'filled_qty', filled_qty) or filled_qty
                                        order_status = status_str  # Update status for below
                                        logger.info(
                                            f"[Warrior Entry] {symbol}: Filled @ ${actual_fill_price:.2f} "
                                            f"(polled attempt {attempt+1})"
                                        )
                                        break
                    except Exception as poll_err:
                        logger.debug(f"[Warrior Entry] {symbol}: Poll attempt {attempt+1} failed: {poll_err}")
                else:
                    if order_status and order_status.lower() not in ("filled", "partially_filled"):
                        logger.info(
                            f"[Warrior Entry] {symbol}: Order still pending after poll - "
                            f"intent recorded, sync will update fill price"
                        )
            
            # Update DB with actual fill price (even if still quote price)
            if actual_fill_price != entry_price or order_status and order_status.lower() in ("filled", "partially_filled"):
                try:
                    from nexus2.db.warrior_db import update_warrior_fill
                    mental_stop_cents = Decimal(str(engine.monitor.settings.mental_stop_cents))
                    actual_fill_decimal = Decimal(str(actual_fill_price))
                    actual_stop = actual_fill_decimal - mental_stop_cents / 100
                    update_warrior_fill(
                        trade_id=order_id,
                        actual_entry_price=float(actual_fill_price),
                        actual_stop_price=float(actual_stop),
                        actual_quantity=int(filled_qty) if filled_qty else shares,
                    )
                    slippage = (float(actual_fill_price) - float(entry_price)) * 100
                    if abs(slippage) > 0.5:  # Log slippage > 0.5 cents
                        logger.info(
                            f"[Warrior Entry] {symbol}: Fill ${actual_fill_price:.2f} vs quote ${entry_price:.2f} "
                            f"= {slippage:+.1f}¢ slippage"
                        )
                    
                    # Log FILL_CONFIRMED event for Trade Events UI
                    from nexus2.domain.automation.trade_event_service import get_trade_event_service
                    trade_event_service = get_trade_event_service()
                    trade_event_service.log_warrior_fill_confirmed(
                        position_id=order_id,
                        symbol=symbol,
                        quote_price=entry_price,
                        fill_price=actual_fill_decimal,
                        slippage_cents=slippage,
                        shares=int(filled_qty) if filled_qty else shares,
                    )
                except Exception as e:
                    logger.warning(f"[Warrior Entry] {symbol}: DB fill update failed: {e}")
            
            # If order is not filled yet, skip monitor add - DB has intent + any fill update
            if order_status and order_status.lower() not in ("filled", "partially_filled"):
                return
            
            # CRITICAL: Use ACTUAL fill price from Alpaca, not intended entry
            # This prevents immediate stop-outs when market price differs from quote
            # 
            # ISSUE: Alpaca may return status="filled" but filled_avg_price=NULL
            # in the immediate response. We must poll to get the actual fill price.
            actual_fill_price = entry_price  # Default to intended price
            slippage_cents = Decimal("0")  # Track slippage
            
            # Try to get fill price from order result first
            if hasattr(order_result, 'filled_avg_price') and order_result.filled_avg_price:
                actual_fill_price = Decimal(str(order_result.filled_avg_price))
            elif isinstance(order_result, dict) and order_result.get("filled_avg_price"):
                actual_fill_price = Decimal(str(order_result["filled_avg_price"]))
            else:
                # Fill price not in immediate response - poll for it
                # This fixes the phantom quote entry price bug (e.g., DVLT $5.44 -> $0.96)
                logger.info(f"[Warrior Entry] {symbol}: Fill price null in response, polling for actual fill...")
                
                broker_order_id = None
                if hasattr(order_result, 'broker_order_id'):
                    broker_order_id = order_result.broker_order_id
                elif isinstance(order_result, dict):
                    broker_order_id = order_result.get("id") or order_result.get("broker_order_id")
                
                if broker_order_id and engine._get_order_status:
                    import asyncio
                    for attempt in range(5):  # Max 5 attempts, 500ms each = 2.5s max
                        await asyncio.sleep(0.5)  # Wait 500ms before polling
                        try:
                            order_detail = await engine._get_order_status(broker_order_id)
                            if order_detail:
                                fill_price = getattr(order_detail, 'avg_fill_price', None)
                                if fill_price and fill_price > 0:
                                    actual_fill_price = Decimal(str(fill_price))
                                    filled_qty = getattr(order_detail, 'filled_quantity', filled_qty) or filled_qty
                                    logger.info(
                                        f"[Warrior Entry] {symbol}: Got fill price on attempt {attempt+1}: "
                                        f"${actual_fill_price:.4f}"
                                    )
                                    break
                        except Exception as poll_err:
                            logger.debug(f"[Warrior Entry] {symbol}: Poll attempt {attempt+1} failed: {poll_err}")
                    else:
                        logger.warning(
                            f"[Warrior Entry] {symbol}: Could not get fill price after 5 attempts, "
                            f"using quote price ${entry_price:.4f}"
                        )
            
            # Ensure Decimal types for all arithmetic (actual_fill_price may be float from MockBroker)
            actual_fill_decimal = Decimal(str(actual_fill_price)) if not isinstance(actual_fill_price, Decimal) else actual_fill_price
            entry_decimal = Decimal(str(entry_price)) if not isinstance(entry_price, Decimal) else entry_price
            
            # Calculate slippage
            slippage_cents = (actual_fill_decimal - entry_decimal) * 100  # In cents
            if abs(slippage_cents) > Decimal("0.01"):  # Only log if there's meaningful slippage
                slippage_bps = (actual_fill_decimal / entry_decimal - 1) * 10000  # Basis points
                logger.info(
                    f"[Warrior Slippage] {symbol}: Fill ${actual_fill_decimal:.2f} vs "
                    f"intended ${entry_decimal:.2f} = {slippage_cents:+.1f}¢ ({slippage_bps:+.1f}bps)"
                )
            
            # Recalculate stop based on actual fill price
            actual_stop = actual_fill_decimal - Decimal(str(engine.monitor.settings.mental_stop_cents)) / 100
            
            engine.monitor.add_position(
                position_id=order_id,
                symbol=symbol,
                entry_price=actual_fill_decimal,  # Use ACTUAL fill price (Decimal)
                shares=int(filled_qty) if filled_qty else shares,  # Use actual filled qty
                support_level=support_level,
                trigger_type=trigger_type.value,  # PMH_BREAK, ORB
                exit_mode_override=selected_exit_mode,  # Auto-selected based on quality score
            )
            
            # Update DB record with actual fill price (intent was already logged above)
            try:
                from nexus2.db.warrior_db import update_warrior_fill
                update_warrior_fill(
                    trade_id=order_id,
                    actual_entry_price=float(actual_fill_price),
                    actual_stop_price=float(actual_stop),
                    actual_quantity=int(filled_qty) if filled_qty else shares,
                )
                logger.debug(f"[Warrior Entry] {symbol}: Updated DB with fill price ${actual_fill_price:.2f}")
                
                # Log FILL_CONFIRMED event for Trade Events UI
                from nexus2.domain.automation.trade_event_service import get_trade_event_service
                trade_event_service = get_trade_event_service()
                trade_event_service.log_warrior_fill_confirmed(
                    position_id=order_id,
                    symbol=symbol,
                    quote_price=entry_decimal,
                    fill_price=actual_fill_decimal,
                    slippage_cents=float(slippage_cents),
                    shares=int(filled_qty) if filled_qty else shares,
                )
            except Exception as e:
                logger.warning(f"[Warrior Entry] {symbol}: DB fill update failed: {e}")
            
            logger.info(
                f"[Warrior Entry] {symbol}: Bought {shares} shares @ ${actual_fill_price} "
                f"({trigger_type.value})"
            )
            
            # Clear pending entry on successful fill
            engine.clear_pending_entry(symbol)
            
        except Exception as e:
            import traceback
            logger.error(f"[Warrior Entry] {symbol}: Order failed: {e}\n{traceback.format_exc()}")
            engine.stats.last_error = str(e)
            # Clear pending entry on failure (allow retry)
            engine.clear_pending_entry(symbol)
    else:
        logger.warning(f"[Warrior Entry] {symbol}: No submit_order callback")
