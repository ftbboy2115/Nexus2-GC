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

# =============================================================================
# SHARED HELPER IMPORTS (from dedicated helpers module)
# =============================================================================
# These are re-exported for backward compatibility with any code that
# imports them from this file. The canonical source is warrior_entry_helpers.py.
from nexus2.domain.automation.warrior_entry_helpers import (
    check_volume_confirmed,
    check_active_market,
    check_volume_expansion,
    check_falling_knife,
    check_high_volume_red_candle,
)

# =============================================================================
# EXTRACTED MODULE IMPORTS (Phase 2 Refactoring)
# =============================================================================
# Pattern detection functions (detect ABCD, whole/half, dip-for-level, PMH break, micro-pullback)
from nexus2.domain.automation.warrior_entry_patterns import (
    detect_abcd_pattern,
    detect_whole_half_anticipatory,
    detect_dip_for_level,
    detect_pmh_break,
    check_micro_pullback_entry as _check_micro_pullback_pattern,
    # Phase 3 extraction - additional patterns
    detect_pullback_pattern,
    detect_bull_flag_pattern,
    detect_vwap_break_pattern,
    detect_inverted_hs_pattern,
    detect_cup_handle_pattern,
    detect_hod_consolidation_break,
)

# Helper functions (Phase 3 extraction)
from nexus2.domain.automation.warrior_entry_helpers import (
    update_candidate_technicals,
)

# Entry guard functions (consolidated guard checks)
from nexus2.domain.automation.warrior_entry_guards import (
    check_entry_guards,
    validate_technicals,
    _check_macd_gate,
    _check_position_guards,
    _check_spread_filter,
)

# Position sizing functions
from nexus2.domain.automation.warrior_entry_sizing import (
    calculate_stop_price,
    calculate_position_size,
    calculate_profit_target,
    calculate_limit_price,
)

# Order execution functions
from nexus2.domain.automation.warrior_entry_execution import (
    determine_exit_mode,
    submit_entry_order,
    poll_for_fill,
    calculate_slippage,
    extract_order_status,
    scale_into_existing_position as _scale_into_position,
    complete_entry,
)

# Pattern Competition scoring (Phase 4 refactoring)
from nexus2.domain.automation.warrior_entry_scoring import (
    PatternCandidate,
    score_pattern,
    compute_level_proximity,
    compute_time_score,
    compute_blue_sky_pct,
    MIN_SCORE_THRESHOLD,
)

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


