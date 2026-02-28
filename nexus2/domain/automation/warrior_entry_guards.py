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
    from nexus2.domain.automation.trade_event_service import trade_event_service as tml
    _trigger = trigger_type.value
    _price = float(current_price)
    
    # Derive blocked_time (HH:MM ET) for counterfactual analysis
    et_now = engine._get_eastern_time()
    _btime = et_now.strftime("%H:%M") if et_now else None
    
    # =========================================================================
    # EOD ENTRY CUTOFF — block ALL new entries past cutoff time (Feb 27 fix)
    # This guard is NON-SKIPPABLE even in A/B test mode (safety critical)
    # =========================================================================
    current_time = et_now.time() if et_now else None
    if current_time is not None:
        # Hard cutoff: no entries after eod_entry_cutoff_time (default 7 PM ET)
        try:
            h, m = map(int, engine.monitor.settings.eod_entry_cutoff_time.split(":"))
            from datetime import time as dt_time
            cutoff = dt_time(h, m)
            if current_time >= cutoff:
                reason = f"EoD entry cutoff: {current_time.strftime('%H:%M')} past {engine.monitor.settings.eod_entry_cutoff_time} ET"
                tml.log_warrior_guard_block(symbol, "eod_cutoff", reason, _trigger, _price, _btime)
                return False, reason
        except (ValueError, AttributeError) as e:
            logger.warning(f"[Warrior Guards] Failed to parse eod_entry_cutoff_time: {e}")
    
    # PHASE 1: Skip all guards for A/B comparison testing (SIM ONLY)
    if getattr(engine, 'skip_guards', False):
        assert engine.monitor.sim_mode, "skip_guards only allowed in simulation"
        logger.info(f"[Warrior Guards] {symbol}: ALL GUARDS SKIPPED (A/B test mode)")
        return True, ""
    
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
                tml.log_warrior_guard_block(symbol, "top_x", reason, _trigger, _price, _btime)
                return False, reason
    
    # MIN SCORE CHECK
    candidate_score = getattr(watched.candidate, 'quality_score', 0) or 0
    if candidate_score < engine.config.min_entry_score:
        tml.log_warrior_guard_block(symbol, "min_score", f"Score {candidate_score} < min {engine.config.min_entry_score}", _trigger, _price, _btime)
        return False, f"Score {candidate_score} < min {engine.config.min_entry_score}"
    
    # BLACKLIST CHECK
    if symbol in engine.config.static_blacklist or symbol in engine._blacklist:
        tml.log_warrior_guard_block(symbol, "blacklist", "Blacklisted", _trigger, _price, _btime)
        return False, "Blacklisted"
    
    # PER-SYMBOL FAIL LIMIT
    symbol_fails = engine._symbol_fails.get(symbol, 0)
    if symbol_fails >= engine._max_fails_per_symbol:
        reason = f"Max fails hit - {symbol_fails} stops today (max={engine._max_fails_per_symbol})"
        tml.log_warrior_guard_block(symbol, "fail_limit", reason, _trigger, _price, _btime)
        return False, reason
    
    # MACD GATE - Block ALL entries when MACD is negative
    # FAIL-CLOSED MANDATE: "Better to not trade than trade blind."
    macd_result = await _check_macd_gate(engine, watched, current_price)
    if not macd_result[0]:
        tml.log_warrior_guard_block(symbol, "macd", macd_result[1], _trigger, _price, _btime)
        return macd_result
    
    # POSITION CHECKS (existing position, max scales, profit check)
    position_result = await _check_position_guards(engine, watched, current_price, trigger_type)
    if not position_result[0]:
        tml.log_warrior_guard_block(symbol, "position", position_result[1], _trigger, _price, _btime)
        return position_result
    
    # PENDING ENTRY CHECK
    if symbol in engine._pending_entries:
        tml.log_warrior_guard_block(symbol, "pending_entry", "Pending buy order exists", _trigger, _price, _btime)
        return False, "Pending buy order exists"
    
    # RE-ENTRY COOLDOWN (LIVE mode)
    if not engine.monitor.sim_mode and symbol in engine.monitor._recently_exited:
        exit_time = engine.monitor._recently_exited[symbol]
        seconds_ago = (now_utc() - exit_time).total_seconds()
        cooldown = engine.monitor._recovery_cooldown_seconds
        if seconds_ago < cooldown:
            reason = f"Re-entry cooldown - exited {seconds_ago:.0f}s ago (waiting {cooldown}s)"
            tml.log_warrior_guard_block(symbol, "live_cooldown", reason, _trigger, _price, _btime)
            return False, reason
    
    # SIM MODE COOLDOWN
    if engine.monitor.sim_mode and symbol in engine.monitor._recently_exited_sim_time:
        exit_sim_time = engine.monitor._recently_exited_sim_time[symbol]
        if hasattr(engine.monitor, '_sim_clock') and engine.monitor._sim_clock:
            current_sim_time = engine.monitor._sim_clock.current_time
            minutes_since_exit = (current_sim_time - exit_sim_time).total_seconds() / 60
            cooldown_minutes = engine.monitor._reentry_cooldown_minutes
            if minutes_since_exit < cooldown_minutes:
                reason = f"SIM re-entry cooldown - exited {minutes_since_exit:.1f}m ago (waiting {cooldown_minutes}m)"
                tml.log_warrior_guard_block(symbol, "sim_cooldown", reason, _trigger, _price, _btime)
                return False, reason
    
    # RE-ENTRY QUALITY GATE: Block re-entry after consecutive losses (Ross: 3-5 trades max per symbol)
    # Graduated policy: allow N consecutive losses before blocking. Resets on profit exit.
    if watched.entry_attempt_count > 0 and engine.monitor.settings.block_reentry_after_loss:
        max_attempts = engine.monitor.settings.max_reentry_after_loss  # Default: 3
        consecutive_losses = watched.consecutive_loss_count
        if consecutive_losses >= max_attempts:
            reason = f"Re-entry BLOCKED after {consecutive_losses} consecutive losses (max={max_attempts}) - Ross gives up after 2+ failures"
            tml.log_warrior_guard_block(symbol, "reentry_loss", reason, _trigger, _price, _btime)
            return False, reason
    
    # SPREAD FILTER
    # Note: _check_spread_filter returns (bool, str, Optional[Decimal])
    # We extract current_ask and store on watched for limit price calculation
    spread_ok, spread_reason, current_ask = await _check_spread_filter(engine, symbol)
    if current_ask is not None:
        watched._spread_check_ask = current_ask  # Store for enter_position to use
    if not spread_ok:
        tml.log_warrior_guard_block(symbol, "spread", spread_reason, _trigger, _price, _btime)
        return False, spread_reason
    
    # L2 ENTRY GATE — order book check (ask walls + spread quality)
    l2_result = _check_l2_gate(engine, symbol, current_price)
    if not l2_result[0]:
        tml.log_warrior_guard_block(symbol, "l2_gate", l2_result[1], _trigger, _price, _btime)
        return l2_result
    
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
        
        # TOLERANCE-BASED MACD CHECK (Feb 24, 2026):
        # Ross uses MACD as "confirmation only" — slightly negative histogram
        # during a pullback doesn't disqualify an entry. Only block when MACD
        # is meaningfully negative (below tolerance threshold).
        histogram = snapshot.macd_histogram or 0
        tolerance = engine.config.macd_histogram_tolerance  # default -0.02
        
        if histogram < tolerance and snapshot.macd_crossover != "bullish":
            reason = (
                f"MACD GATE - blocking entry "
                f"(histogram={histogram:.4f} < tolerance={tolerance}, "
                f"crossover={snapshot.macd_crossover}) - MACD too negative for entry"
            )
            return False, reason
        
        # If histogram is between tolerance and 0, allow with info log
        if histogram < 0:
            logger.info(
                f"[Warrior Entry] {symbol}: MACD slightly negative but within tolerance "
                f"(histogram={histogram:.4f}, tolerance={tolerance}) - allowing entry"
            )
        
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
    # NOTE: Must use engine.monitor, NOT get_warrior_monitor() singleton,
    # because the concurrent runner uses a per-case engine with its own monitor.
    monitor = engine.monitor
    for pos in monitor.get_positions():
        if pos.symbol == symbol:
            max_scales = monitor.settings.max_scale_count
            if pos.scale_count >= max_scales:
                return False, f"BLOCKED - already at max scale #{pos.scale_count} (limit={max_scales})"
            
            # 25% profit-check guard (toggleable for A/B testing via GC param sweep)
            # Default OFF — Ross adds on strength well past 25% gain.
            # Setting enable_profit_check_guard=True restores old blocking behavior.
            if monitor.settings.enable_profit_check_guard:
                unrealized_pnl_pct = ((entry_price - pos.entry_price) / pos.entry_price) * 100
                price_past_target = pos.profit_target and entry_price > pos.profit_target
                pnl_above_threshold = unrealized_pnl_pct > 25
                if price_past_target or pnl_above_threshold:
                    return False, "BLOCKING - position already past target/25% gain. Take profit first."
            
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
    
    Includes progressive EoD spread gates (Feb 27 fix):
    - Phase 1 (4-6 PM): max eod_phase1_max_spread_pct (default 2%)
    - Phase 2 (6-7 PM): max eod_phase2_max_spread_pct (default 1%)
    
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
                
                # Normal spread check (config.max_entry_spread_percent)
                if spread_percent > engine.config.max_entry_spread_percent:
                    reason = (
                        f"REJECTED - spread {spread_percent:.1f}% > "
                        f"{engine.config.max_entry_spread_percent}% threshold "
                        f"(bid=${bid:.2f}, ask=${ask:.2f})"
                    )
                    return False, reason, None
                
                # Progressive EoD spread gates (Feb 27 fix)
                # Tighten spread requirements as post-market deepens
                try:
                    from datetime import time as dt_time
                    et_now = engine._get_eastern_time()
                    current_time = et_now.time() if et_now else None
                    if current_time is not None:
                        phase2_start = dt_time(18, 0)  # 6 PM
                        phase1_start = dt_time(16, 0)  # 4 PM
                        
                        eod_limit = None
                        phase_label = ""
                        if current_time >= phase2_start:
                            eod_limit = engine.monitor.settings.eod_phase2_max_spread_pct
                            phase_label = "phase2 (6-7 PM)"
                        elif current_time >= phase1_start:
                            eod_limit = engine.monitor.settings.eod_phase1_max_spread_pct
                            phase_label = "phase1 (4-6 PM)"
                        
                        if eod_limit is not None and spread_percent > eod_limit:
                            reason = (
                                f"EoD spread gate ({phase_label}): spread {spread_percent:.1f}% > "
                                f"max {eod_limit}% (bid=${bid:.2f}, ask=${ask:.2f})"
                            )
                            return False, reason, None
                except Exception as e:
                    logger.debug(f"[Warrior Entry] {symbol}: EoD spread check skipped: {e}")
                
                logger.debug(
                    f"[Warrior Entry] {symbol}: Spread OK {spread_percent:.1f}% "
                    f"(max={engine.config.max_entry_spread_percent}%)"
                )
            elif bid <= 0 or ask <= 0:
                # FAIL-CLOSED (Phase 11 A1 fix): block entry on invalid bid/ask
                logger.warning(
                    f"[Warrior Entry] {symbol}: No valid bid/ask data "
                    f"(bid=${bid}, ask=${ask}) - BLOCKING entry (fail-closed)"
                )
                return False, f"Invalid bid/ask data (bid=${bid}, ask=${ask})", None
    except Exception as e:
        # FAIL-CLOSED (Phase 11 A1 fix): block entry on spread check failure
        logger.warning(f"[Warrior Entry] {symbol}: Spread check failed: {e} - BLOCKING entry (fail-closed)")
        return False, f"Spread check error: {e}", None
    
    return True, "", current_ask


