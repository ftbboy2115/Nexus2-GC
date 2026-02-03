"""
Warrior Entry Execution

Pure extraction of order submission and fill polling logic from 
warrior_engine_entry.py::enter_position.

NOTE: Original functions remain in warrior_engine_entry.py.
      These are EXTRACTED COPIES for refactoring phase.
"""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

from nexus2.domain.automation.warrior_engine_types import (
    EntryTriggerType,
    WatchedCandidate,
)
from nexus2.utils.time_utils import now_utc

if TYPE_CHECKING:
    from nexus2.domain.automation.warrior_engine import WarriorEngine


logger = logging.getLogger(__name__)


# =============================================================================
# ORDER SUBMISSION HELPERS
# =============================================================================


def determine_exit_mode(
    engine: "WarriorEngine",
    watched: WatchedCandidate,
) -> str:
    """
    Determine exit mode based on entry conditions.
    
    EXIT MODE SELECTION:
    - Start with session setting as default
    - Override for re-entries (base_hit for quick scalps)
    - Override for volume explosions (home_run for runners)
    
    Args:
        engine: The WarriorEngine instance
        watched: The watched candidate
    
    Returns:
        Exit mode string: "base_hit" or "home_run"
    """
    symbol = watched.candidate.symbol
    session_exit_mode = engine.monitor.settings.session_exit_mode
    selected_exit_mode = session_exit_mode  # Default to user's session setting
    
    # RE-ENTRY / VOLUME EXPLOSION OVERRIDE
    is_reentry = watched.entry_attempt_count > 0 and watched.last_exit_time is not None
    entry_volume_ratio = getattr(watched, 'entry_volume_ratio', 0) or 0
    
    if is_reentry:
        # RE-ENTRY SAFETY VALVE: Force base_hit for re-entries
        # Ross CMCT transcript (Dec 2025): Re-entries are quick scalps, not home runs
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
    
    return selected_exit_mode


async def submit_entry_order(
    engine: "WarriorEngine",
    symbol: str,
    shares: int,
    limit_price: Decimal,
    exit_mode: str,
    trigger_type: EntryTriggerType,
) -> Tuple[Optional[Any], Optional[str], Optional[str]]:
    """
    Submit limit order via broker.
    
    Args:
        engine: The WarriorEngine instance
        symbol: Stock symbol
        shares: Number of shares
        limit_price: Limit price
        exit_mode: Exit mode for position management
        trigger_type: Entry trigger type
    
    Returns:
        (order_result, order_id, broker_order_id) or (None, None, None) on failure
    """
    if not engine._submit_order:
        logger.warning(f"[Warrior Entry] {symbol}: No submit_order callback")
        return None, None, None
    
    # Mark pending entry BEFORE submitting order
    engine._pending_entries[symbol] = now_utc()
    engine._save_pending_entries()
    logger.info(f"[Warrior Entry] {symbol}: Marked pending entry")
    
    try:
        order_result = await engine._submit_order(
            symbol=symbol,
            shares=shares,
            side="buy",
            order_type="limit",
            limit_price=float(limit_price),
            stop_loss=None,  # Mental stop, not broker stop
            exit_mode=exit_mode,
            entry_trigger=trigger_type.value,
        )
        
        # Check for blacklist response from broker
        if isinstance(order_result, dict) and order_result.get("blacklist"):
            engine._blacklist.add(symbol)
            logger.warning(f"[Warrior Entry] {symbol}: Added to blacklist - {order_result.get('error')}")
            return None, None, None
        
        if order_result is None:
            logger.warning(f"[Warrior Entry] {symbol}: Order returned None")
            return None, None, None
        
        # Extract order IDs
        order_id = None
        broker_order_id = None
        
        if hasattr(order_result, 'client_order_id'):
            order_id = str(order_result.client_order_id)
        elif isinstance(order_result, dict):
            order_id = order_result.get("order_id", symbol)
        else:
            order_id = symbol
        
        if hasattr(order_result, 'id'):
            broker_order_id = str(order_result.id)
        elif hasattr(order_result, 'broker_order_id'):
            broker_order_id = order_result.broker_order_id
        elif isinstance(order_result, dict):
            broker_order_id = order_result.get("id") or order_result.get("broker_order_id")
        
        return order_result, order_id, broker_order_id
        
    except Exception as e:
        import traceback
        logger.error(f"[Warrior Entry] {symbol}: Order failed: {e}\n{traceback.format_exc()}")
        engine.stats.last_error = str(e)
        engine.clear_pending_entry(symbol)
        return None, None, None