def check_volume_expansion(
    candles: list,
    min_expansion: float = 3.0,
    lookback: int = 10
) -> tuple[bool, float, str]:
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
            # SKIP entirely in simulation mode: prices come from historical bar data,
            # phantom quotes are impossible, and this check hits global singletons
            is_sim = getattr(engine.config, 'sim_only', False)
            if not is_sim:
                skip_phantom_check = False
                try:
                    from nexus2.adapters.simulation.historical_bar_loader import get_historical_bar_loader
                    loader = get_historical_bar_loader()
                    if loader.has_10s_bars(symbol):
                        skip_phantom_check = True  # Using high-fidelity 10s historical data
                except Exception:
                    pass
                
                if engine._get_intraday_bars and not skip_phantom_check:
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
            # Throttled to 60s intervals: with 10s stepping, technicals recompute 6x/min.
            # MACD/EMA/VWAP don't meaningfully change in 10 seconds.
            import time as _time
            _last = getattr(watched, '_last_tech_update_ts', 0)
            if _time.time() - _last >= 60:
                await update_candidate_technicals(engine, watched, current_price)
                watched._last_tech_update_ts = _time.time()
            
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
                # REFACTORED: Use extracted pattern function, then call enter_position
                micro_trigger = await _check_micro_pullback_pattern(engine, watched, current_price)
                if micro_trigger:
                    await enter_position(engine, watched, current_price, micro_trigger)
                continue  # Skip PMH break logic for extended stocks
            
            # =============================================================================
            # PATTERN COMPETITION: Parallel evaluation with scoring
            # =============================================================================
            # Instead of sequential pattern checks with early enter_position() calls,
            # we collect ALL matching patterns as candidates, score them, and pick the best.
            # This prevents first-match bias and enables quality-based selection.
            
            setup_type = getattr(watched, 'setup_type', None)
            if setup_type:
                logger.debug(f"[Warrior Entry] {symbol}: Pattern routing - setup_type={setup_type}")
            
            # -----------------------------------------------------------------
            # COMPUTE SCORING CONTEXT (once per symbol per cycle)
            # -----------------------------------------------------------------
            # Volume ratio (from candidate metadata or computed)
            volume_ratio = float(getattr(watched.candidate, 'relative_volume', 1.0) or 1.0)
            
            # Catalyst strength (from candidate metadata)
            catalyst_strength = float(getattr(watched.candidate, 'catalyst_strength', 0.5) or 0.5)
            
            # Spread % (from candidate metadata)
            spread_pct = float(getattr(watched.candidate, 'spread_percent', 0.5) or 0.5)
            
            # Level proximity (how close to whole/half dollar)
            level_proximity = compute_level_proximity(current_price)
            
            # Time score (ORB window = optimal)
            et_now = engine._get_eastern_time()
            time_score = compute_time_score(et_now.hour, et_now.minute)
            
            # Blue Sky score boost (near 52-week high = no overhead resistance)
            # Try candidate first, then fetch from FMP quote if not available
            year_high = getattr(watched.candidate, 'year_high', None)
            if year_high is None:
                try:
                    # Fresh FMP quote has yearHigh
                    fmp_quote = engine.market_data.fmp.get_quote(symbol)
                    if fmp_quote and fmp_quote.year_high:
                        year_high = fmp_quote.year_high
                except Exception:
                    pass  # Blue Sky boost just won't apply
            
            blue_sky_pct = compute_blue_sky_pct(current_price, year_high)
            if blue_sky_pct is not None and blue_sky_pct <= 5.0:
                logger.info(
                    f"[Warrior Entry] {symbol}: BLUE SKY boost - "
                    f"price ${current_price:.2f} is {blue_sky_pct:.1f}% below 52w high ${year_high:.2f}"
                )
            
            # -----------------------------------------------------------------
            # COLLECT PATTERN CANDIDATES
            # -----------------------------------------------------------------
            candidates: list[PatternCandidate] = []
            
            # Helper to add candidate with scoring
            def add_candidate(trigger: Optional[EntryTriggerType], confidence: float = 0.7):
                """Add pattern to candidates list if it triggered."""
                if trigger:
                    score = score_pattern(
                        pattern=trigger,
                        volume_ratio=volume_ratio,
                        pattern_confidence=confidence,
                        catalyst_strength=catalyst_strength,
                        spread_pct=spread_pct,
                        level_proximity=level_proximity,
                        time_score=time_score,
                        blue_sky_pct=blue_sky_pct,
                    )
                    candidates.append(PatternCandidate(
                        pattern=trigger,
                        score=score,
                        factors={
                            "confidence": confidence,
                            "volume": volume_ratio,
                            "catalyst": catalyst_strength,
                            "spread": spread_pct,
                            "level_prox": level_proximity,
                            "time": time_score,
                            "blue_sky": blue_sky_pct,
                        }
                    ))
                    logger.debug(
                        f"[Warrior Entry] {symbol}: Candidate {trigger.name} "
                        f"score={score:.3f} (conf={confidence:.2f})"
                    )
            
            # ABCD PATTERN (standalone - doesn't depend on PMH relationship)
            abcd_trigger = await detect_abcd_pattern(engine, watched, current_price, setup_type)
            add_candidate(abcd_trigger, confidence=0.75)  # ABCD has moderate-high confidence when detected
            
            # =============================================================================
            # PMH-RELATIVE CHECKS
            # =============================================================================
            
            # ROSS RE-ENTRY LOGIC: Track when price drops below PMH
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
                
                # WHOLE/HALF DOLLAR ANTICIPATORY (below PMH)
                whole_half_trigger = await detect_whole_half_anticipatory(engine, watched, current_price)
                add_candidate(whole_half_trigger, confidence=0.80)  # High confidence at psychological levels
                
                # DIP-FOR-LEVEL PATTERN (below PMH)
                dip_trigger = await detect_dip_for_level(engine, watched, current_price, setup_type)
                add_candidate(dip_trigger, confidence=0.70)
                
                # HOD CONSOLIDATION BREAK (below PMH — Ross's "break of high-of-day")
                hod_break_trigger = await detect_hod_consolidation_break(
                    engine, watched, current_price, setup_type
                )
                add_candidate(hod_break_trigger, confidence=0.85)
                
            else:
                # Price is above PMH
                
                # Check if this is a fresh breakout after pullback
                if watched.entry_triggered and watched.last_below_pmh:
                    watched.last_below_pmh = False
                    watched.entry_triggered = False  # Reset to allow new entry attempt
                    watched.entry_attempt_count += 1
                    logger.info(
                        f"[Warrior Entry] {symbol}: Fresh breakout after pullback "
                        f"(re-entry attempt #{watched.entry_attempt_count})"
                    )
                
                if watched.entry_triggered:
                    # PULLBACK PATTERN (above PMH): Ross's "break through high after dip"
                    pullback_trigger = await detect_pullback_pattern(engine, watched, current_price)
                    add_candidate(pullback_trigger, confidence=0.65)
                else:
                    # ORB trigger at 9:30
                    if engine.config.orb_enabled and not watched.orb_established:
                        await check_orb_setup(engine, watched, current_price)
                    
                    # PMH breakout
                    pmh_trigger = await detect_pmh_break(engine, watched, current_price, setup_type)
                    add_candidate(pmh_trigger, confidence=0.85)  # PMH break is high confidence
                    
                    # ORB breakout (after ORB established)
                    if watched.orb_established and watched.orb_high and current_price > watched.orb_high:
                        logger.debug(f"[Warrior Entry] {symbol}: ORB BREAKOUT candidate at ${current_price}")
                        add_candidate(EntryTriggerType.ORB, confidence=0.80)
                    
                    # BULL FLAG
                    bull_flag_trigger = await detect_bull_flag_pattern(engine, watched, current_price)
                    add_candidate(bull_flag_trigger, confidence=0.70)
                    
                    # INVERTED HEAD & SHOULDERS
                    inverted_hs_trigger = await detect_inverted_hs_pattern(engine, watched, current_price)
                    add_candidate(inverted_hs_trigger, confidence=0.65)  # Lower confidence - complex pattern
                    
                    # CUP & HANDLE
                    cup_handle_trigger = await detect_cup_handle_pattern(engine, watched, current_price)
                    add_candidate(cup_handle_trigger, confidence=0.70)
            
            # =============================================================================
            # PMH-INDEPENDENT PATTERNS (run at all price levels)
            # =============================================================================
            # VWAP breaks are about price crossing the volume-weighted average,
            # NOT about pre-market high relationship. RDIB's VWAP reclaim at $15-19
            # was never detected because PMH was $34.96 (always gated out).
            vwap_break_trigger = await detect_vwap_break_pattern(engine, watched, current_price, setup_type)
            add_candidate(vwap_break_trigger, confidence=0.75)
            
            # -----------------------------------------------------------------
            # WINNER SELECTION: Pick best candidate and enter
            # -----------------------------------------------------------------
            if candidates:
                winner = max(candidates, key=lambda c: c.score)
                
                if winner.score >= MIN_SCORE_THRESHOLD:
                    logger.info(
                        f"[Warrior Entry] {symbol}: WINNER={winner.pattern.name} "
                        f"score={winner.score:.3f} (threshold={MIN_SCORE_THRESHOLD}), "
                        f"candidates={len(candidates)}"
                    )
                    
                    # Store competition metadata on watched candidate for trade event
                    watched.entry_confidence = winner.score
                    
                    await enter_position(engine, watched, current_price, winner.pattern)
                else:
                    logger.info(
                        f"[Warrior Entry] {symbol}: Best candidate {winner.pattern.name} "
                        f"BELOW THRESHOLD ({winner.score:.3f} < {MIN_SCORE_THRESHOLD})"
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
    
    # ==========================================================================
    # PROFIT-CHECK GUARD: Block scale-ins when position is already at profit target
    # 
    # PAVM LESSON (Jan 2026): DIP_FOR_LEVEL at $14.23 had target ~$14.50.
    # Price reached $20.80 (+46%) → ABCD add reset target → held to $12.84 (-38%).
    # 
    # Ross Cameron pattern (HIND Jan 27): "I take profit off the table...then I 
    # get back in" - he takes profit FIRST, then re-enters if setup reforms.
    # ==========================================================================
    current_price = entry_price  # Scale entry price
    unrealized_pnl_per_share = current_price - existing_position.entry_price
    unrealized_pnl_pct = (unrealized_pnl_per_share / existing_position.entry_price) * 100
    
    # Block if: (1) Current price >= profit target, OR (2) Unrealized P&L > 25%
    profit_target = existing_position.profit_target or Decimal("0")
    price_past_target = profit_target > 0 and current_price >= profit_target
    pnl_above_threshold = unrealized_pnl_pct > 25  # 25% gain threshold
    
    if price_past_target or pnl_above_threshold:
        reason = (
            f"past target ${profit_target:.2f}" if price_past_target 
            else f"+{unrealized_pnl_pct:.1f}% unrealized"
        )
        logger.warning(
            f"[Warrior Entry] {symbol}: BLOCKING SCALE-IN - position already {reason}. "
            f"Take profit first per Ross Cameron methodology. "
            f"(entry=${existing_position.entry_price:.2f}, current=${current_price:.2f})"
        )
        return
    
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
    
    Orchestrates entry by calling extracted modules:
    - Guards: check_entry_guards()
    - Sizing: calculate_stop_price(), calculate_position_size()
    - Execution: submit_entry_order(), poll_for_fill()
    
    Args:
        engine: The WarriorEngine instance
        watched: The watched candidate to enter
        entry_price: Price to enter at
        trigger_type: Type of entry trigger (ORB, PMH_BREAK, etc.)
    """
    symbol = watched.candidate.symbol
    
    # =========================================================================
    # ENTRY GUARDS (via extracted module)
    # =========================================================================
    can_enter, block_reason = await check_entry_guards(
        engine, watched, entry_price, trigger_type
    )
    
    if not can_enter:
        if block_reason == "scale_into_existing":
            # MICRO_PULLBACK: Scale into existing position instead of blocking
            # REFACTORED: Use extracted scale function from warrior_entry_execution.py
            logger.info(
                f"[Warrior Entry] {symbol}: Already holding - triggering SCALE-IN "
                f"(micro-pullback re-entry at ${entry_price:.2f})"
            )
            await _scale_into_position(
                engine, watched, entry_price, trigger_type
            )
            watched.entry_triggered = True
            return
        else:
            logger.info(f"[Warrior Entry] {symbol}: {block_reason}")
            watched.entry_triggered = True
            return

    # Note: All guard checks (MIN_SCORE, BLACKLIST, FAIL_LIMIT, MACD GATE, 
    # POSITION GUARDS, PENDING ENTRIES, COOLDOWN, SPREAD FILTER) are now 
    # handled by check_entry_guards() above.
    
    # Get current_ask from spread check result (passed via watched metadata)
    # The guards module stored it if spread check was performed
    current_ask = getattr(watched, '_spread_check_ask', None)
    
    # =========================================================================
    # TECHNICAL VALIDATION (via extracted module)
    # =========================================================================
    tech_valid, tech_reason = await validate_technicals(engine, watched, entry_price)
    if not tech_valid:
        # If VWAP_BREAK was rejected because price is below session VWAP,
        # reset last_below_vwap to prevent the pattern from endlessly re-firing.
        # The pattern's VWAP (all candles) diverges from the guard's VWAP
        # (today's session only), so the pattern thinks price crossed VWAP
        # when it actually hasn't according to the accurate session VWAP.
        if trigger_type == EntryTriggerType.VWAP_BREAK and tech_reason and "below VWAP" in tech_reason:
            watched.last_below_vwap = False
            logger.info(f"[Warrior Entry] {symbol}: Reset last_below_vwap after guard VWAP rejection")
        # NOTE: validate_technicals handles logging and entry_triggered flag for FAIL-CLOSED
        return
    
    # Check if we can open new position (max positions, daily loss)
    if not await engine._can_open_position():
        logger.info(f"[Warrior Entry] {symbol}: Cannot open (max positions or daily loss)")
        return
    
    # =========================================================================
    # POSITION SIZING (via extracted module)
    # =========================================================================
    
    # Mark as triggered
    watched.entry_triggered = True
    watched.last_below_vwap = False  # Reset VWAP break tracking after successful entry
    engine.stats.entries_triggered += 1
    
    # Calculate stop price using consolidation low methodology
    mental_stop, stop_method, calculated_candle_low = await calculate_stop_price(
        engine, symbol, entry_price
    )
    
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
    
    # MAX STOP DISTANCE WARNING
    # Ross uses tight stops (1-3%). If consolidation low produces an absurdly wide stop,
    # log a warning for visibility. Hard-blocking was too aggressive — volatile gappers
    # naturally have wide 5-bar consolidation lows during sparse premarket periods.
    # TODO: Improve calculate_stop_price to use entry bar low instead of 5-bar consolidation low
    max_stop_distance_pct = Decimal("0.15")  # 15% threshold for warning
    stop_distance = abs(entry_price - mental_stop)
    stop_distance_pct = stop_distance / entry_price if entry_price > 0 else Decimal("1")
    
    if stop_distance_pct > max_stop_distance_pct:
        logger.warning(
            f"[Warrior Entry] {symbol}: WIDE STOP WARNING - "
            f"${mental_stop:.2f} is {stop_distance_pct:.1%} from entry ${entry_price:.2f} "
            f"(>{max_stop_distance_pct:.0%}). Consolidation low may span too much time."
        )
    
    # Calculate position size based on risk per trade and stop distance
    shares = calculate_position_size(
        engine, watched, entry_price, mental_stop
    )
    
    if shares is None or shares < 1:
        if shares is None:
            logger.warning(f"[Warrior Entry] {symbol}: Invalid risk calculation")
        else:
            logger.info(f"[Warrior Entry] {symbol}: Position too small")
        return
    
    # =========================================================================
    # ORDER SUBMISSION
    # =========================================================================
    
    # Calculate limit price using current ask or fallback
    entry_decimal = Decimal(str(entry_price)) if not isinstance(entry_price, Decimal) else entry_price
    limit_price = calculate_limit_price(entry_decimal, current_ask)
    
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
            
            # EXIT MODE SELECTION:
            # Start with session setting as default, only override for exceptional cases
            # This respects user's configured session_exit_mode in monitor settings
            session_exit_mode = engine.monitor.settings.session_exit_mode
            selected_exit_mode = session_exit_mode  # Default to user's session setting
            
            # RE-ENTRY / VOLUME EXPLOSION OVERRIDE:
            # Only override session setting for truly exceptional conditions
            is_reentry = watched.entry_attempt_count > 0 and watched.last_exit_time is not None
            entry_volume_ratio = getattr(watched, 'entry_volume_ratio', 0) or 0
            
            if is_reentry:
                # RE-ENTRY SAFETY VALVE: Force base_hit for re-entries
                # Ross CMCT transcript (Dec 2025): Re-entries are quick scalps, not home runs
                # "I add on the dip... when it broke the low of 85, I had to sell"
                # Take quick +18¢ profit, cut if it doesn't work - don't bag-hold
                selected_exit_mode = "base_hit"
                logger.info(
                    f"[Warrior Entry] {symbol}: exit_mode=base_hit "
                    f"(RE-ENTRY #{watched.entry_attempt_count}: quick scalp mode, not home run)"
                )
            elif entry_volume_ratio >= 5.0:
                # Extreme volume explosion (5x+): override to home_run for potential runner
                selected_exit_mode = "home_run"
                logger.info(
                    f"[Warrior Entry] {symbol}: exit_mode=home_run "
                    f"(VOLUME EXPLOSION: {entry_volume_ratio:.1f}x, overriding session setting)"
                )
            else:
                # Use session setting (base_hit or home_run)
                logger.info(
                    f"[Warrior Entry] {symbol}: exit_mode={selected_exit_mode} "
                    f"(using session setting)"
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
                
                # ENTRY VALIDATION LOG: Capture expected outcome for data-driven tuning
                validation_parts = []
                if watched.expected_target:
                    validation_parts.append(f"target=${watched.expected_target:.2f}")
                if watched.expected_stop:
                    validation_parts.append(f"stop=${watched.expected_stop:.2f}")
                if watched.entry_confidence:
                    validation_parts.append(f"conf={watched.entry_confidence:.2f}")
                if watched.ross_entry:
                    delta = float(entry_decimal) - float(watched.ross_entry)
                    validation_parts.append(f"ross=${watched.ross_entry:.2f} Δ${delta:+.2f}")
                if validation_parts:
                    logger.info(
                        f"[ENTRY VALIDATION] {symbol}: {', '.join(validation_parts)}"
                    )
                    # Persist to DB for Data Explorer
                    from nexus2.db.warrior_db import log_entry_validation
                    log_entry_validation(
                        trade_id=order_id,
                        symbol=symbol,
                        entry_price=float(entry_decimal),
                        entry_trigger=trigger_type.value,
                        expected_target=float(watched.expected_target) if watched.expected_target else None,
                        expected_stop=float(watched.expected_stop) if watched.expected_stop else None,
                        entry_confidence=float(watched.entry_confidence) if watched.entry_confidence else None,
                        ross_entry=float(watched.ross_entry) if watched.ross_entry else None,
                        ross_pnl=float(watched.ross_pnl) if watched.ross_pnl else None,
                        is_sim=engine.monitor.sim_mode,
                    )
                
                # CRITICAL: Log ENTRY event to trade_event_service BEFORE fill confirmation
                # This ensures correct audit order: ENTRY -> FILL_CONFIRMED
                from nexus2.domain.automation.trade_event_service import trade_event_service
                
                # Use the SAME snapshot that was calculated at the MACD gate
                # This ensures audit trail matches exactly what was used for the entry decision
                # (Fixes "Technical context unavailable" bug where audit used different data path)
                tech_context = None
                entry_snapshot = getattr(watched, 'entry_snapshot', None)
                if entry_snapshot:
                    tech_context = {
                        "symbol_vwap": float(entry_snapshot.vwap) if entry_snapshot.vwap else None,
                        "symbol_above_vwap": float(entry_decimal) > float(entry_snapshot.vwap) if entry_snapshot.vwap else None,
                        "symbol_ema9": float(entry_snapshot.ema_9) if entry_snapshot.ema_9 else None,
                        "symbol_above_ema9": float(entry_decimal) > float(entry_snapshot.ema_9) if entry_snapshot.ema_9 else None,
                        "symbol_macd_value": float(entry_snapshot.macd_histogram) if entry_snapshot.macd_histogram else None,
                        "symbol_macd_status": "positive" if entry_snapshot.macd_histogram and entry_snapshot.macd_histogram > 0.05 else ("negative" if entry_snapshot.macd_histogram and entry_snapshot.macd_histogram < -0.05 else "flat"),
                        "data_insufficient": getattr(entry_snapshot, 'data_insufficient', False),
                        "source": "entry_decision",  # AUDIT: Indicates this is from the actual entry decision, not a re-fetch
                    }
                else:
                    logger.warning(f"[Warrior Entry] {symbol}: No entry_snapshot available for audit logging")
                
                trade_event_service.log_warrior_entry(
                    position_id=order_id,
                    symbol=symbol,
                    entry_price=entry_decimal,
                    stop_price=mental_stop,
                    shares=shares,
                    trigger_type=trigger_type.value,
                    technical_context=tech_context,
                    exit_mode=selected_exit_mode,  # For Entry Type column display
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
                    from nexus2.domain.automation.trade_event_service import trade_event_service
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
            
            
            # NOTE: Fill price has already been polled above (lines 1177-1225)
            # actual_fill_price is already set from the poll loop
            
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
                
                # NOTE: FILL_CONFIRMED is logged in the poll block above (around line 2435)
                # when actual fill price is obtained. Do not duplicate here.
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
