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
                
                if current_price >= trigger_price:
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
                            logger.info(
                                f"[Warrior Entry] {symbol}: VWAP BREAK at ${current_price:.2f} "
                                f"(VWAP=${vwap:.2f})"
                            )
                            watched.last_below_vwap = False  # Reset for next break
                            await enter_position(
                                engine,
                                watched,
                                current_price,
                                EntryTriggerType.VWAP_BREAK
                            )
                    
        except Exception as e:
            logger.error(f"[Warrior Watch] Error checking {symbol}: {e}")


async def check_orb_setup(
    engine: "WarriorEngine",
    watched: WatchedCandidate,
    current_price: Decimal,
) -> None:
    """
    Check for Opening Range Breakout setup.
    
    Establishes the ORB high/low from the first 1-minute candle after 9:31 AM ET.
    
    Args:
        engine: The WarriorEngine instance
        watched: The watched candidate to check
        current_price: Current price of the symbol
    """
    # Get first 1-minute candle
    et_now = engine._get_eastern_time()
    
    # Only establish ORB in first minute after open
    if et_now.time() > dt_time(9, 31):
        if engine._get_intraday_bars:
            bars = await engine._get_intraday_bars(
                watched.candidate.symbol, 
                timeframe="1min",
                limit=1
            )
            if bars and len(bars) > 0:
                first_bar = bars[0]
                watched.orb_high = first_bar.high
                watched.orb_low = first_bar.low
                watched.orb_established = True
                logger.info(
                    f"[Warrior ORB] {watched.candidate.symbol}: "
                    f"High=${watched.orb_high}, Low=${watched.orb_low}"
                )


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
    
    # TOP PICK ONLY - Ross Cameron (Jan 20 2026): "TWWG was the ONLY trade I took today"
    # Only enter the highest-scoring candidate, skip the rest
    # Uses dynamic_score which includes VWAP/EMA trend bonus (trending > fading)
    if engine.config.top_pick_only:
        # Get all watched candidates sorted by dynamic score (includes trend bonus)
        all_watched = list(engine._watchlist.values())
        if all_watched:
            # Find the top scorer using dynamic_score (quality_score + trend bonus)
            top_pick = max(all_watched, key=lambda w: w.dynamic_score)
            if watched.candidate.symbol != top_pick.candidate.symbol:
                # Not the top pick - mark as triggered to prevent log spam
                top_dynamic = top_pick.dynamic_score
                our_dynamic = watched.dynamic_score
                top_static = getattr(top_pick.candidate, 'quality_score', 0) or 0
                our_static = getattr(watched.candidate, 'quality_score', 0) or 0
                logger.info(
                    f"[Warrior Entry] {symbol}: TOP_PICK_ONLY - blocked "
                    f"(dynamic={our_dynamic}, static={our_static}) "
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
    
    # Check if we already hold this symbol (prevents double-buying after restart)
    if engine._get_positions:
        try:
            positions = await engine._get_positions()
            held_symbols = {p.get("symbol") or p.symbol for p in positions if p}
            if symbol in held_symbols:
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
        # Ensure Decimal arithmetic (entry_price may be float from MockBroker)
        entry_decimal = Decimal(str(entry_price)) if not isinstance(entry_price, Decimal) else entry_price
        mental_stop = entry_decimal - Decimal(str(engine.monitor.settings.mental_stop_cents)) / 100
        stop_method = "fallback_15c"
    
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
            high_quality_threshold = 10  # TODO: Pull from scanner settings
            if quality_score >= high_quality_threshold:
                selected_exit_mode = "home_run"
            else:
                selected_exit_mode = "base_hit"
            logger.info(
                f"[Warrior Entry] {symbol}: exit_mode={selected_exit_mode} "
                f"(quality_score={quality_score}, threshold={high_quality_threshold})"
            )
            
            order_result = await engine._submit_order(
                symbol=symbol,
                shares=shares,
                side="buy",
                order_type="limit",  # Limit order, not market
                limit_price=float(limit_price),  # offset above ask
                stop_loss=None,  # Mental stop, not broker stop
                exit_mode=selected_exit_mode,  # Pass to MockBroker for GUI display
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
                )
                set_entry_order_id(order_id, order_id)
                logger.info(
                    f"[Warrior Entry] {symbol}: Intent logged to DB "
                    f"(trigger={trigger_type.value}, order_id={order_id[:8]}...)"
                )
            except Exception as e:
                logger.warning(f"[Warrior Entry] {symbol}: DB intent log failed: {e}")
            
            # If order is not filled yet, skip monitor add - DB has intent, sync will match it
            if order_status and order_status.lower() not in ("filled", "partially_filled"):
                logger.info(
                    f"[Warrior Entry] {symbol}: Order pending (status={order_status}) - "
                    f"intent recorded, will update on fill"
                )
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