async def poll_for_fill(
    engine: "WarriorEngine",
    symbol: str,
    broker_order_id: str,
    entry_price: Decimal,
    max_attempts: int = 5,
    delay_seconds: float = 0.5,
) -> Tuple[Decimal, Optional[int], Optional[str]]:
    """
    Poll broker for fill confirmation.
    
    Args:
        engine: The WarriorEngine instance
        symbol: Stock symbol
        broker_order_id: Broker order ID for polling
        entry_price: Intended entry price (fallback)
        max_attempts: Maximum poll attempts
        delay_seconds: Delay between attempts
    
    Returns:
        (actual_fill_price, filled_qty, order_status)
    """
    actual_fill_price = entry_price
    filled_qty = None
    order_status = None
    
    logger.info(
        f"[Warrior Entry] {symbol}: Poll setup - broker_order_id={broker_order_id}, "
        f"has_get_order_status={engine._get_order_status is not None}"
    )
    
    if not (broker_order_id and engine._get_order_status):
        return actual_fill_price, filled_qty, order_status
    
    for attempt in range(max_attempts):
        await asyncio.sleep(delay_seconds)
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
                            filled_qty = getattr(order_detail, 'filled_qty', None)
                            order_status = status_str
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
    
    return actual_fill_price, filled_qty, order_status


def calculate_slippage(
    actual_fill_price: Decimal,
    entry_price: Decimal,
    symbol: str,
) -> Decimal:
    """
    Calculate and log slippage between intended and actual fill price.
    
    Args:
        actual_fill_price: Actual fill price from broker
        entry_price: Intended entry price
        symbol: Stock symbol
    
    Returns:
        Slippage in cents
    """
    actual_fill_decimal = Decimal(str(actual_fill_price)) if not isinstance(actual_fill_price, Decimal) else actual_fill_price
    entry_decimal = Decimal(str(entry_price)) if not isinstance(entry_price, Decimal) else entry_price
    
    slippage_cents = (actual_fill_decimal - entry_decimal) * 100
    
    if abs(slippage_cents) > Decimal("0.01"):
        slippage_bps = (actual_fill_decimal / entry_decimal - 1) * 10000
        logger.info(
            f"[Warrior Slippage] {symbol}: Fill ${actual_fill_decimal:.2f} vs "
            f"intended ${entry_decimal:.2f} = {slippage_cents:+.1f}¢ ({slippage_bps:+.1f}bps)"
        )
    
    return slippage_cents


def extract_order_status(order_result: Any) -> Tuple[Optional[str], int]:
    """
    Extract order status and filled quantity from order result.
    
    Args:
        order_result: Result from broker order submission
    
    Returns:
        (order_status, filled_qty)
    """
    order_status = None
    filled_qty = 0
    
    if hasattr(order_result, 'status'):
        status_val = order_result.status
        order_status = status_val.value if hasattr(status_val, 'value') else str(status_val)
        filled_qty = getattr(order_result, 'filled_qty', 0) or 0
    elif isinstance(order_result, dict):
        order_status = order_result.get("status")
        filled_qty = order_result.get("filled_qty", 0) or 0
    
    return order_status, filled_qty


# =============================================================================
# SCALING INTO EXISTING POSITION (MICRO-PULLBACK RE-ENTRIES)
# =============================================================================


