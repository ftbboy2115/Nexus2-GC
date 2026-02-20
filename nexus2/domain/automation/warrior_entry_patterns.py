"""
Warrior Entry Pattern Detection

Extracted pattern detection wrapper functions from warrior_engine_entry.py.
Each function returns the trigger type if pattern fires, None otherwise.

IMPORTANT: These functions do NOT call enter_position() - the caller handles that.
This enables unit testing of pattern detection in isolation.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from nexus2.domain.automation.warrior_engine import WarriorEngine
    from nexus2.domain.automation.warrior_engine_types import WatchedCandidate

from nexus2.domain.automation.warrior_engine_types import EntryTriggerType

# Import shared helper functions from the helpers module (avoids circular import)
from nexus2.domain.automation.warrior_entry_helpers import (
    check_active_market,
    check_falling_knife,
    check_volume_confirmed,
    check_volume_expansion,
    check_high_volume_red_candle,
)

logger = logging.getLogger(__name__)


# =============================================================================
# PATTERN DETECTION FUNCTIONS
# =============================================================================


async def detect_abcd_pattern(
    engine: "WarriorEngine",
    watched: "WatchedCandidate",
    current_price: Decimal,
    setup_type: Optional[str],
) -> Optional[EntryTriggerType]:
    """
    Detect ABCD pattern breakout.
    
    Ross Cameron (Jan 29 2026): DCX for +$6,268
    Cold-day strategy: A (low) → B (rally high) → C (higher low) → D (break B)
    Entry: When price breaks above B high (D point) with volume
    Stop: Below C low
    Target: Measured move (AB distance from C)
    
    Args:
        engine: WarriorEngine instance
        watched: WatchedCandidate being evaluated
        current_price: Current stock price
        setup_type: Optional setup type filter from test case
        
    Returns:
        EntryTriggerType.ABCD if pattern triggers, None otherwise
    """
    symbol = watched.candidate.symbol
    
    # PATTERN COMPETITION: Only check if setup_type is None or "abcd"
    should_check_abcd = setup_type is None or setup_type == "abcd"
    if not (engine.config.abcd_enabled and not watched.entry_triggered and should_check_abcd):
        return None
    
    if not engine._get_intraday_bars:
        return None
    
    try:
        candles = await engine._get_intraday_bars(symbol, "1min", limit=40)
        if not candles or len(candles) < 15:
            return None
        
        from nexus2.domain.indicators.pattern_service import get_pattern_service
        pattern_svc = get_pattern_service()
        
        candle_dicts = [
            {"high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
            for c in candles
        ]
        
        # Detect ABCD pattern
        pattern = pattern_svc.detect_abcd(candle_dicts, lookback=30, symbol=symbol)
        
        if not pattern:
            return None
        
        watched.abcd_pattern = pattern
        from datetime import datetime, timezone
        watched.abcd_detected_at = datetime.now(timezone.utc)
        
        # Check for D breakout (price breaks above B high)
        if not pattern.is_breakout(current_price, buffer_cents=5):
            return None
        
        # Volume confirmation: current bar should have higher volume
        current_bar_vol = candles[-1].volume if candles else 0
        avg_vol = sum(c.volume for c in candles[-10:]) / 10 if len(candles) >= 10 else 0
        
        # Require volume above average (80% of avg is acceptable)
        vol_confirmed = current_bar_vol >= avg_vol * 0.8
        
        if not vol_confirmed:
            logger.debug(
                f"[Warrior Entry] {symbol}: ABCD breakout "
                f"but volume not confirmed ({current_bar_vol:,} < avg {avg_vol:,.0f})"
            )
            return None
        
        logger.info(
            f"[Warrior Entry] {symbol}: ABCD BREAKOUT at ${current_price:.2f} "
            f"(A=${pattern.a_low:.2f}, B=${pattern.b_high:.2f}, C=${pattern.c_low:.2f}, "
            f"stop=${pattern.stop_price:.2f}, target=${pattern.target_price:.2f}, "
            f"R:R={pattern.risk_reward:.1f}, conf={pattern.confidence:.2f})"
        )
        
        # ENTRY VALIDATION: Capture intent for entry
        watched.expected_target = Decimal(str(pattern.target_price))
        watched.expected_stop = Decimal(str(pattern.stop_price))
        watched.entry_confidence = pattern.confidence
        
        return EntryTriggerType.ABCD
        
    except Exception as e:
        logger.debug(f"[Warrior Entry] {symbol}: ABCD check failed: {e}")
        return None


async def detect_whole_half_anticipatory(
    engine: "WarriorEngine",
    watched: "WatchedCandidate",
    current_price: Decimal,
) -> Optional[EntryTriggerType]:
    """
    Detect Whole/Half Dollar Anticipatory entry.
    
    Ross Cameron's #1 momentum entry:
    "Best entry for me $5.97 for the break of six" (GRI Jan 28 2026)
    
    Entry in 3-10 cent zone BELOW a whole/half dollar level when
    momentum is pushing toward that level.
    
    Args:
        engine: WarriorEngine instance
        watched: WatchedCandidate being evaluated
        current_price: Current stock price
        
    Returns:
        EntryTriggerType.WHOLE_HALF_ANTICIPATORY if pattern triggers, None otherwise
    """
    symbol = watched.candidate.symbol
    
    if not (engine.config.whole_half_anticipatory_enabled and not watched.entry_triggered):
        return None
    
    # Must be below PMH for this pattern
    if current_price >= watched.pmh:
        return None
    
    current_float = float(current_price)
    
    # Find nearest whole ($6.00) and half ($5.50) dollar levels ABOVE current
    nearest_whole = int(current_float) + 1  # e.g., $5.97 -> $6.00
    nearest_half = (int(current_float * 2) + 1) / 2  # e.g., $5.37 -> $5.50
    
    # Check both levels
    for level, level_type in [(nearest_whole, "whole"), (nearest_half, "half")]:
        distance_cents = (level - current_float) * 100
        
        # Log distance check (INFO only when close to range)
        if distance_cents > 0 and distance_cents < 20:
            logger.info(
                f"[Warrior Entry] {symbol}: WHOLE/HALF distance check - "
                f"${current_float:.2f} is {distance_cents:.1f}¢ from ${level:.2f} ({level_type})"
            )
        
        # ANTICIPATORY ZONE: 3-10 cents BELOW the level
        # Ross buys at $5.97 for break of $6.00 (3 cents below)
        if not (3 <= distance_cents <= 10):
            continue
        
        # MOMENTUM CHECK: Detect if current tick is BREAKING OUT
        has_momentum = False
        breakout_above_range = False
        range_high = None
        
        if not engine._get_intraday_bars:
            continue
        
        try:
            candles = await engine._get_intraday_bars(symbol, "1min", limit=10)
            if not candles or len(candles) < 3:
                continue
            
            # Get recent range from completed bars
            range_high = max(c.high for c in candles[-5:])
            range_low = min(c.low for c in candles[-5:])
            
            if range_high <= range_low:
                continue
            
            # BREAKOUT DETECTION: current tick above range high
            breakout_above_range = current_float > range_high * 1.02  # 2% above
            
            # POSITION IN RANGE: how far into the range
            position_in_range = (current_float - range_low) / (range_high - range_low)
            
            # MOMENTUM = breaking out OR already significantly extended (>90%)
            has_momentum = breakout_above_range or position_in_range > 0.9
            
            logger.info(
                f"[Warrior Entry] {symbol}: WHOLE/HALF MOMENTUM CHECK - "
                f"breakout={breakout_above_range} (price ${current_float:.2f} vs range high ${range_high:.2f}), "
                f"range_pos={position_in_range:.1%}, result={'PASS' if has_momentum else 'FAIL'}"
            )
            
        except Exception as e:
            logger.warning(f"[Warrior Entry] {symbol}: Momentum check failed: {e}")
            continue
        
        if not has_momentum:
            continue
        
        # VOLUME CHECK: Only require volume if NOT a clear breakout
        vol_ok = True
        vol_ratio = 0.0
        
        if not breakout_above_range:
            # Not a clear breakout - require volume confirmation
            vol_ok, vol_ratio, vol_reason = check_volume_expansion(
                candles, min_expansion=1.5, lookback=10
            )
            if not vol_ok:
                logger.info(
                    f"[Warrior Entry] {symbol}: WHOLE/HALF near ${level:.2f} but "
                    f"volume weak ({vol_reason}). Waiting for volume spike..."
                )
                continue
        else:
            # Clear breakout - price action confirms, skip volume wait
            logger.info(
                f"[Warrior Entry] {symbol}: WHOLE/HALF BREAKOUT CONFIRMED - "
                f"price ${current_float:.2f} broke above range ${range_high:.2f}, entering..."
            )
        
        logger.info(
            f"[Warrior Entry] {symbol}: WHOLE/HALF ANTICIPATORY - "
            f"${current_price:.2f} for break of ${level:.2f} ({level_type}) "
            f"[breakout={breakout_above_range}]"
        )
        
        watched.target_level = Decimal(str(level))
        watched.entry_volume_ratio = vol_ratio if vol_ratio > 0 else 1.0
        
        return EntryTriggerType.WHOLE_HALF_ANTICIPATORY
    
    return None


async def detect_dip_for_level(
    engine: "WarriorEngine",
    watched: "WatchedCandidate",
    current_price: Decimal,
    setup_type: Optional[str],
    activity_candles: list = None,
) -> Optional[EntryTriggerType]:
    """
    Detect DIP-FOR-LEVEL pattern.
    
    Ross Cameron buys dips near psychological levels.
    Example: TNMG at $3.93, target $4.00 level.
    
    Requirements:
    - Price below PMH
    - Above VWAP (not a falling knife)
    - Near a key level (whole/half dollars)
    - Volume expansion present
    - Active market (not dead premarket)
    
    Args:
        engine: WarriorEngine instance
        watched: WatchedCandidate being evaluated
        current_price: Current stock price
        setup_type: Optional setup type filter from test case
        activity_candles: Optional pre-fetched candles for efficiency
        
    Returns:
        EntryTriggerType.DIP_FOR_LEVEL if pattern triggers, None otherwise
    """
    symbol = watched.candidate.symbol
    
    if not (engine.config.dip_for_level_enabled and not watched.entry_triggered):
        return None
    
    # Must be below PMH for this pattern
    if current_price >= watched.pmh:
        return None
    
    # TIME GATE: DIP_FOR_LEVEL requires established intraday structure
    from datetime import datetime
    import pytz
    et = pytz.timezone("US/Eastern")
    now_et = datetime.now(et)
    
    # Get sim clock time if we're in sim mode
    try:
        from nexus2.adapters.simulation import get_simulation_clock
        sim_clock = get_simulation_clock()
        if sim_clock and sim_clock.current_time:
            now_et = sim_clock.current_time
    except Exception:
        pass
    
    if now_et.hour < 6:
        logger.info(
            f"[Warrior Entry] {symbol}: DIP_FOR_LEVEL blocked - early premarket "
            f"({now_et.strftime('%H:%M')}). Wait until 06:00+."
        )
        return None
    
    # FALLING KNIFE FILTER
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
                
                is_above_20_ema = snapshot.ema_20 and current_price > Decimal(str(snapshot.ema_20))
                macd_ok = snapshot.is_macd_bullish
                
                if not is_above_20_ema and not macd_ok:
                    is_falling_knife = True
                    logger.info(
                        f"[Warrior Entry] {symbol}: FALLING KNIFE - blocked dip entry "
                        f"(below 20 EMA ${snapshot.ema_20:.2f}, MACD negative)"
                    )
        except Exception as e:
            # FAIL-CLOSED: Cannot verify falling knife status - block entry
            logger.warning(
                f"[Warrior Entry] {symbol}: FAIL-CLOSED - Falling knife check failed: {e}. "
                f"Cannot verify trend safety, blocking DIP_FOR_LEVEL entry."
            )
            return None
    
    if is_falling_knife:
        return None
    
    # VWAP GATE: Must be above VWAP
    if not watched.current_vwap:
        logger.info(
            f"[Warrior Entry] {symbol}: DIP_FOR_LEVEL blocked - no VWAP data yet. "
            f"Wait for sufficient candles."
        )
        return None
    
    if current_price < watched.current_vwap:
        logger.info(
            f"[Warrior Entry] {symbol}: DIP_FOR_LEVEL blocked - below VWAP "
            f"(${current_price:.2f} < VWAP ${watched.current_vwap:.2f}). "
            f"Wait for VWAP break first."
        )
        return None
    
    # KEY LEVEL CHECK
    levels = engine._get_key_levels(current_price)
    levels_above = [l for l in levels if l > current_price]
    if not levels_above:
        return None
    
    nearest_level = min(levels_above)
    distance_cents = int((nearest_level - current_price) * 100)
    
    if distance_cents > engine.config.level_proximity_cents:
        return None
    
    # ACTIVE MARKET CHECK
    market_active = True
    inactive_reason = ""
    
    if engine._get_intraday_bars:
        try:
            if activity_candles is None:
                tf = engine.config.entry_bar_timeframe
                if tf == "10s":
                    activity_candles = await engine._get_intraday_bars(symbol, "10s", limit=60)
                else:
                    activity_candles = await engine._get_intraday_bars(symbol, "1min", limit=10)
            
            logger.info(
                f"[Warrior Entry] {symbol}: DIP-FOR-LEVEL active market check - "
                f"got {len(activity_candles) if activity_candles else 0} candles"
            )
            
            if activity_candles:
                # Adjust thresholds for 10s bars vs 1min bars
                tf = engine.config.entry_bar_timeframe
                if tf == "10s":
                    market_active, inactive_reason = check_active_market(
                        activity_candles,
                        min_bars=18,
                        min_volume_per_bar=200,
                        max_time_gap_minutes=5,
                    )
                else:
                    market_active, inactive_reason = check_active_market(
                        activity_candles,
                        min_bars=5,
                        min_volume_per_bar=1000,
                        max_time_gap_minutes=15,
                    )
                logger.info(
                    f"[Warrior Entry] {symbol}: DIP-FOR-LEVEL active market result: "
                    f"active={market_active}, reason='{inactive_reason}'"
                )
        except Exception as e:
            logger.warning(f"[Warrior Entry] {symbol}: DIP-FOR-LEVEL active market check FAILED: {e}")
    
    if not market_active:
        logger.info(
            f"[Warrior Entry] {symbol}: DIP-FOR-LEVEL BLOCKED - market not active "
            f"({inactive_reason}). Waiting for more activity..."
        )
        return None
    
    # RE-ENTRY GUARDS
    is_reentry = watched.entry_attempt_count > 0 and watched.last_exit_time is not None
    reentry_volume_threshold = 5.0
    reentry_cooldown_minutes = 10
    max_entry_attempts = 2
    
    if is_reentry:
        from datetime import timedelta
        from nexus2.utils.time_utils import now_utc
        
        # Guard 1: Cooldown
        if watched.last_exit_time:
            time_since_exit = (now_utc() - watched.last_exit_time).total_seconds() / 60
            if time_since_exit < reentry_cooldown_minutes:
                logger.debug(
                    f"[Warrior Entry] {symbol}: RE-ENTRY cooldown "
                    f"({time_since_exit:.1f}m < {reentry_cooldown_minutes}m)"
                )
                return None
        
        # Guard 2: Max attempts
        if watched.entry_attempt_count >= max_entry_attempts:
            logger.info(
                f"[Warrior Entry] {symbol}: RE-ENTRY BLOCKED - max attempts "
                f"({watched.entry_attempt_count} >= {max_entry_attempts})"
            )
            return None
        
        # Guard 3: Price above last exit
        if watched.last_exit_price and current_price < watched.last_exit_price:
            logger.debug(
                f"[Warrior Entry] {symbol}: RE-ENTRY blocked - price ${current_price:.2f} "
                f"< exit ${watched.last_exit_price:.2f} (not buying strength)"
            )
            return None
    
    # VOLUME EXPANSION CHECK
    min_volume_expansion = reentry_volume_threshold if is_reentry else 3.0
    vol_ok, vol_ratio, vol_reason = check_volume_expansion(
        activity_candles,
        min_expansion=min_volume_expansion,
        lookback=10
    )
    
    if not vol_ok:
        logger.info(
            f"[Warrior Entry] {symbol}: DIP-FOR-LEVEL BLOCKED - "
            f"volume {vol_ratio:.1f}x avg ({vol_reason}). Waiting for volume spike..."
        )
        return None
    
    logger.info(
        f"[Warrior Entry] {symbol}: DIP-FOR-LEVEL volume OK - {vol_ratio:.1f}x avg"
        f"{' (RE-ENTRY)' if is_reentry else ''}"
    )
    
    # Store volume ratio and target level
    watched.entry_volume_ratio = vol_ratio
    watched.target_level = nearest_level
    
    logger.info(
        f"[Warrior Entry] {symbol}: DIP-FOR-LEVEL pattern "
        f"(${current_price:.2f} near ${nearest_level}, "
        f"dip {watched.dip_from_high_pct:.1f}%)"
    )
    
    return EntryTriggerType.DIP_FOR_LEVEL


async def detect_pmh_break(
    engine: "WarriorEngine",
    watched: "WatchedCandidate",
    current_price: Decimal,
    setup_type: Optional[str],
) -> Optional[EntryTriggerType]:
    """
    Detect PMH (Pre-Market High) breakout with candle confirmation.
    
    Ross Cameron "Candle Over Candle" pattern:
    - First candle exceeds PMH = "control candle"
    - Entry triggers when NEXT candle breaks control candle's high
    
    This naturally filters rejection wicks (LCFY 08:01 had high $7.26 but close $6.20).
    
    Args:
        engine: WarriorEngine instance
        watched: WatchedCandidate being evaluated
        current_price: Current stock price
        setup_type: Optional setup type filter from test case
        
    Returns:
        EntryTriggerType.PMH_BREAK if pattern triggers, None otherwise
    """
    symbol = watched.candidate.symbol
    
    # PATTERN COMPETITION: Only check if setup_type matches
    should_check_pmh = setup_type is None or setup_type == "pmh"
    if not (engine.config.pmh_enabled and not watched.entry_triggered and should_check_pmh):
        return None
    
    trigger_price = watched.pmh + engine.config.pmh_buffer_cents / 100
    
    if current_price < trigger_price:
        return None
    
    # Get current candle info for confirmation logic
    current_candle_high = None
    current_candle_time = None
    
    if engine._get_intraday_bars:
        try:
            candles = await engine._get_intraday_bars(symbol, "1min", limit=2)
            if candles and len(candles) >= 1:
                current_candle = candles[-1]
                current_candle_high = Decimal(str(current_candle.high))
                
                if hasattr(current_candle, 'timestamp') and current_candle.timestamp:
                    current_candle_time = (
                        current_candle.timestamp.strftime("%H:%M") 
                        if hasattr(current_candle.timestamp, 'strftime') 
                        else str(current_candle.timestamp)
                    )
                else:
                    try:
                        from nexus2.adapters.simulation import get_simulation_clock
                        sim_clock = get_simulation_clock()
                        current_candle_time = sim_clock.get_time_string()
                    except Exception:
                        current_candle_time = "unknown"
        except Exception as e:
            logger.debug(f"[Warrior Entry] {symbol}: Candle fetch for confirmation failed: {e}")
    
    # ACTIVE MARKET GATE
    market_active = True
    inactive_reason = ""
    
    if engine._get_intraday_bars:
        try:
            tf = engine.config.entry_bar_timeframe
            if tf == "10s":
                activity_candles = await engine._get_intraday_bars(symbol, "10s", limit=60)
            else:
                activity_candles = await engine._get_intraday_bars(symbol, "1min", limit=10)
            logger.info(
                f"[Warrior Entry] {symbol}: Active market check - got {len(activity_candles) if activity_candles else 0} candles"
            )
            if activity_candles:
                # Adjust thresholds for 10s bars vs 1min bars
                if tf == "10s":
                    market_active, inactive_reason = check_active_market(
                        activity_candles,
                        min_bars=18,
                        min_volume_per_bar=200,
                        max_time_gap_minutes=5,
                    )
                else:
                    market_active, inactive_reason = check_active_market(
                        activity_candles,
                        min_bars=5,
                        min_volume_per_bar=1000,
                        max_time_gap_minutes=15,
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
        return None
    
    # STAGE 1: Set control candle if not already set
    if watched.control_candle_high is None:
        watched.control_candle_high = current_candle_high if current_candle_high else current_price
        watched.control_candle_time = current_candle_time if current_candle_time else "N/A"
        logger.info(
            f"[Warrior Entry] {symbol}: PMH break detected at {watched.control_candle_time}, "
            f"control candle high=${watched.control_candle_high:.2f} - waiting for confirmation"
        )
        return None
    
    # STAGE 2: Check if CURRENT candle is DIFFERENT from control candle and breaks control high
    if current_candle_time and current_candle_time != watched.control_candle_time:
        if current_price > watched.control_candle_high:
            logger.info(
                f"[Warrior Entry] {symbol}: CANDLE CONFIRMATION - "
                f"${current_price:.2f} breaks control high ${watched.control_candle_high:.2f} "
                f"(control set at {watched.control_candle_time})"
            )
            return EntryTriggerType.PMH_BREAK
        else:
            logger.debug(
                f"[Warrior Entry] {symbol}: Waiting for break of control high "
                f"${watched.control_candle_high:.2f} (current=${current_price:.2f})"
            )
    
    return None


async def check_micro_pullback_entry(
    engine: "WarriorEngine",
    watched: "WatchedCandidate",
    current_price: Decimal,
) -> Optional[EntryTriggerType]:
    """
    MICRO-PULLBACK ENTRY for extended stocks (>100% gap).
    
    Pattern (Ross Cameron methodology):
    1. Stock making higher highs (uptrend), above VWAP
    2. Small dip occurs on LIGHT volume (healthy pullback)
    3. Entry when price breaks prior swing high on HIGHER volume
    4. MACD must be positive ("green light" system)
    
    Example: VERO at $5.92 - break of swing high, not PMH
    
    Args:
        engine: WarriorEngine instance
        watched: WatchedCandidate being evaluated
        current_price: Current stock price
        
    Returns:
        EntryTriggerType.MICRO_PULLBACK if pattern triggers, None otherwise
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
                return None
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
            return None
    
    # MACD check (Ross relaxes for scalps - allow near-zero)
    # Ross enters extended stock scalps when MACD is near zero, not strictly positive
    macd_tolerance = engine.config.micro_pullback_macd_tolerance
    macd_ok = is_macd_bullish or (macd_val >= macd_tolerance)
    
    if engine.config.require_macd_positive and not macd_ok:
        logger.info(
            f"[Warrior Entry] {symbol}: MICRO_PULLBACK skip - MACD too negative "
            f"({macd_val:.4f} < {macd_tolerance}, {macd_debug_info})"
        )
        return None
    
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
            return None
        
        logger.info(
            f"[Warrior Entry] {symbol}: MICRO_PULLBACK ENTRY "
            f"(${current_price:.2f} breaks ${watched.swing_high:.2f}, "
            f"vol {current_bar_volume:,} > {prior_bar_volume:,})"
        )
        # Update state for caller
        watched.swing_high = current_price
        watched.micro_pullback_ready = False
        return EntryTriggerType.MICRO_PULLBACK
    
    # TRACK SWING HIGHS (only if not ready or first high)
    if watched.swing_high is None or current_price > watched.swing_high:
        watched.swing_high = current_price
        watched.swing_high_time = datetime.now(timezone.utc).strftime("%H:%M")
        watched.pullback_low = None
        watched.micro_pullback_ready = False
        logger.info(f"[Warrior Entry] {symbol}: New swing high ${watched.swing_high:.2f}")
        return None
    
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
        return None
    
    # If we reach here, price == swing_high (rare edge case, do nothing)
    return None


