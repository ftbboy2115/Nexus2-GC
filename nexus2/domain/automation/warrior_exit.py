"""
Warrior Exit Module

Handles position evaluation and exit execution for Warrior Trading positions.
Extracted from warrior_monitor.py for improved modularity.

Ross Cameron Exit Rules:
1. Mental stop (10-20 cents) - no broker stop visible to HFT
2. Technical stop (support - 2-5 cents)
3. Candle-under-candle (new low)
4. Topping tail (rejection at highs)
5. 2:1 R profit target -> 50% partial, move stop to breakeven
6. After-hours exit (prevent overnight holds)
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from nexus2.utils.time_utils import now_utc
from nexus2.domain.automation.warrior_types import (
    WarriorExitReason,
    WarriorExitSignal,
    WarriorPosition,
)

if TYPE_CHECKING:
    from nexus2.domain.automation.warrior_monitor import WarriorMonitor

logger = logging.getLogger(__name__)


# =============================================================================
# PRICE FALLBACK CHAIN
# =============================================================================


async def _get_price_with_fallbacks(
    monitor: "WarriorMonitor",
    position: WarriorPosition,
) -> Optional[Decimal]:
    """
    Get current price using Alpaca with fallback chain.
    
    Fallback order:
    1. Alpaca quote API
    2. Schwab real-time bid/ask
    3. FMP delayed quote
    4. Alpaca position current_price
    """
    if not monitor._get_price:
        logger.error(f"[Warrior] {position.symbol}: No price callback configured!")
        return None
    
    price = await monitor._get_price(position.symbol)
    
    # If Alpaca fails, try Schwab as first fallback (real-time bid/ask)
    if price is None or price == 0:
        logger.info(f"[Warrior] {position.symbol}: Alpaca quote failed, trying Schwab fallback...")
        try:
            from nexus2.adapters.market_data.schwab_adapter import get_schwab_adapter
            schwab = get_schwab_adapter()
            if schwab.is_authenticated():
                schwab_quote = schwab.get_quote(position.symbol)
                if schwab_quote and schwab_quote.get("price") and schwab_quote["price"] > 0:
                    price = float(schwab_quote["price"])
                    logger.info(f"[Warrior] {position.symbol}: Schwab fallback successful, price=${price}")
            else:
                logger.debug(f"[Warrior] Schwab not authenticated, skipping fallback")
        except Exception as e:
            logger.warning(f"[Warrior] {position.symbol}: Schwab fallback failed: {e}")
    
    # If still no price, try FMP as final fallback
    if price is None or price == 0:
        logger.info(f"[Warrior] {position.symbol}: Trying FMP fallback...")
        try:
            from nexus2.adapters.market_data.fmp_adapter import get_fmp_adapter
            fmp = get_fmp_adapter()
            fmp_quote = fmp.get_quote(position.symbol)
            if fmp_quote and fmp_quote.price and fmp_quote.price > 0:
                price = float(fmp_quote.price)
                logger.info(f"[Warrior] {position.symbol}: FMP fallback successful, price=${price}")
        except Exception as e:
            logger.warning(f"[Warrior] {position.symbol}: FMP fallback failed: {e}")
    
    # FINAL FALLBACK: Alpaca position current_price
    if price is None or price == 0:
        logger.info(f"[Warrior] {position.symbol}: Trying Alpaca position fallback...")
        try:
            if monitor._get_broker_positions:
                alpaca_positions = await monitor._get_broker_positions()
                if alpaca_positions:
                    for pos in alpaca_positions:
                        pos_symbol = pos.get("symbol") if isinstance(pos, dict) else getattr(pos, "symbol", None)
                        if pos_symbol == position.symbol:
                            pos_price = pos.get("current_price") if isinstance(pos, dict) else getattr(pos, "current_price", None)
                            if pos_price and float(pos_price) > 0:
                                price = float(pos_price)
                                logger.info(f"[Warrior] {position.symbol}: Alpaca position fallback successful, price=${price}")
                            break
        except Exception as e:
            logger.warning(f"[Warrior] {position.symbol}: Alpaca position fallback failed: {e}")
    
    # If still no valid price after ALL fallbacks
    if price is None or price == 0:
        logger.warning(
            f"[Warrior] {position.symbol}: All quote sources failed (price={price})! "
            f"STOP CHECK SKIPPED (stop=${position.current_stop})"
        )
        return None
    
    return Decimal(str(price))


# =============================================================================
# EXIT CHECKS
# =============================================================================


async def _check_after_hours_exit(
    monitor: "WarriorMonitor",
    position: WarriorPosition,
    current_price: Decimal,
    r_multiple: float,
) -> Optional[WarriorExitSignal]:
    """Check for after-hours exit conditions."""
    s = monitor.settings
    
    if not s.enable_after_hours_exit:
        return None
    
    from zoneinfo import ZoneInfo
    et_now = datetime.now(ZoneInfo("America/New_York"))
    current_time_str = et_now.strftime("%H:%M")
    
    # Force exit at 7:30 PM ET with ESCALATING offset
    if current_time_str >= s.force_exit_time_et:
        pnl = (current_price - position.entry_price) * position.shares
        
        # Parse force_exit_time to calculate minutes elapsed
        force_hour, force_min = map(int, s.force_exit_time_et.split(":"))
        force_exit_dt = et_now.replace(hour=force_hour, minute=force_min, second=0, microsecond=0)
        minutes_since_force = (et_now - force_exit_dt).total_seconds() / 60
        
        # Escalating offset: 2% base, +2% every 2 minutes, max 10%
        offset_tier = min(int(minutes_since_force / 2), 4)
        exit_offset = 0.02 + (offset_tier * 0.02)
        
        logger.warning(
            f"[Warrior] {position.symbol}: AFTER-HOURS EXIT at ${current_price} "
            f"(offset={exit_offset*100:.0f}%, {minutes_since_force:.1f}min since {s.force_exit_time_et} ET)"
        )
        return WarriorExitSignal(
            position_id=position.position_id,
            symbol=position.symbol,
            reason=WarriorExitReason.AFTER_HOURS_EXIT,
            exit_price=current_price,
            shares_to_exit=position.shares,
            pnl_estimate=pnl,
            stop_price=position.current_stop,
            r_multiple=r_multiple,
            trigger_description=f"Force exit at {s.force_exit_time_et} ET (offset={exit_offset*100:.0f}%)",
            exit_offset_percent=exit_offset,
        )
    
    # Tighten stop to breakeven at tighten time (if profitable)
    if current_time_str >= s.tighten_stop_time_et:
        if current_price > position.entry_price and position.current_stop < position.entry_price:
            old_stop = position.current_stop
            position.current_stop = position.entry_price
            logger.info(
                f"[Warrior] {position.symbol}: After-hours stop tightened to breakeven "
                f"${position.current_stop} (was ${old_stop})"
            )
    
    return None


async def _check_spread_exit(
    monitor: "WarriorMonitor",
    position: WarriorPosition,
    current_price: Decimal,
    r_multiple: float,
) -> Optional[WarriorExitSignal]:
    """Check for spread-based exit (liquidity protection)."""
    s = monitor.settings
    
    if not s.enable_spread_exit:
        return None
    
    # Only check spread after grace period
    entry_time = position.entry_time
    if entry_time.tzinfo is None:
        from datetime import timezone
        entry_time = entry_time.replace(tzinfo=timezone.utc)
    seconds_since_entry = (now_utc() - entry_time).total_seconds()
    
    if seconds_since_entry < s.spread_grace_period_seconds:
        return None
    
    if not monitor._get_quote_with_spread:
        return None
    
    try:
        spread_data = await monitor._get_quote_with_spread(position.symbol)
        if not spread_data:
            return None
        
        liquidity_status = spread_data.get("liquidity_status", "unknown")
        spread_pct = spread_data.get("spread_percent")
        bid = spread_data.get("bid", 0)
        ask = spread_data.get("ask", 0)
        
        if liquidity_status == "ok" and spread_pct is not None:
            logger.info(
                f"[Warrior] {position.symbol}: Spread {spread_pct:.1f}% "
                f"(max={s.max_spread_percent}%, bid=${bid:.2f}, ask=${ask:.2f})"
            )
            
            if spread_pct > s.max_spread_percent:
                pnl = (current_price - position.entry_price) * position.shares
                logger.warning(
                    f"[Warrior] {position.symbol}: SPREAD EXIT - spread {spread_pct:.1f}% "
                    f"(max={s.max_spread_percent}%, bid=${bid}, ask=${ask})"
                )
                return WarriorExitSignal(
                    position_id=position.position_id,
                    symbol=position.symbol,
                    reason=WarriorExitReason.SPREAD_EXIT,
                    exit_price=current_price,
                    shares_to_exit=position.shares,
                    pnl_estimate=pnl,
                    stop_price=position.current_stop,
                    r_multiple=r_multiple,
                    trigger_description=f"Spread {spread_pct:.1f}% > max {s.max_spread_percent}%",
                )
        elif liquidity_status == "no_ask_liquidity":
            logger.debug(
                f"[Warrior] {position.symbol}: No ask liquidity (bid=${bid:.2f}, ask=N/A) - spread check skipped"
            )
        elif liquidity_status == "no_bid_liquidity":
            logger.warning(
                f"[Warrior] {position.symbol}: No bid liquidity (bid=N/A, ask=${ask:.2f}) - caution!"
            )
        else:
            logger.debug(
                f"[Warrior] {position.symbol}: No quote data available for spread check"
            )
    except Exception as e:
        logger.debug(f"[Warrior] {position.symbol}: Spread check failed: {e}")
    
    return None


def _check_stop_hit(
    position: WarriorPosition,
    current_price: Decimal,
    r_multiple: float,
) -> Optional[WarriorExitSignal]:
    """Check if stop has been hit."""
    if current_price > position.current_stop:
        return None
    
    pnl = (current_price - position.entry_price) * position.shares
    
    # Determine stop type
    if position.technical_stop and position.current_stop == position.technical_stop:
        exit_reason = WarriorExitReason.TECHNICAL_STOP
        stop_type = "technical (candle low)"
    else:
        exit_reason = WarriorExitReason.MENTAL_STOP
        stop_type = "mental (15c)"
    
    logger.warning(
        f"[Warrior] {position.symbol}: STOP HIT at ${current_price} "
        f"(stop was ${position.current_stop}, type={stop_type})"
    )
    return WarriorExitSignal(
        position_id=position.position_id,
        symbol=position.symbol,
        reason=exit_reason,
        exit_price=current_price,
        shares_to_exit=position.shares,
        pnl_estimate=pnl,
        stop_price=position.current_stop,
        r_multiple=r_multiple,
        trigger_description=f"Price ${current_price} <= {stop_type} stop ${position.current_stop}",
    )


async def _check_candle_under_candle(
    monitor: "WarriorMonitor",
    position: WarriorPosition,
    current_price: Decimal,
    r_multiple: float,
) -> Optional[WarriorExitSignal]:
    """Check for candle-under-candle exit pattern."""
    s = monitor.settings
    
    if not s.enable_candle_under_candle or not monitor._get_intraday_candles:
        return None
    
    candles = await monitor._get_intraday_candles(position.symbol, timeframe="1min", limit=3)
    if not candles or len(candles) < 2:
        return None
    
    current_candle = candles[-1]
    prev_candle = candles[-2]
    
    # New low = current low < previous low
    if current_candle.low < prev_candle.low:
        # Also confirm it's red (close < open)
        if current_candle.close < current_candle.open:
            pnl = (current_price - position.entry_price) * position.shares
            logger.info(f"[Warrior] {position.symbol}: Candle-under-candle detected")
            return WarriorExitSignal(
                position_id=position.position_id,
                symbol=position.symbol,
                reason=WarriorExitReason.CANDLE_UNDER_CANDLE,
                exit_price=current_price,
                shares_to_exit=position.shares,
                pnl_estimate=pnl,
                r_multiple=r_multiple,
                trigger_description="New candle low (character exit)",
            )
    
    return None


async def _check_topping_tail(
    monitor: "WarriorMonitor",
    position: WarriorPosition,
    current_price: Decimal,
    r_multiple: float,
) -> Optional[WarriorExitSignal]:
    """Check for topping tail exit pattern."""
    s = monitor.settings
    
    if not s.enable_topping_tail or not monitor._get_intraday_candles:
        return None
    
    candles = await monitor._get_intraday_candles(position.symbol, timeframe="1min", limit=2)
    if not candles:
        return None
    
    current_candle = candles[-1]
    candle_range = current_candle.high - current_candle.low
    
    if candle_range <= 0:
        return None
    
    # Upper wick = high - max(open, close)
    body_top = max(current_candle.open, current_candle.close)
    upper_wick = current_candle.high - body_top
    wick_ratio = float(upper_wick / candle_range)
    
    # Topping tail: wick > 60% of range, at/near highs
    is_near_high = current_candle.high >= position.high_since_entry * Decimal("0.995")
    
    if wick_ratio >= s.topping_tail_threshold and is_near_high:
        pnl = (current_price - position.entry_price) * position.shares
        logger.info(
            f"[Warrior] {position.symbol}: Topping tail detected "
            f"(wick {wick_ratio*100:.0f}%)"
        )
        return WarriorExitSignal(
            position_id=position.position_id,
            symbol=position.symbol,
            reason=WarriorExitReason.TOPPING_TAIL,
            exit_price=current_price,
            shares_to_exit=position.shares,
            pnl_estimate=pnl,
            r_multiple=r_multiple,
            trigger_description=f"Topping tail ({wick_ratio*100:.0f}% wick)",
        )
    
    return None


async def _check_profit_target(
    monitor: "WarriorMonitor",
    position: WarriorPosition,
    current_price: Decimal,
    r_multiple: float,
) -> Optional[WarriorExitSignal]:
    """Check for profit target hit (partial exit)."""
    from nexus2.domain.automation.trade_event_service import trade_event_service
    
    s = monitor.settings
    
    if position.partial_taken:
        return None
    
    if current_price < position.profit_target:
        return None
    
    shares_to_exit = int(position.shares * s.partial_exit_fraction)
    if shares_to_exit < 1:
        return None
    
    pnl = (current_price - position.entry_price) * shares_to_exit
    logger.info(
        f"[Warrior] {position.symbol}: Profit target hit at {r_multiple:.1f}R "
        f"-> Partial exit ({shares_to_exit} shares)"
    )
    
    # Mark partial taken
    position.partial_taken = True
    position.shares -= shares_to_exit
    
    # Move stop to breakeven
    if s.move_stop_to_breakeven:
        position.current_stop = position.entry_price
        if monitor._update_stop:
            await monitor._update_stop(position.position_id, position.entry_price)
        trade_event_service.log_warrior_breakeven(
            position_id=position.position_id,
            symbol=position.symbol,
            entry_price=position.entry_price,
        )
        logger.info(f"[Warrior] {position.symbol}: Stop moved to breakeven")
    
    monitor.partials_triggered += 1
    
    # Determine target description
    if monitor.settings.profit_target_cents > 0:
        target_desc = f"Fixed +{monitor.settings.profit_target_cents}¢ target hit"
    else:
        target_desc = f"{monitor.settings.profit_target_r}:1 R target hit (${position.profit_target})"
    
    return WarriorExitSignal(
        position_id=position.position_id,
        symbol=position.symbol,
        reason=WarriorExitReason.PARTIAL_EXIT,
        exit_price=current_price,
        shares_to_exit=shares_to_exit,
        pnl_estimate=pnl,
        r_multiple=r_multiple,
        trigger_description=target_desc,
    )


# =============================================================================
# MAIN EVALUATION FUNCTION
# =============================================================================


async def evaluate_position(
    monitor: "WarriorMonitor",
    position: WarriorPosition,
    prefetched_price: Optional[float] = None,
) -> Optional[WarriorExitSignal]:
    """
    Evaluate position for exit conditions.
    
    Checks (in order of priority):
    1. Stop hit (mental or technical)
    2. Candle-under-candle pattern
    3. Topping tail rejection
    4. Profit target reached
    
    Args:
        monitor: The WarriorMonitor instance
        position: The position to evaluate
        prefetched_price: Pre-fetched price from batch quote (avoids individual API call)
    """
    # Get current price
    if prefetched_price is not None and prefetched_price != 0:
        current_price = Decimal(str(prefetched_price))
    else:
        current_price = await _get_price_with_fallbacks(monitor, position)
        if current_price is None:
            return None
    
    # Update high since entry
    if current_price > position.high_since_entry:
        position.high_since_entry = current_price
        try:
            from nexus2.db.warrior_db import update_high_since_entry
            update_high_since_entry(position.position_id, float(current_price))
        except Exception as e:
            logger.debug(f"[Warrior] {position.symbol}: Failed to persist high: {e}")
    
    # Calculate current R
    if position.risk_per_share > 0:
        current_gain = current_price - position.entry_price
        r_multiple = float(current_gain / position.risk_per_share)
    else:
        r_multiple = 0.0
    
    # CHECK 0: After-Hours Exit
    signal = await _check_after_hours_exit(monitor, position, current_price, r_multiple)
    if signal:
        return signal
    
    # CHECK 0.5: Spread Exit
    signal = await _check_spread_exit(monitor, position, current_price, r_multiple)
    if signal:
        return signal
    
    # CHECK 1: Stop Hit
    signal = _check_stop_hit(position, current_price, r_multiple)
    if signal:
        return signal
    
    # CHECK 2: Candle-Under-Candle
    signal = await _check_candle_under_candle(monitor, position, current_price, r_multiple)
    if signal:
        return signal
    
    # CHECK 3: Topping Tail
    signal = await _check_topping_tail(monitor, position, current_price, r_multiple)
    if signal:
        return signal
    
    # CHECK 4: Profit Target
    signal = await _check_profit_target(monitor, position, current_price, r_multiple)
    if signal:
        return signal
    
    return None


# =============================================================================
# EXIT EXECUTION
# =============================================================================


async def handle_exit(
    monitor: "WarriorMonitor",
    signal: WarriorExitSignal,
) -> None:
    """Handle an exit signal by executing the order and updating state."""
    from nexus2.domain.automation.trade_event_service import trade_event_service
    
    logger.info(
        f"[Warrior] Exit: {signal.symbol} - {signal.reason.value} - "
        f"{signal.shares_to_exit} shares (P&L: ${signal.pnl_estimate:.2f})"
    )
    
    order_success = False
    
    # Mark pending exit BEFORE submitting order (prevents duplicate exit signals)
    if signal.reason != WarriorExitReason.PARTIAL_EXIT:
        monitor._mark_pending_exit(signal.symbol)
    
    if monitor._execute_exit:
        try:
            result = await monitor._execute_exit(signal)
            monitor.exits_triggered += 1
            order_success = True
            
            # Get actual exit price from broker execution
            if result and isinstance(result, dict) and "actual_exit_price" in result:
                actual_exit_price = Decimal(str(result["actual_exit_price"]))
                position = monitor._positions.get(signal.position_id)
                if position:
                    actual_pnl = (actual_exit_price - position.entry_price) * signal.shares_to_exit
                else:
                    actual_pnl = signal.pnl_estimate
            else:
                actual_exit_price = signal.exit_price
                actual_pnl = signal.pnl_estimate
            
            # Store broker order ID for confirmation tracking
            if result and isinstance(result, dict) and "order" in result:
                order = result["order"]
                broker_order_id = getattr(order, "broker_order_id", None) if order else None
                if broker_order_id:
                    from nexus2.db.warrior_db import set_exit_order_id
                    set_exit_order_id(signal.position_id, broker_order_id)
                    logger.debug(f"[Warrior] {signal.symbol}: Stored exit order ID {broker_order_id}")
            
            # Log trade event
            exit_reason_map = {
                WarriorExitReason.MENTAL_STOP: "mental_stop",
                WarriorExitReason.TECHNICAL_STOP: "technical_stop",
                WarriorExitReason.CANDLE_UNDER_CANDLE: "candle_under_candle",
                WarriorExitReason.TOPPING_TAIL: "topping_tail",
                WarriorExitReason.TIME_STOP: "time_stop",
                WarriorExitReason.AFTER_HOURS_EXIT: "after_hours_exit",
                WarriorExitReason.BREAKOUT_FAILURE: "breakout_failure",
            }
            
            if signal.reason == WarriorExitReason.PARTIAL_EXIT:
                trade_event_service.log_warrior_partial_exit(
                    position_id=signal.position_id,
                    symbol=signal.symbol,
                    shares_sold=signal.shares_to_exit,
                    exit_price=actual_exit_price,
                    pnl=actual_pnl,
                    r_multiple=signal.r_multiple,
                )
            else:
                trade_event_service.log_warrior_exit(
                    position_id=signal.position_id,
                    symbol=signal.symbol,
                    exit_price=actual_exit_price,
                    exit_reason=exit_reason_map.get(signal.reason, "manual"),
                    pnl=actual_pnl,
                )
            
            # Track realized P&L
            monitor._add_realized_pnl(actual_pnl)
                
        except Exception as e:
            logger.error(f"[Warrior] Exit execution failed: {e}")
            monitor.last_error = str(e)
    else:
        logger.warning("[Warrior] No execute_exit callback - signal not acted on")
    
    # CRITICAL: Always remove position on FULL exit, even if order fails!
    if signal.reason != WarriorExitReason.PARTIAL_EXIT:
        # Track as recently exited
        monitor._recently_exited[signal.symbol] = now_utc()
        monitor._save_recently_exited()
        
        # 2-Strike Rule: only count if order was successful
        if order_success:
            stop_reasons = {
                WarriorExitReason.MENTAL_STOP,
                WarriorExitReason.TECHNICAL_STOP,
                WarriorExitReason.BREAKOUT_FAILURE,
            }
            if signal.reason in stop_reasons and monitor._record_symbol_fail:
                monitor._record_symbol_fail(signal.symbol)
        
        monitor.remove_position(signal.position_id)
        logger.info(f"[Warrior] {signal.symbol}: Removed from monitor (order_success={order_success})")