async def scale_into_existing_position(
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
# ENTRY COMPLETION (DB + Monitor Integration)
# =============================================================================


async def complete_entry(
    engine: "WarriorEngine",
    watched: WatchedCandidate,
    entry_price: Decimal,
    actual_fill_price: Decimal,
    order_id: str,
    shares: int,
    mental_stop: Decimal,
    trigger_type: EntryTriggerType,
    exit_mode: str,
    support_level: Decimal,
    stop_method: str,
    limit_price: Decimal,
    filled_qty: Optional[int] = None,
    order_status: Optional[str] = None,
) -> None:
    """
    Complete entry by logging to DB and adding to monitor.
    
    Handles:
    - Intent logging to DB (before fill)
    - Entry validation logging
    - Trade event service logging
    - Fill confirmation and slippage
    - Monitor position addition
    
    Args:
        engine: The WarriorEngine instance
        watched: The watched candidate
        entry_price: Intended entry price (quote price)
        actual_fill_price: Actual fill price from broker
        order_id: Client order ID
        shares: Number of shares
        mental_stop: Mental stop price
        trigger_type: Entry trigger type
        exit_mode: Exit mode (base_hit or home_run)
        support_level: Support level for position
        stop_method: Stop calculation method used
        limit_price: Limit price sent to broker
        filled_qty: Actual filled quantity (optional)
        order_status: Order status string (optional)
    """
    symbol = watched.candidate.symbol
    entry_decimal = Decimal(str(entry_price)) if not isinstance(entry_price, Decimal) else entry_price
    
    # =================================================================
    # INTENT LOGGING: Write to DB to preserve trigger_type
    # =================================================================
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
            quote_price=float(entry_price),
            limit_price=float(limit_price),
            quote_source="unified",  # TODO: Pass actual source from quote
            exit_mode=exit_mode,
            is_sim=engine.monitor.sim_mode,
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
        from nexus2.domain.automation.trade_event_service import trade_event_service
        
        # Use the SAME snapshot that was calculated at the MACD gate
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
                "source": "entry_decision",
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
            exit_mode=exit_mode,
        )
    except Exception as e:
        logger.warning(f"[Warrior Entry] {symbol}: DB intent log failed: {e}")
    
    # =================================================================
    # FILL CONFIRMATION: Update DB with actual fill price
    # =================================================================
    actual_fill_decimal = Decimal(str(actual_fill_price)) if not isinstance(actual_fill_price, Decimal) else actual_fill_price
    
    if actual_fill_price != entry_price or (order_status and order_status.lower() in ("filled", "partially_filled")):
        try:
            from nexus2.db.warrior_db import update_warrior_fill
            mental_stop_cents = Decimal(str(engine.monitor.settings.mental_stop_cents))
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
    
    # =================================================================
    # MONITOR INTEGRATION: Add position to monitor
    # =================================================================
    # Calculate slippage and recalculate stop
    slippage_cents = (actual_fill_decimal - entry_decimal) * 100
    if abs(slippage_cents) > Decimal("0.01"):
        slippage_bps = (actual_fill_decimal / entry_decimal - 1) * 10000
        logger.info(
            f"[Warrior Slippage] {symbol}: Fill ${actual_fill_decimal:.2f} vs "
            f"intended ${entry_decimal:.2f} = {slippage_cents:+.1f}¢ ({slippage_bps:+.1f}bps)"
        )
    
    # Recalculate stop based on actual fill price
    actual_stop = actual_fill_decimal - Decimal(str(engine.monitor.settings.mental_stop_cents)) / 100
    
    engine.monitor.add_position(
        position_id=order_id,
        symbol=symbol,
        entry_price=actual_fill_decimal,
        shares=int(filled_qty) if filled_qty else shares,
        support_level=support_level,
        trigger_type=trigger_type.value,
        exit_mode_override=exit_mode,
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


