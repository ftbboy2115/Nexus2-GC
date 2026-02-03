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
    check_volume_expansion,
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
                activity_candles = await engine._get_intraday_bars(symbol, "1min", limit=10)
            
            logger.info(
                f"[Warrior Entry] {symbol}: DIP-FOR-LEVEL active market check - "
                f"got {len(activity_candles) if activity_candles else 0} candles"
            )
            
            if activity_candles:
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
            activity_candles = await engine._get_intraday_bars(symbol, "1min", limit=10)
            logger.info(
                f"[Warrior Entry] {symbol}: Active market check - got {len(activity_candles) if activity_candles else 0} candles"
            )
            if activity_candles:
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