# =============================================================================
# ADDITIONAL PATTERN DETECTION FUNCTIONS (Phase 3 Extraction)
# =============================================================================


async def detect_pullback_pattern(
    engine: "WarriorEngine",
    watched: "WatchedCandidate",
    current_price: Decimal,
) -> Optional[EntryTriggerType]:
    """
    Detect PULLBACK pattern (above PMH): Ross's "break through high after dip".
    
    When price has run above PMH, then pulls back from HOD.
    Re-entry on "first candle to make new high" after pullback.
    
    Pattern requirements:
    - 2-10% pullback from HOD
    - Near a key level (VWAP or round-number)
    
    Args:
        engine: WarriorEngine instance
        watched: WatchedCandidate being evaluated
        current_price: Current stock price
        
    Returns:
        EntryTriggerType.PULLBACK if pattern triggers, None otherwise
    """
    symbol = watched.candidate.symbol
    
    if not (engine.config.pullback_enabled and watched.recent_high):
        return None
    
    pullback_pct = float(
        (watched.recent_high - current_price) / watched.recent_high * 100
    )
    watched.dip_from_high_pct = pullback_pct
    
    # Trigger if 2-10% pullback from HOD and near a level (or VWAP)
    if not (2.0 <= pullback_pct <= 10.0):
        return None
    
    # Get levels including VWAP
    levels = engine._get_key_levels(current_price)
    
    # Fetch VWAP from technical service
    vwap = None
    candles = None
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
        return EntryTriggerType.PULLBACK
    
    return None


