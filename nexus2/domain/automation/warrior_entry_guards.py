"""
Warrior Entry Guards

Pure extraction of entry guard logic from warrior_engine_entry.py::enter_position.
Guards check conditions that BLOCK entry (blacklist, cooldowns, max positions, etc.)

NOTE: Original functions remain in warrior_engine_entry.py.
      These are EXTRACTED COPIES for refactoring phase.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Optional, Tuple

from nexus2.domain.automation.warrior_engine_types import (
    EntryTriggerType,
    WatchedCandidate,
)
from nexus2.utils.time_utils import now_utc

if TYPE_CHECKING:
    from nexus2.domain.automation.warrior_engine import WarriorEngine


logger = logging.getLogger(__name__)


# =============================================================================
# ENTRY GUARD HELPERS
# =============================================================================


async def check_entry_guards(
    engine: "WarriorEngine",
    watched: WatchedCandidate,
    current_price: Decimal,
    trigger_type: EntryTriggerType,
) -> Tuple[bool, str]:
    """
    Check all entry guards that can BLOCK an entry.
    
    Returns (can_enter, block_reason).
    Includes: top_x picks, min score, blacklist, fail limit, MACD gate,
              position checks, pending entries, cooldowns, spread filter.
    
    Args:
        engine: The WarriorEngine instance
        watched: The watched candidate to check
        current_price: Current price (for spread/position checks)
        trigger_type: Type of entry trigger
    
    Returns:
        (True, "") if entry allowed
        (False, reason) if blocked
    """
    symbol = watched.candidate.symbol
    
    # TOP X PICKS - Ross Cameron (Jan 20 2026): "TWWG was the ONLY trade I took today"
    if engine.config.top_x_picks > 0:
        all_watched = sorted(
            engine._watchlist.values(),
            key=lambda w: w.dynamic_score,
            reverse=True
        )
        if all_watched:
            top_x_symbols = {w.candidate.symbol for w in all_watched[:engine.config.top_x_picks]}
            if watched.candidate.symbol not in top_x_symbols:
                top_pick = all_watched[0]
                our_rank = next((i+1 for i, w in enumerate(all_watched) if w.candidate.symbol == symbol), len(all_watched))
                reason = (
                    f"TOP_{engine.config.top_x_picks}_ONLY - blocked (rank={our_rank}, "
                    f"dynamic={watched.dynamic_score}) "
                    f"top pick is {top_pick.candidate.symbol} (dynamic={top_pick.dynamic_score})"
                )
                return False, reason
    
    # MIN SCORE CHECK
    candidate_score = getattr(watched.candidate, 'quality_score', 0) or 0
    if candidate_score < engine.config.min_entry_score:
        return False, f"Score {candidate_score} < min {engine.config.min_entry_score}"
    
    # BLACKLIST CHECK
    if symbol in engine.config.static_blacklist or symbol in engine._blacklist:
        return False, "Blacklisted"
    
    # PER-SYMBOL FAIL LIMIT
    symbol_fails = engine._symbol_fails.get(symbol, 0)
    if symbol_fails >= engine._max_fails_per_symbol:
        return False, f"Max fails hit - {symbol_fails} stops today (max={engine._max_fails_per_symbol})"
    
    # MACD GATE - Block ALL entries when MACD is negative
    # FAIL-CLOSED MANDATE: "Better to not trade than trade blind."
    macd_result = await _check_macd_gate(engine, watched, current_price)
    if not macd_result[0]:
        return macd_result
    
    # POSITION CHECKS (existing position, max scales, profit check)
    position_result = await _check_position_guards(engine, watched, current_price, trigger_type)
    if not position_result[0]:
        return position_result
    
    # PENDING ENTRY CHECK
    if symbol in engine._pending_entries:
        return False, "Pending buy order exists"
    
    # RE-ENTRY COOLDOWN (LIVE mode)
    if not engine.monitor.sim_mode and symbol in engine.monitor._recently_exited:
        exit_time = engine.monitor._recently_exited[symbol]
        seconds_ago = (now_utc() - exit_time).total_seconds()
        cooldown = engine.monitor._recovery_cooldown_seconds
        if seconds_ago < cooldown:
            return False, f"Re-entry cooldown - exited {seconds_ago:.0f}s ago (waiting {cooldown}s)"
    
    # SIM MODE COOLDOWN
    if engine.monitor.sim_mode and symbol in engine.monitor._recently_exited_sim_time:
        exit_sim_time = engine.monitor._recently_exited_sim_time[symbol]
        if hasattr(engine.monitor, '_sim_clock') and engine.monitor._sim_clock:
            current_sim_time = engine.monitor._sim_clock.current_time
            minutes_since_exit = (current_sim_time - exit_sim_time).total_seconds() / 60
            cooldown_minutes = engine.monitor._reentry_cooldown_minutes
            if minutes_since_exit < cooldown_minutes:
                return False, f"SIM re-entry cooldown - exited {minutes_since_exit:.1f}m ago (waiting {cooldown_minutes}m)"
    
    # SPREAD FILTER
    # Note: _check_spread_filter returns (bool, str, Optional[Decimal])
    # We extract current_ask and store on watched for limit price calculation
    spread_ok, spread_reason, current_ask = await _check_spread_filter(engine, symbol)
    if current_ask is not None:
        watched._spread_check_ask = current_ask  # Store for enter_position to use
    if not spread_ok:
        return False, spread_reason
    
    return True, ""


async def _check_macd_gate(
    engine: "WarriorEngine",
    watched: WatchedCandidate,
    entry_price: Decimal,
) -> Tuple[bool, str]:
    """
    MACD Gate: Block entries when MACD is negative.
    
    FAIL-CLOSED: If we cannot verify technicals, BLOCK the trade.
    
    Returns:
        (True, "") if MACD OK
        (False, reason) if blocked
    """
    symbol = watched.candidate.symbol
    
    if not engine._get_intraday_bars:
        return False, "FAIL-CLOSED - no intraday bar callback available. Cannot verify MACD/technicals."
    
    try:
        candles = await engine._get_intraday_bars(symbol, "1min", limit=50)
        
        # FAIL-CLOSED: Block if bar data is missing or insufficient
        if not candles or len(candles) < 10:
            bar_count = len(candles) if candles else 0
            return False, f"FAIL-CLOSED - insufficient bar data ({bar_count} bars, need 10+). Cannot verify MACD/technicals."
        
        from nexus2.domain.indicators import get_technical_service
        tech = get_technical_service()
        candle_dicts = [
            {"high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
            for c in candles
        ]
        snapshot = tech.get_snapshot(symbol, candle_dicts, entry_price)
        
        if not snapshot.is_macd_bullish:
            reason = (
                f"MACD GATE - blocking entry "
                f"(histogram={f'{snapshot.macd_histogram:.4f}' if snapshot.macd_histogram else 'N/A'}, "
                f"crossover={snapshot.macd_crossover}) - Ross rule: no entry when MACD negative"
            )
            return False, reason
        
        # CRITICAL: Store snapshot for audit logging
        watched.entry_snapshot = snapshot
        logger.info(
            f"[Warrior Entry] {symbol}: MACD OK for entry "
            f"(histogram={f'{snapshot.macd_histogram:.4f}' if snapshot.macd_histogram else 'N/A'})"
        )
        return True, ""
        
    except Exception as e:
        return False, f"FAIL-CLOSED - MACD check failed: {e}. Cannot verify momentum."


async def _check_position_guards(
    engine: "WarriorEngine",
    watched: WatchedCandidate,
    entry_price: Decimal,
    trigger_type: EntryTriggerType,
) -> Tuple[bool, str]:
    """
    Check position-related guards: max scales, profit check, existing positions.
    
    Returns:
        (True, "") if can proceed
        (False, reason) if blocked
    """
    symbol = watched.candidate.symbol
    
    # FIRST: Check MONITOR positions for max_scale enforcement
    from nexus2.domain.automation.warrior_monitor import get_warrior_monitor
    monitor = get_warrior_monitor()
    for pos in monitor.get_positions():
        if pos.symbol == symbol:
            max_scales = monitor.settings.max_scale_count
            if pos.scale_count >= max_scales:
                return False, f"BLOCKED - already at max scale #{pos.scale_count} (limit={max_scales})"
            
            # PROFIT-CHECK GUARD: Block adds when position is past profit target
            unrealized_pnl_pct = ((entry_price - pos.entry_price) / pos.entry_price) * 100
            profit_target = pos.profit_target or Decimal("0")
            price_past_target = profit_target > 0 and entry_price >= profit_target
            pnl_above_threshold = unrealized_pnl_pct > 25  # 25% gain threshold
            
            if price_past_target or pnl_above_threshold:
                reason = (
                    f"past target ${profit_target:.2f}" if price_past_target
                    else f"+{unrealized_pnl_pct:.1f}% unrealized"
                )
                return False, f"BLOCKING {trigger_type.name} - position already {reason}. Take profit first."
            
            break
    
    # SECOND: Check BROKER positions for double-buy prevention
    if engine._get_positions:
        try:
            positions = await engine._get_positions()
            held_symbols = {p.get("symbol") or p.symbol for p in positions if p}
            if symbol in held_symbols:
                if trigger_type == EntryTriggerType.MICRO_PULLBACK:
                    # MICRO_PULLBACK: Allow scale-in (handled separately)
                    return True, "scale_into_existing"
                else:
                    return False, "Already holding position"
        except Exception as e:
            logger.warning(f"[Warrior Entry] {symbol}: Position check failed: {e}")
    
    return True, ""


async def _check_spread_filter(
    engine: "WarriorEngine",
    symbol: str,
) -> Tuple[bool, str, Optional[Decimal]]:
    """
    Check bid-ask spread for entry suitability.
    
    Returns:
        (True, "", current_ask) if spread OK
        (False, reason, None) if blocked
    """
    current_ask = None
    
    if not (engine._get_quote_with_spread and engine.config.max_entry_spread_percent > 0):
        return True, "", None
    
    try:
        spread_data = await engine._get_quote_with_spread(symbol)
        if spread_data:
            bid = spread_data.get("bid", 0)
            ask = spread_data.get("ask", 0)
            
            if bid > 0 and ask > 0:
                current_ask = Decimal(str(ask))
                spread_percent = ((ask - bid) / bid) * 100
                
                if spread_percent > engine.config.max_entry_spread_percent:
                    reason = (
                        f"REJECTED - spread {spread_percent:.1f}% > "
                        f"{engine.config.max_entry_spread_percent}% threshold "
                        f"(bid=${bid:.2f}, ask=${ask:.2f})"
                    )
                    return False, reason, None
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
    
    return True, "", current_ask


# =============================================================================
# TECHNICAL VALIDATION (VWAP/EMA Gates)
# =============================================================================


async def validate_technicals(
    engine: "WarriorEngine",
    watched: WatchedCandidate,
    entry_price: Decimal,
) -> Tuple[bool, Optional[str]]:
    """
    Validate technical conditions for entry (VWAP/EMA alignment).
    
    Technical Validation per Ross Cameron:
    - Entry should be above VWAP
    - Entry should be above 9 EMA (within 1% tolerance)
    
    Args:
        engine: The WarriorEngine instance
        watched: The watched candidate to validate
        entry_price: Proposed entry price
    
    Returns:
        (True, None) if technicals OK
        (False, rejection_reason) if failed
    """
    symbol = watched.candidate.symbol
    
    if not engine._get_intraday_bars:
        # Cannot validate - proceed with caution
        return True, None
    
    try:
        # Use shared session VWAP (same calculation as pattern detector)
        from nexus2.domain.automation.warrior_vwap_utils import get_session_vwap
        actual_vwap = await get_session_vwap(engine, symbol, float(entry_price))
        
        # Fetch candles for EMA/MACD (needs continuity bars for warm-up)
        candles = await engine._get_intraday_bars(symbol, "1min", limit=50)
        if not candles or len(candles) < 10:
            # Not enough data - proceed with VWAP check only
            if actual_vwap and entry_price < actual_vwap:
                reason = (
                    f"REJECTED - below VWAP "
                    f"(${entry_price:.2f} < VWAP ${actual_vwap:.2f})"
                )
                logger.warning(f"[Warrior Entry] {symbol}: {reason}")
                return False, reason
            return True, None
        
        from nexus2.domain.indicators import get_technical_service
        tech = get_technical_service()
        
        # Use ALL candles for MACD/EMA (needs continuity for warm-up)
        all_candle_dicts = [
            {"high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
            for c in candles
        ]
        
        # Get MACD/EMA from all bars (includes continuity)
        snapshot = tech.get_snapshot(symbol, all_candle_dicts, entry_price)
        
        # Check: price should be above VWAP (Ross Cameron rule)
        # Uses shared session VWAP for consistency with pattern detector
        if actual_vwap and entry_price < actual_vwap:
            reason = (
                f"REJECTED - below VWAP "
                f"(${entry_price:.2f} < VWAP ${actual_vwap:.2f})"
            )
            logger.warning(f"[Warrior Entry] {symbol}: {reason}")
            # NOTE: Do NOT set entry_triggered=True here - VWAP is a temporary condition
            # that can change. We want to re-check on next tick if price moves above VWAP.
            return False, reason
        
        # Check: price should be above 9 EMA (within 1% tolerance)
        if snapshot.ema_9 and entry_price < snapshot.ema_9 * Decimal("0.99"):
            reason = (
                f"REJECTED - below 9 EMA "
                f"(${entry_price:.2f} < 9EMA ${snapshot.ema_9:.2f})"
            )
            logger.warning(f"[Warrior Entry] {symbol}: {reason}")
            # NOTE: Do NOT set entry_triggered=True here - 9 EMA is a temporary condition
            return False, reason
        
        # Log technical confirmation
        logger.info(
            f"[Warrior Entry] {symbol}: Technical OK - "
            f"VWAP=${f'{actual_vwap:.2f}' if actual_vwap else 'N/A'}, "
            f"9EMA=${f'{snapshot.ema_9:.2f}' if snapshot.ema_9 else 'N/A'}, "
            f"MACD={snapshot.macd_crossover}"
        )
        
        return True, None
        
    except Exception as e:
        # FAIL-CLOSED: Cannot verify technicals - block entry
        reason = f"FAIL-CLOSED - Technical check failed: {e}. Cannot verify VWAP/EMA/MACD, blocking entry."
        logger.warning(f"[Warrior Entry] {symbol}: {reason}")
        watched.entry_triggered = True  # Mark as triggered to prevent retries
        return False, reason
