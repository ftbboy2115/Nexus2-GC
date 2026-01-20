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
            
            # PMH breakout
            if engine.config.pmh_enabled:
                trigger_price = watched.pmh + engine.config.pmh_buffer_cents / 100
                if current_price >= trigger_price:
                    logger.info(f"[Warrior Entry] {symbol}: PMH BREAKOUT at ${current_price}")
                    await enter_position(
                        engine, 
                        watched, 
                        current_price, 
                        EntryTriggerType.PMH_BREAK
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
    if engine.config.top_pick_only:
        # Get all watched candidates sorted by score
        all_watched = list(engine._watchlist.values())
        if all_watched:
            # Find the top scorer (by candidate quality score)
            top_pick = max(all_watched, key=lambda w: getattr(w.candidate, 'quality_score', 0) or 0)
            if watched.candidate.symbol != top_pick.candidate.symbol:
                # Not the top pick - skip silently (avoid log spam)
                return
    
    # MIN SCORE CHECK - Require minimum quality score for entry
    candidate_score = getattr(watched.candidate, 'quality_score', 0) or 0
    if candidate_score < engine.config.min_entry_score:
        logger.info(
            f"[Warrior Entry] {symbol}: Score {candidate_score} < min {engine.config.min_entry_score}, skipping"
        )
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
    
    # ROSS RE-ENTRY MACD GATE: Block re-entry when MACD is negative
    # Per Ross Cameron: "Because MACD was negative, it was taking too much risk"
    # Only applies to re-entries (entry_attempt_count > 0), not first entry
    if watched.entry_attempt_count > 0 and engine._get_intraday_bars:
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
                        f"[Warrior Entry] {symbol}: MACD GATE - blocking re-entry "
                        f"(histogram={snapshot.macd_histogram:.4f if snapshot.macd_histogram else 'N/A'}, "
                        f"crossover={snapshot.macd_crossover}) - Ross rule: no re-entry when MACD negative"
                    )
                    watched.entry_triggered = True  # Block this attempt
                    return
                else:
                    logger.info(
                        f"[Warrior Entry] {symbol}: MACD OK for re-entry "
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
    if symbol in engine.monitor._recently_exited:
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
    
    if engine._get_intraday_bars:
        try:
            candles = await engine._get_intraday_bars(symbol, "1min", limit=5)
            if candles and len(candles) >= 1:
                # Ross method: Use low of the current/entry candle with 2¢ buffer
                entry_candle = candles[-1]  # Most recent candle (entry candle)
                entry_candle_low = Decimal(str(entry_candle.low))
                
                # Add 2¢ buffer below the low
                mental_stop = entry_candle_low - Decimal("0.02")
                stop_method = "candle_low"
                
                logger.info(
                    f"[Warrior Entry] {symbol}: Stop ${mental_stop:.2f} via {stop_method} "
                    f"(candle low=${entry_candle_low:.2f} - 2¢)"
                )
        except Exception as e:
            logger.debug(f"[Warrior Entry] {symbol}: Entry candle stop calc failed: {e}")
    
    if mental_stop is None:
        mental_stop = entry_price - engine.monitor.settings.mental_stop_cents / 100
        stop_method = "fallback_15c"
    
    risk_per_share = entry_price - mental_stop
    
    if risk_per_share <= 0:
        logger.warning(f"[Warrior Entry] {symbol}: Invalid risk calculation")
        return
    
    shares = int(engine.config.risk_per_trade / risk_per_share)
    
    # Cap by max capital
    max_shares = int(engine.config.max_capital / entry_price)
    shares = min(shares, max_shares)
    
    # Apply testing limits
    if engine.config.max_shares_per_trade is not None:
        shares = min(shares, engine.config.max_shares_per_trade)
    if engine.config.max_value_per_trade is not None:
        max_by_value = int(engine.config.max_value_per_trade / entry_price)
        shares = min(shares, max_by_value)
    
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
        limit_price = (entry_price * fallback_multiplier).quantize(Decimal("0.01"))
        logger.info(f"[Warrior Entry] {symbol}: Limit based on entry ${entry_price:.2f} x 1.015 = ${limit_price:.2f} (no bid/ask)")
    
    # Mark pending entry BEFORE submitting order (prevents duplicate entries on restart)
    engine._pending_entries[symbol] = now_utc()
    engine._save_pending_entries()
    logger.info(f"[Warrior Entry] {symbol}: Marked pending entry")
    
    if engine._submit_order:
        try:
            order_result = await engine._submit_order(
                symbol=symbol,
                shares=shares,
                side="buy",
                order_type="limit",  # Limit order, not market
                limit_price=float(limit_price),  # offset above ask
                stop_loss=None,  # Mental stop, not broker stop
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
                order_status = str(order_result.status)
                filled_qty = getattr(order_result, 'filled_qty', 0) or 0
            elif isinstance(order_result, dict):
                order_status = order_result.get("status")
                filled_qty = order_result.get("filled_qty", 0) or 0
            
            # If order is not filled yet, skip monitor add - auto-recovery will handle it
            if order_status and order_status.lower() not in ("filled", "partially_filled"):
                logger.info(
                    f"[Warrior Entry] {symbol}: Order pending (status={order_status}) - "
                    f"auto-recovery will sync when filled"
                )
                return
            
            # CRITICAL: Use ACTUAL fill price from Alpaca, not intended entry
            # This prevents immediate stop-outs when market price differs from quote
            actual_fill_price = entry_price  # Default to intended price
            slippage_cents = Decimal("0")  # Track slippage
            
            if hasattr(order_result, 'filled_avg_price') and order_result.filled_avg_price:
                actual_fill_price = Decimal(str(order_result.filled_avg_price))
                slippage_cents = (actual_fill_price - entry_price) * 100  # In cents
                if slippage_cents != 0:
                    slippage_bps = (actual_fill_price / entry_price - 1) * 10000  # Basis points
                    logger.info(
                        f"[Warrior Slippage] {symbol}: Fill ${actual_fill_price:.2f} vs "
                        f"intended ${entry_price:.2f} = {slippage_cents:+.1f}¢ ({slippage_bps:+.1f}bps)"
                    )
            elif isinstance(order_result, dict) and order_result.get("filled_avg_price"):
                actual_fill_price = Decimal(str(order_result["filled_avg_price"]))
                slippage_cents = (actual_fill_price - entry_price) * 100
                if slippage_cents != 0:
                    slippage_bps = (actual_fill_price / entry_price - 1) * 10000
                    logger.info(
                        f"[Warrior Slippage] {symbol}: Fill ${actual_fill_price:.2f} vs "
                        f"intended ${entry_price:.2f} = {slippage_cents:+.1f}¢ ({slippage_bps:+.1f}bps)"
                    )
            
            # Recalculate stop based on actual fill price
            actual_stop = actual_fill_price - engine.monitor.settings.mental_stop_cents / 100
            
            engine.monitor.add_position(
                position_id=order_id,
                symbol=symbol,
                entry_price=actual_fill_price,  # Use ACTUAL fill price
                shares=int(filled_qty) if filled_qty else shares,  # Use actual filled qty
                support_level=support_level,
                trigger_type=trigger_type.value,  # PMH_BREAK, ORB
            )
            
            # Log to Warrior DB for restart recovery
            try:
                from nexus2.db.warrior_db import log_warrior_entry, set_entry_order_id
                mental_stop_cents = Decimal(str(engine.monitor.settings.mental_stop_cents))
                profit_target_r = Decimal(str(engine.monitor.settings.profit_target_r))
                target = actual_fill_price + (mental_stop_cents / 100 * profit_target_r)
                log_warrior_entry(
                    trade_id=order_id,
                    symbol=symbol,
                    entry_price=float(actual_fill_price),  # Use actual fill
                    quantity=shares,
                    stop_price=float(actual_stop),  # Use recalculated stop
                    target_price=float(target),
                    trigger_type=trigger_type.value,
                    support_level=float(support_level),
                    stop_method=stop_method,
                )
                # Store broker order ID for sync recovery after restart
                set_entry_order_id(order_id, order_id)
                logger.debug(f"[Warrior Entry] {symbol}: Linked position {order_id[:8]}... to broker order")
            except Exception as e:
                logger.warning(f"[Warrior Entry] DB log failed: {e}")
            
            logger.info(
                f"[Warrior Entry] {symbol}: Bought {shares} shares @ ${actual_fill_price} "
                f"({trigger_type.value})"
            )
            
            # Clear pending entry on successful fill
            engine.clear_pending_entry(symbol)
            
        except Exception as e:
            logger.error(f"[Warrior Entry] {symbol}: Order failed: {e}")
            engine.stats.last_error = str(e)
            # Clear pending entry on failure (allow retry)
            engine.clear_pending_entry(symbol)
    else:
        logger.warning(f"[Warrior Entry] {symbol}: No submit_order callback")