async def detect_bull_flag_pattern(
    engine: "WarriorEngine",
    watched: "WatchedCandidate",
    current_price: Decimal,
) -> Optional[EntryTriggerType]:
    """
    Detect BULL FLAG pattern - Ross Cameron: "First green after pullback".
    
    Pattern: 2+ consecutive red candles (pullback), then first green candle
    breaks above the previous candle's high.
    
    Args:
        engine: WarriorEngine instance
        watched: WatchedCandidate being evaluated
        current_price: Current stock price
        
    Returns:
        EntryTriggerType.BULL_FLAG if pattern triggers, None otherwise
    """
    symbol = watched.candidate.symbol
    
    if not (engine.config.bull_flag_enabled and not watched.entry_triggered):
        return None
    
    if not engine._get_intraday_bars:
        return None
    
    try:
        candles = await engine._get_intraday_bars(symbol, "1min", limit=10)
        if not candles or len(candles) < 3:
            return None
        
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
            return EntryTriggerType.BULL_FLAG
        
        # Update tracking for next iteration
        watched.last_candle_was_green = current_is_green
        
    except Exception as e:
        logger.debug(f"[Warrior Entry] {symbol}: Bull flag check failed: {e}")
    
    return None


async def detect_vwap_break_pattern(
    engine: "WarriorEngine",
    watched: "WatchedCandidate",
    current_price: Decimal,
    setup_type: Optional[str],
) -> Optional[EntryTriggerType]:
    """
    Detect VWAP BREAK pattern - Ross Cameron (Jan 20 2026): 
    "I took this trade for the break through VWAP".
    
    Pattern: Stock pulls back below VWAP, consolidates, then breaks back above.
    This is distinct from VWAP_RECLAIM (which is reclaiming after losing VWAP).
    
    Filters:
    - Falling knife filter (below 20 EMA + MACD negative)
    - Volume confirmation required
    - High volume red candle filter
    
    Args:
        engine: WarriorEngine instance
        watched: WatchedCandidate being evaluated
        current_price: Current stock price
        setup_type: Optional setup type filter from test case
        
    Returns:
        EntryTriggerType.VWAP_BREAK if pattern triggers, None otherwise
    """
    symbol = watched.candidate.symbol
    
    # EARLY PREMARKET GUARD: No VWAP breaks before 6 AM ET
    # Precedent: detect_dip_for_level_pattern has the same guard (line 319)
    # VWAP from <6 min of data is noise, not a tradeable signal
    from nexus2.utils.time_utils import now_et
    current_et = now_et()
    try:
        from nexus2.adapters.simulation import get_simulation_clock
        sim_clock = get_simulation_clock()
        if sim_clock and sim_clock.current_time:
            current_et = sim_clock.current_time
    except Exception:
        pass
    
    if current_et.hour < 6:
        return None
    
    # PATTERN COMPETITION: Only check if setup_type matches
    should_check_vwap_break = setup_type is None or setup_type in ("vwap_break", "vwap_reclaim")
    if not (engine.config.vwap_break_enabled and not watched.entry_triggered and should_check_vwap_break):
        return None
    
    if not engine._get_intraday_bars:
        return None
    
    # Use shared session VWAP utility (same calculation as entry guard)
    from nexus2.domain.automation.warrior_vwap_utils import get_session_vwap, get_session_bar_limit
    
    vwap = await get_session_vwap(engine, symbol, float(current_price))
    if not vwap:
        return None
    
    # Fetch candles for volume/falling knife checks (using session-accurate limit)
    candles = None
    snapshot = None
    
    try:
        bar_limit = get_session_bar_limit(engine)
        candles = await engine._get_intraday_bars(symbol, "1min", limit=bar_limit)
        if candles and len(candles) >= 5:
            from nexus2.domain.indicators import get_technical_service
            tech = get_technical_service()
            candle_dicts = [
                {"high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
                for c in candles
            ]
            snapshot = tech.get_snapshot(symbol, candle_dicts, float(current_price))
    except Exception as e:
        logger.debug(f"[Warrior Entry] {symbol}: Candle fetch for VWAP break checks failed: {e}")
        return None
    
    if not vwap:
        return None
    
    # Track when price is below VWAP (setup for break)
    if current_price < vwap:
        if not watched.last_below_vwap:
            logger.debug(f"[Warrior Entry] {symbol}: Below VWAP ${vwap:.2f} - ready for break")
        watched.last_below_vwap = True
        return None
    
    # VWAP BREAK: Price crosses above VWAP after being below
    if current_price >= vwap and watched.last_below_vwap:
        # Require price to be at least 5c above VWAP for confirmation
        buffer_above_vwap = Decimal("0.05")
        if current_price < vwap + buffer_above_vwap:
            return None
        
        # FALLING KNIFE FILTER: Block on fading/weak stocks
        if candles and len(candles) >= 20:
            is_falling, reason = check_falling_knife(current_price, snapshot)
            if is_falling:
                logger.info(
                    f"[Warrior Entry] {symbol}: VWAP BREAK blocked (FALLING KNIFE) - {reason}"
                )
                watched.last_below_vwap = False
                return None
        
        # VOLUME CONFIRMATION: Break bar must have volume expansion
        vol_confirmed, curr_vol, avg_vol = check_volume_confirmed(candles)
        if not vol_confirmed:
            logger.info(
                f"[Warrior Entry] {symbol}: VWAP BREAK blocked (LOW VOLUME) - "
                f"bar vol {curr_vol:,} < avg {avg_vol:,.0f}"
            )
            # Don't reset last_below_vwap - wait for volume on next bar
            return None
        
        # HIGH VOLUME RED CANDLE FILTER: Block on distribution bars
        # Ross Cameron: "high volume red candle is a red flag literally"
        is_red_flag, red_vol, red_avg = check_high_volume_red_candle(candles)
        if is_red_flag:
            logger.info(
                f"[Warrior Entry] {symbol}: VWAP BREAK blocked (HIGH VOL RED) - "
                f"red bar vol {red_vol:,} >= 1.5x avg {red_avg:,.0f}"
            )
            watched.last_below_vwap = False
            return None
        
        logger.info(
            f"[Warrior Entry] {symbol}: VWAP BREAK at ${current_price:.2f} "
            f"(VWAP=${vwap:.2f}, vol={curr_vol:,})"
        )
        # NOTE: Do NOT reset last_below_vwap here. If the entry guard rejects
        # (e.g., price is below the full-session VWAP), we want the pattern to
        # re-fire when price genuinely crosses above. Reset happens in enter_position
        # after the entry succeeds, or after guards pass.
        return EntryTriggerType.VWAP_BREAK
    
    return None


async def detect_inverted_hs_pattern(
    engine: "WarriorEngine",
    watched: "WatchedCandidate",
    current_price: Decimal,
) -> Optional[EntryTriggerType]:
    """
    Detect INVERTED HEAD & SHOULDERS pattern - Ross Cameron (Jan 28 2026): SXTP for +$1,900.
    
    Pattern: Left Shoulder → Head (lowest) → Right Shoulder → Neckline break
    Entry: When price breaks above neckline with volume confirmation.
    
    Args:
        engine: WarriorEngine instance
        watched: WatchedCandidate being evaluated
        current_price: Current stock price
        
    Returns:
        EntryTriggerType.INVERTED_HS if pattern triggers, None otherwise
    """
    symbol = watched.candidate.symbol
    
    if not (engine.config.inverted_hs_enabled and not watched.entry_triggered):
        return None
    
    if not engine._get_intraday_bars:
        return None
    
    try:
        candles = await engine._get_intraday_bars(symbol, "1min", limit=30)
        if not candles or len(candles) < 15:
            return None
        
        from nexus2.domain.indicators.pattern_service import get_pattern_service
        pattern_svc = get_pattern_service()
        
        candle_dicts = [
            {"high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
            for c in candles
        ]
        
        # Detect pattern
        pattern = pattern_svc.detect_inverted_hs(candle_dicts, lookback=20)
        
        if not pattern:
            return None
        
        watched.inverted_hs_pattern = pattern
        from datetime import datetime, timezone
        watched.inverted_hs_detected_at = datetime.now(timezone.utc)
        
        # Check for neckline breakout with volume
        if not pattern.is_breakout(current_price, buffer_cents=5):
            return None
        
        # Volume confirmation: current bar should have higher volume
        current_bar_vol = candles[-1].volume if candles else 0
        prior_bar_vol = candles[-2].volume if len(candles) >= 2 else 0
        avg_vol = sum(c.volume for c in candles[-10:]) / 10 if len(candles) >= 10 else prior_bar_vol
        
        # Require volume above average or higher than prior bar
        vol_confirmed = current_bar_vol >= avg_vol or current_bar_vol > prior_bar_vol
        
        if not vol_confirmed:
            logger.debug(
                f"[Warrior Entry] {symbol}: Inverted H&S neckline break "
                f"but volume not confirmed ({current_bar_vol:,} < avg {avg_vol:,.0f})"
            )
            return None
        
        logger.info(
            f"[Warrior Entry] {symbol}: INVERTED H&S BREAKOUT at ${current_price:.2f} "
            f"(neckline=${pattern.neckline:.2f}, head=${pattern.head_low:.2f}, "
            f"confidence={pattern.confidence:.2f}, vol={current_bar_vol:,})"
        )
        return EntryTriggerType.INVERTED_HS
        
    except Exception as e:
        logger.debug(f"[Warrior Entry] {symbol}: Inverted H&S check failed: {e}")
        return None


async def detect_cup_handle_pattern(
    engine: "WarriorEngine",
    watched: "WatchedCandidate",
    current_price: Decimal,
) -> Optional[EntryTriggerType]:
    """
    Detect CUP & HANDLE VWAP BREAK pattern - Ross Cameron (Jan 30 2026): LRHC for +$3,686.
    
    Consolidation pattern that breaks through resistance (often VWAP):
    Left rim → Cup low → Right rim → Handle pullback → Breakout
    Entry: When price breaks above handle high through VWAP.
    
    Args:
        engine: WarriorEngine instance
        watched: WatchedCandidate being evaluated
        current_price: Current stock price
        
    Returns:
        EntryTriggerType.CUP_HANDLE if pattern triggers, None otherwise
    """
    symbol = watched.candidate.symbol
    
    if not (engine.config.cup_handle_enabled and not watched.entry_triggered):
        return None
    
    if not engine._get_intraday_bars:
        return None
    
    try:
        candles = await engine._get_intraday_bars(symbol, "1min", limit=50)
        if not candles or len(candles) < 20:
            return None
        
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
        pattern = pattern_svc.detect_cup_handle(candle_dicts, vwap=vwap, lookback=40, symbol=symbol)
        
        if not pattern:
            return None
        
        watched.cup_handle_pattern = pattern
        from datetime import datetime, timezone
        watched.cup_handle_detected_at = datetime.now(timezone.utc)
        
        # Check for breakout (price breaks above handle high)
        if not pattern.is_breakout(current_price, buffer_cents=5):
            return None
        
        # Volume confirmation
        current_bar_vol = candles[-1].volume if candles else 0
        avg_vol = sum(c.volume for c in candles[-10:]) / 10 if len(candles) >= 10 else 0
        vol_confirmed = current_bar_vol >= avg_vol * 0.8
        
        if not vol_confirmed:
            logger.debug(
                f"[Warrior Entry] {symbol}: Cup & Handle breakout "
                f"but volume not confirmed ({current_bar_vol:,} < avg {avg_vol:,.0f})"
            )
            return None
        
        vwap_info = f", VWAP=${vwap:.2f}" if vwap else ""
        logger.info(
            f"[Warrior Entry] {symbol}: CUP & HANDLE BREAKOUT at ${current_price:.2f} "
            f"(cup low=${pattern.cup_low:.2f}, breakout=${pattern.breakout_level:.2f}{vwap_info}, "
            f"stop=${pattern.stop_price:.2f}, target=${pattern.target_price:.2f}, "
            f"conf={pattern.confidence:.2f})"
        )
        return EntryTriggerType.CUP_HANDLE
        
    except Exception as e:
        logger.debug(f"[Warrior Entry] {symbol}: Cup & Handle check failed: {e}")
        return None


async def detect_hod_consolidation_break(
    engine: "WarriorEngine",
    watched: "WatchedCandidate",
    current_price: Decimal,
    setup_type: Optional[str] = None,
) -> Optional[EntryTriggerType]:
    """
    Detect HOD Consolidation Break pattern — Ross Cameron's "Break of high-of-day".

    MLEC evidence (ross_mlec_20260213):
    - Bars 08:03–08:10: price consolidates $7.00–$7.90 after spike to $8.49
    - Bar 08:11: breakout — open $7.62, high $9.07, volume 554K vs ~225K avg
    - Ross entered ~$7.86–$7.97 on this HOD break

    Pattern:
    1. Find highest high across recent candles (HOD level)
    2. Identify consolidation: last 5 candles have highs within tight range below HOD
    3. Trigger: current_price > consolidation high AND volume expansion
    4. Gates: MACD >= 0, price above VWAP

    Args:
        engine: WarriorEngine instance
        watched: WatchedCandidate being evaluated
        current_price: Current stock price
        setup_type: Optional setup type filter from test case

    Returns:
        EntryTriggerType.HOD_BREAK if pattern triggers, None otherwise
    """
    symbol = watched.candidate.symbol

    # Config guard — NOTE: HOD_BREAK intentionally does NOT check entry_triggered.
    # Unlike other patterns, HOD_BREAK fires later in the session after consolidation.
    # If an earlier pattern (dip_for_level, whole_half) tried and was guard-rejected,
    # entry_triggered=True would block HOD_BREAK forever. Since HOD_BREAK is a
    # fundamentally different pattern, it should evaluate independently.
    if not engine.config.hod_break_enabled:
        return None

    # PATTERN COMPETITION: Fire when setup_type is pmh or hod_break (or unset)
    # This pattern is specifically designed for PMH cases where price hasn't reached PMH
    should_check = setup_type is None or setup_type in ("pmh", "hod_break")
    if not should_check:
        return None

    if not engine._get_intraday_bars:
        return None

    try:
        candles = await engine._get_intraday_bars(symbol, "1min", limit=30)
        if not candles or len(candles) < 10:
            return None

        # ---------------------------------------------------------------
        # Step 1: Find HOD level from PRIOR candles only (exclude current bar)
        # The current bar may BE the breakout — including it creates a paradox
        # where consol_high >= hod_level always blocks breakout bars.
        # ---------------------------------------------------------------
        prior_candles = candles[:-1]
        hod_level = max(Decimal(str(c.high)) for c in prior_candles)

        # NOTE: We do NOT check current_price >= hod_level here.
        # With 1-min bar granularity, the breakout bar's close naturally exceeds
        # prior HOD. The consolidation-below-HOD check at Step 2 validates the setup.

        # ---------------------------------------------------------------
        # Step 2: Identify consolidation in recent candles
        # ---------------------------------------------------------------
        # Use 5 candles BEFORE the current bar for consolidation detection
        consol_candles = candles[-6:-1]
        consol_highs = [Decimal(str(c.high)) for c in consol_candles]
        consol_lows = [Decimal(str(c.low)) for c in consol_candles]

        consol_high = max(consol_highs)
        consol_low = min(consol_lows)

        # Tightness check: dynamic ATR-based threshold
        # Compute ATR of consolidation candles, allow range up to 2x ATR
        consol_ranges = [
            float(Decimal(str(c.high)) - Decimal(str(c.low)))
            for c in consol_candles
        ]
        consol_atr = sum(consol_ranges) / len(consol_ranges) if consol_ranges else 0
        consol_range = float(consol_high - consol_low)
        max_allowed_range = consol_atr * 2.0

        if consol_atr <= 0:
            return None

        if consol_range > max_allowed_range:
            logger.info(
                f"[Warrior Entry] {symbol}: HOD_BREAK skip - "
                f"consolidation too wide (range=${consol_range:.2f} > "
                f"2×ATR=${max_allowed_range:.2f}, ATR=${consol_atr:.2f})"
            )
            return None

        # Consolidation must be BELOW HOD (at least 1% below)
        if consol_high >= hod_level:
            logger.info(
                f"[Warrior Entry] {symbol}: HOD_BREAK skip - "
                f"consolidation not below HOD (consol_high=${consol_high:.2f} "
                f">= HOD=${hod_level:.2f})"
            )
            return None  # Not consolidating below HOD

        gap_to_hod_pct = float((hod_level - consol_high) / hod_level * 100)
        if gap_to_hod_pct < 1.0:
            return None  # Too close to HOD — not a meaningful consolidation

        # ---------------------------------------------------------------
        # Step 3: Trigger — price breaks above consolidation high
        # ---------------------------------------------------------------
        if current_price <= consol_high:
            return None  # Not breaking out yet

        # ---------------------------------------------------------------
        # Step 4: Volume confirmation (matching cup_handle: >= 80% of 10-bar avg)
        # ---------------------------------------------------------------
        current_bar_vol = candles[-1].volume if hasattr(candles[-1], 'volume') else 0
        avg_vol = sum(c.volume for c in candles[-10:]) / 10 if len(candles) >= 10 else 0
        vol_confirmed = current_bar_vol >= avg_vol * 0.8

        if not vol_confirmed:
            logger.debug(
                f"[Warrior Entry] {symbol}: HOD_BREAK skip - "
                f"volume not confirmed ({current_bar_vol:,} < 80% of avg {avg_vol:,.0f})"
            )
            return None

        # ---------------------------------------------------------------
        # Step 5: Technical gates — MACD >= 0 and above VWAP
        # ---------------------------------------------------------------
        from nexus2.domain.indicators import get_technical_service
        tech = get_technical_service()
        candle_dicts = [
            {"high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
            for c in candles
        ]
        snapshot = tech.get_snapshot(symbol, candle_dicts, float(current_price))

        # MACD gate
        macd_val = snapshot.macd_line if snapshot.macd_line else 0
        if macd_val < 0:
            logger.debug(
                f"[Warrior Entry] {symbol}: HOD_BREAK skip - "
                f"MACD negative ({macd_val:.4f})"
            )
            return None

        # VWAP gate
        if snapshot.vwap:
            vwap = Decimal(str(snapshot.vwap))
            if current_price < vwap:
                logger.debug(
                    f"[Warrior Entry] {symbol}: HOD_BREAK skip - "
                    f"below VWAP (${current_price:.2f} < ${vwap:.2f})"
                )
                return None

        # ---------------------------------------------------------------
        # All checks passed — HOD consolidation break detected
        # ---------------------------------------------------------------
        logger.info(
            f"[Warrior Entry] {symbol}: HOD CONSOLIDATION BREAK at ${current_price:.2f} "
            f"(HOD=${hod_level:.2f}, consol_high=${consol_high:.2f}, "
            f"range=${consol_range:.2f}, ATR=${consol_atr:.2f}, gap_to_hod={gap_to_hod_pct:.1f}%, "
            f"vol={current_bar_vol:,}, MACD={macd_val:.4f})"
        )
        return EntryTriggerType.HOD_BREAK

    except Exception as e:
        logger.warning(f"[Warrior Entry] {symbol}: HOD consolidation break check failed: {e}")
        return None