def _check_l2_gate(
    engine: "WarriorEngine",
    symbol: str,
    entry_price: Decimal,
) -> Tuple[bool, str]:
    """
    L2 order book gate. Checks for ask walls and spread quality.
    
    FAIL-OPEN: If L2 data unavailable, ALWAYS allow entry.
    
    Modes (from monitor settings):
        log_only: Log L2 conditions but never block (default)
        warn: Log WARNING but still allow entry
        block: Actually reject the entry
    
    Returns:
        (True, "") if entry allowed
        (False, reason) if blocked (only in 'block' mode)
    """
    try:
        from nexus2 import config as app_config

        # FAIL-OPEN: L2 disabled or no streamer → allow
        if not app_config.L2_ENABLED:
            return True, ""

        streamer = getattr(engine, "_l2_streamer", None)
        if streamer is None:
            return True, ""

        # Get snapshot — no data → allow
        snapshot = streamer.get_snapshot(symbol)
        if snapshot is None:
            logger.debug(f"[L2 Gate] {symbol}: No L2 snapshot available — allowing entry")
            return True, ""

        # Read settings from monitor
        settings = engine.monitor.settings
        mode = getattr(settings, "l2_gate_mode", "log_only")
        wall_threshold = getattr(settings, "l2_wall_threshold_volume", 10000)
        proximity_pct = getattr(settings, "l2_wall_proximity_pct", 1.0)

        # Lazy import signal functions
        from nexus2.domain.market_data.l2_signals import detect_ask_wall, get_spread_quality

        # Check 1: Ask wall within proximity of entry price
        ask_wall = detect_ask_wall(snapshot, threshold_volume=wall_threshold)
        wall_triggered = False
        wall_msg = ""
        if ask_wall is not None:
            max_wall_price = entry_price * (1 + Decimal(str(proximity_pct)) / 100)
            if ask_wall.price <= max_wall_price:
                wall_triggered = True
                wall_msg = (
                    f"ask wall {ask_wall.volume:,} shares at ${float(ask_wall.price):.2f} "
                    f"(within {proximity_pct}% of entry ${float(entry_price):.2f})"
                )

        # Check 2: Spread quality
        spread_q = get_spread_quality(snapshot)
        wide_spread = spread_q.quality == "wide"

        # Build assessment log
        assessment_parts = []
        if wall_triggered:
            assessment_parts.append(f"ASK_WALL: {wall_msg}")
        if wide_spread:
            assessment_parts.append(
                f"WIDE_SPREAD: {spread_q.spread_bps:.1f} bps "
                f"(bid_depth={spread_q.bid_depth}, ask_depth={spread_q.ask_depth})"
            )
        if not assessment_parts:
            assessment_parts.append("OK")
            if ask_wall:
                assessment_parts.append(
                    f"(wall at ${float(ask_wall.price):.2f} outside proximity)"
                )

        assessment = "; ".join(assessment_parts)
        triggered = wall_triggered  # Wide spread alone doesn't block, just logged

        # Mode-based behavior
        if mode == "log_only":
            logger.info(f"[L2 Gate] {symbol}: {assessment} [mode=log_only]")
            return True, ""
        elif mode == "warn":
            if triggered:
                logger.warning(f"[L2 Gate] {symbol}: {assessment} [mode=warn — allowing entry]")
            else:
                logger.info(f"[L2 Gate] {symbol}: {assessment} [mode=warn]")
            return True, ""
        elif mode == "block":
            if triggered:
                reason = f"L2 gate: {wall_msg}"
                logger.warning(f"[L2 Gate] {symbol}: BLOCKING — {reason}")
                return False, reason
            else:
                logger.info(f"[L2 Gate] {symbol}: {assessment} [mode=block — passing]")
                return True, ""
        else:
            # Unknown mode — treat as log_only
            logger.info(f"[L2 Gate] {symbol}: {assessment} [mode={mode} — unknown, treating as log_only]")
            return True, ""

    except Exception as e:
        # FAIL-OPEN: L2 errors must never block trades
        logger.warning(f"[L2 Gate] {symbol}: Error — {e}. Allowing entry (fail-open).")
        return True, ""


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
    
    # PHASE 1: Skip technical validation for A/B comparison testing (SIM ONLY)
    if getattr(engine, 'skip_guards', False):
        assert engine.monitor.sim_mode, "skip_guards only allowed in simulation"
        logger.info(f"[Warrior Technicals] {symbol}: VALIDATION SKIPPED (A/B test mode)")
        return True, None
    
    if not engine._get_intraday_bars:
        # Cannot validate - proceed with caution
        return True, None
    
    try:
        candles = await engine._get_intraday_bars(symbol, "1min", limit=50)
        if not candles or len(candles) < 10:
            # FAIL-CLOSED: Cannot verify VWAP/EMA with insufficient data
            reason = f"FAIL-CLOSED - Only {len(candles) if candles else 0} candles available (need 10+). Cannot validate technicals."
            logger.warning(f"[Warrior Entry] {symbol}: {reason}")
            return False, reason
        
        from nexus2.domain.indicators import get_technical_service
        tech = get_technical_service()
        
        # CRITICAL FIX (Feb 1 2026): Filter out continuity bars for VWAP
        # Continuity bars from previous day EOD (15:00-16:00) distort VWAP
        # VWAP should only use TODAY's session bars
        from nexus2.domain.automation.warrior_vwap_utils import _get_current_hour
        current_hour = _get_current_hour(engine)
        
        # Filter for today's session bars only (VWAP calculation)
        today_candles = []
        for c in candles:
            bar_time = getattr(c, 'time', '') or ''
            if not bar_time:
                continue
            try:
                hour = int(bar_time.split(':')[0])
                if current_hour is not None:
                    if current_hour < 10:  # Premarket
                        if 4 <= hour < 10:
                            today_candles.append(c)
                    else:  # Regular hours
                        if 4 <= hour <= current_hour:
                            today_candles.append(c)
                else:
                    if 4 <= hour < 10:
                        today_candles.append(c)
            except (ValueError, IndexError):
                today_candles.append(c)
        
        # Use filtered candles for VWAP
        vwap_candle_dicts = [
            {"high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
            for c in today_candles
        ] if today_candles else []
        
        # Use ALL candles for MACD/EMA (needs continuity for warm-up)
        all_candle_dicts = [
            {"high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
            for c in candles
        ]
        
        # Get VWAP from today's bars only
        vwap_snapshot = tech.get_snapshot(symbol, vwap_candle_dicts, entry_price) if vwap_candle_dicts else None
        # Get MACD/EMA from all bars (includes continuity)
        snapshot = tech.get_snapshot(symbol, all_candle_dicts, entry_price)
        
        # Check: price should be above VWAP (Ross Cameron rule)
        # Use vwap_snapshot (today's bars only) for accurate session VWAP
        actual_vwap = vwap_snapshot.vwap if vwap_snapshot else snapshot.vwap
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
