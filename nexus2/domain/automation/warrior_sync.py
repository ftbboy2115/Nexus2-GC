"""
Warrior Broker Sync Module

Handles synchronization between WarriorMonitor state and Alpaca broker positions.
Extracted from warrior_monitor.py for improved modularity.

Responsibilities:
- Sync monitored position share counts with broker
- Auto-recover orphaned broker positions
- Confirm pending exits when broker shows zero shares
- Immediate stop check on recovery (handles positions gapped below stop)
"""

import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional, Dict, Any
from uuid import uuid4

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
# BROKER SYNC FUNCTIONS
# =============================================================================


def _build_broker_map(broker_positions: List[Any]) -> Dict[str, int]:
    """Build symbol -> qty lookup from broker positions."""
    broker_map = {}
    for pos in broker_positions:
        if isinstance(pos, dict):
            symbol = pos.get("symbol")
            qty = int(pos.get("qty", 0))
        else:
            symbol = pos.symbol
            qty = int(pos.qty)
        broker_map[symbol] = qty
    return broker_map


def _find_broker_position(broker_positions: List[Any], symbol: str) -> Optional[Any]:
    """Find a broker position by symbol."""
    for pos in broker_positions:
        pos_symbol = pos.get("symbol") if isinstance(pos, dict) else getattr(pos, "symbol", None)
        if pos_symbol == symbol:
            return pos
    return None


def _get_entry_price(broker_pos: Any) -> Decimal:
    """Extract entry price from broker position."""
    if isinstance(broker_pos, dict):
        return Decimal(str(broker_pos.get("avg_price", 0)))
    return Decimal(str(getattr(broker_pos, "avg_price", 0)))


async def _sync_monitored_positions(
    monitor: "WarriorMonitor",
    broker_map: Dict[str, int],
) -> None:
    """Sync each monitored position with broker state."""
    for position_id, position in list(monitor._positions.items()):
        symbol = position.symbol
        broker_qty = broker_map.get(symbol, 0)

        if broker_qty == 0:
            # Position closed at broker - remove from monitor
            logger.warning(
                f"[Warrior Sync] {symbol}: Broker has 0 shares, removing from monitor"
            )
            monitor.remove_position(position_id)
        elif broker_qty != position.shares:
            # Shares mismatch - update monitor to match broker
            old_shares = position.shares
            position.shares = broker_qty

            # If broker has fewer shares, partial was taken
            if broker_qty < old_shares:
                position.partial_taken = True

            logger.info(
                f"[Warrior Sync] {symbol}: Updated shares {old_shares} -> {broker_qty}"
            )


async def _check_pending_exit_status(
    monitor: "WarriorMonitor",
    symbol: str,
    broker_entry: Decimal,
    now: datetime,
) -> bool:
    """
    Check if pending exit should be cleared or skipped.
    
    Returns True if recovery should be skipped, False if should continue.
    """
    from nexus2.db.warrior_db import get_warrior_trade_by_symbol
    
    pending_trade = get_warrior_trade_by_symbol(symbol, status="pending_exit")
    
    if not pending_trade or broker_entry <= 0:
        logger.debug(f"[Warrior Sync] {symbol}: Skipping recovery (pending exit)")
        return True
    
    db_entry = Decimal(str(pending_trade.get("entry_price", 0)))
    
    # Try to confirm by order ID if available
    exit_order_id = pending_trade.get("exit_order_id")
    if exit_order_id and monitor._get_order_status:
        try:
            order_status = await monitor._get_order_status(exit_order_id)
            if order_status:
                status = order_status.status.value if hasattr(order_status.status, 'value') else str(order_status.status)
                if status == "filled":
                    logger.info(f"[Warrior Sync] {symbol}: Exit confirmed by order ID (filled)")
                    monitor._clear_pending_exit(symbol, to_closed=True)
                    return True
                elif status in ["cancelled", "expired", "rejected"]:
                    logger.info(f"[Warrior Sync] {symbol}: Exit order {status}, reverting to open")
                    monitor._clear_pending_exit(symbol, to_closed=False)
                    # Don't return - allow recovery below
        except Exception as e:
            logger.debug(f"[Warrior Sync] {symbol}: Order status check failed: {e}")
    
    # Fallback: If entry prices differ by more than 1%, this is a NEW position
    price_diff_pct = abs((broker_entry - db_entry) / db_entry * 100) if db_entry > 0 else 100
    
    # Check if pending_exit is stale (>2 minutes old)
    updated_at_str = pending_trade.get("updated_at")
    is_stale = False
    stale_seconds = 0
    if updated_at_str:
        try:
            if isinstance(updated_at_str, str):
                updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
            else:
                updated_at = updated_at_str
            # Ensure timezone-aware (assume UTC if naive)
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            stale_seconds = (now - updated_at).total_seconds()
            is_stale = stale_seconds > 120  # 2 minutes
        except Exception:
            pass
    
    if price_diff_pct > 1.0:
        logger.info(
            f"[Warrior Sync] {symbol}: Clearing stale pending_exit "
            f"(DB entry=${db_entry:.2f}, broker=${broker_entry:.2f})"
        )
        monitor._clear_pending_exit(symbol, to_closed=True)
        return False  # Continue with recovery
    elif is_stale:
        logger.info(
            f"[Warrior Sync] {symbol}: Clearing stale pending_exit "
            f"(exit order timed out after {stale_seconds:.0f}s, broker still has shares)"
        )
        monitor._clear_pending_exit(symbol, to_closed=False)  # Revert to open
        return False  # Continue with recovery
    else:
        logger.debug(f"[Warrior Sync] {symbol}: Skipping recovery (pending exit)")
        return True


async def _calculate_stop_price(
    monitor: "WarriorMonitor",
    symbol: str,
    entry_price: Decimal,
) -> tuple[Optional[Decimal], str]:
    """Calculate stop price using technical analysis or fallback."""
    stop_price = None
    stop_method = "fallback_15c"
    
    if monitor._get_intraday_candles:
        try:
            candles = await monitor._get_intraday_candles(symbol, "1min", limit=50)
            if candles and len(candles) >= 5:
                from nexus2.domain.indicators import get_stop_calculator
                stop_calc = get_stop_calculator()
                stop_price, stop_method = stop_calc.get_best_stop(
                    [{"high": c.high, "low": c.low, "close": c.close, "volume": c.volume} for c in candles],
                    entry_price,
                    symbol,
                )
        except Exception as e:
            logger.debug(f"[Warrior Sync] {symbol}: Technical stop calc failed: {e}")
    
    # Fallback to 15¢ stop if technical calc failed
    if stop_price is None:
        stop_price = entry_price - monitor.settings.mental_stop_cents / 100
        stop_method = "fallback_15c"
    
    return stop_price, stop_method


async def _recover_position(
    monitor: "WarriorMonitor",
    symbol: str,
    qty: int,
    broker_pos: Any,
    now: datetime,
) -> Optional[WarriorPosition]:
    """
    Recover a position from broker that's not in monitor.
    
    Returns the recovered position or None if recovery should be skipped.
    """
    from nexus2.db.warrior_db import get_warrior_trade_by_symbol, log_warrior_entry
    from nexus2.domain.automation.trade_event_service import trade_event_service
    
    entry_price = _get_entry_price(broker_pos)
    if entry_price <= 0:
        logger.warning(
            f"[Warrior Sync] {symbol}: Found at broker ({qty} shares) but cannot recover - no entry price"
        )
        return None
    
    # Calculate stop price
    stop_price, stop_method = await _calculate_stop_price(monitor, symbol, entry_price)
    
    # Get current price for validation
    current_price = None
    if monitor._get_price:
        try:
            current_price = await monitor._get_price(symbol)
            if current_price:
                current_price = Decimal(str(current_price))
        except Exception:
            pass
    
    # If already below stop, skip sync (position is invalidated)
    # BUT: Don't skip recovery - we need to add it to trigger immediate exit
    
    profit_target_r = Decimal(str(monitor.settings.profit_target_r))
    target_price = entry_price + (monitor.settings.mental_stop_cents / 100 * profit_target_r)
    
    # Try to recover existing trade (preserves original position_id and trigger_type)
    existing_trade = None
    recovered_position_id = None
    recovered_trigger_type = "synced"  # Default for truly external positions
    
    try:
        existing_trade = get_warrior_trade_by_symbol(symbol)
        if existing_trade:
            recovered_position_id = existing_trade["id"]
            recovered_trigger_type = existing_trade.get("trigger_type", "recovered")
            logger.info(
                f"[Warrior Sync] {symbol}: Recovering existing position {recovered_position_id[:8]}... "
                f"(trigger: {recovered_trigger_type})"
            )
    except Exception as lookup_err:
        logger.debug(f"[Warrior Sync] {symbol}: Lookup failed: {lookup_err}")
    
    # Use recovered ID or create new for external positions
    position_id = recovered_position_id or str(uuid4())
    
    # Use DB values if we recovered an existing trade
    if existing_trade:
        # Prefer DB values for accurate recovery
        recovered_entry_price = Decimal(str(existing_trade.get("entry_price", entry_price)))
        recovered_high = Decimal(str(existing_trade.get("high_since_entry", entry_price) or entry_price))
        
        # CRITICAL: Restore original stop and target from DB
        db_stop = existing_trade.get("stop_price")
        db_target = existing_trade.get("target_price")
        if db_stop:
            stop_price = Decimal(str(db_stop))
            stop_method = "db_restored"
        if db_target:
            target_price = Decimal(str(db_target))
        
        # Parse entry_time from DB (ISO string)
        entry_time_str = existing_trade.get("entry_time")
        if entry_time_str:
            try:
                if isinstance(entry_time_str, str):
                    recovered_entry_time = datetime.fromisoformat(entry_time_str.replace("Z", "+00:00"))
                else:
                    recovered_entry_time = entry_time_str
                # Ensure timezone-aware (assume UTC if naive)
                if recovered_entry_time.tzinfo is None:
                    recovered_entry_time = recovered_entry_time.replace(tzinfo=timezone.utc)
            except Exception:
                recovered_entry_time = now
        else:
            recovered_entry_time = now
        
        # Check if partial was already taken
        partial_already_taken = existing_trade.get("partial_taken", False)
    else:
        # New external position - use Alpaca values
        recovered_entry_price = entry_price
        recovered_high = entry_price
        recovered_entry_time = now
        partial_already_taken = False
    
    # TARGET SANITY CHECK: If target is already below current price,
    # mark partial as taken to prevent false profit-target exits
    if current_price and target_price:
        if current_price > target_price:
            if not partial_already_taken:
                logger.warning(
                    f"[Warrior Sync] {symbol}: Target sanity check - price ${current_price:.2f} "
                    f"> target ${target_price:.2f}, marking partial as taken"
                )
                partial_already_taken = True
    
    position = WarriorPosition(
        position_id=position_id,
        symbol=symbol,
        entry_price=recovered_entry_price,
        shares=qty,
        entry_time=recovered_entry_time,
        current_stop=stop_price,
        profit_target=target_price,
        mental_stop=stop_price,
        technical_stop=None,
        high_since_entry=recovered_high,
        risk_per_share=recovered_entry_price - stop_price,
        original_shares=qty,
        partial_taken=partial_already_taken,
    )
    monitor._positions[position.position_id] = position
    
    # =============================================================
    # CRITICAL: Check if position is below stop at recovery time
    # =============================================================
    if current_price and stop_price:
        if current_price <= stop_price:
            logger.warning(
                f"[Warrior Sync] {symbol}: RECOVERED BELOW STOP - "
                f"price=${current_price:.2f} <= stop=${stop_price:.2f}, "
                f"triggering immediate exit"
            )
            # Generate exit signal
            pnl = (current_price - recovered_entry_price) * qty
            r_multiple = float(pnl / (position.risk_per_share * qty)) if position.risk_per_share > 0 else 0
            exit_signal = WarriorExitSignal(
                position_id=position.position_id,
                symbol=symbol,
                reason=WarriorExitReason.MENTAL_STOP,
                exit_price=current_price,
                shares_to_exit=qty,
                pnl_estimate=pnl,
                stop_price=stop_price,
                r_multiple=r_multiple,
                trigger_description=f"Recovered below stop (${current_price:.2f} <= ${stop_price:.2f})",
            )
            # Execute exit immediately
            await monitor._handle_exit(exit_signal)
            return None  # Don't log recovery since we're exiting
    
    # Only log new entry if we didn't recover an existing one
    if not existing_trade:
        # Persist to warrior_db for Trade History (new external position)
        try:
            log_warrior_entry(
                trade_id=position.position_id,
                symbol=symbol,
                entry_price=float(entry_price),
                quantity=qty,
                stop_price=float(stop_price),
                target_price=float(target_price),
                trigger_type="external",
                support_level=float(stop_price),
            )
        except Exception as db_err:
            logger.warning(f"[Warrior Sync] {symbol}: DB log failed: {db_err}")
        
        # Log entry event for AI trade analysis (new external position)
        try:
            trade_event_service.log_warrior_entry(
                position_id=position.position_id,
                symbol=symbol,
                entry_price=entry_price,
                stop_price=stop_price,
                shares=qty,
                trigger_type="external",
            )
        except Exception as event_err:
            logger.warning(f"[Warrior Sync] {symbol}: Event log failed: {event_err}")
    
    logger.info(
        f"[Warrior Sync] {symbol}: {'Recovered' if existing_trade else 'Auto-synced'} "
        f"({qty} shares @ ${entry_price:.2f}, stop=${stop_price:.2f} via {stop_method})"
    )
    
    return position


async def _recover_orphaned_positions(
    monitor: "WarriorMonitor",
    broker_positions: List[Any],
    broker_map: Dict[str, int],
) -> None:
    """Check for broker positions not in monitor and auto-recover them."""
    monitored_symbols = {p.symbol for p in monitor._positions.values()}
    now = now_utc()
    
    # Clean up old entries from recently exited
    expired = [s for s, t in monitor._recently_exited.items()
               if (now - t).total_seconds() > monitor._recovery_cooldown_seconds]
    for s in expired:
        del monitor._recently_exited[s]
    
    for symbol, qty in broker_map.items():
        if symbol not in monitored_symbols and qty > 0:
            # Find the broker position data
            broker_pos = _find_broker_position(broker_positions, symbol)
            if not broker_pos:
                continue
            
            # Get entry price early for pending_exit check
            broker_entry = _get_entry_price(broker_pos)
            
            # Skip if pending exit (prevents re-adding position we're trying to close)
            if monitor._is_pending_exit(symbol):
                should_skip = await _check_pending_exit_status(monitor, symbol, broker_entry, now)
                if should_skip:
                    continue
            
            # Skip if recently exited (prevent race condition with pending sell orders)
            if symbol in monitor._recently_exited:
                exit_time = monitor._recently_exited[symbol]
                secs_ago = (now - exit_time).total_seconds()
                logger.debug(f"[Warrior Sync] {symbol}: Skipping recovery (exited {secs_ago:.0f}s ago)")
                continue
            
            # Recover the position
            await _recover_position(monitor, symbol, qty, broker_pos, now)


async def _confirm_completed_exits(
    monitor: "WarriorMonitor",
    broker_map: Dict[str, int],
) -> None:
    """Confirm pending exits that are now fully closed at broker."""
    for symbol in monitor._get_pending_exit_symbols():
        if broker_map.get(symbol, 0) == 0:
            # Position gone from broker = exit confirmed
            monitor._clear_pending_exit(symbol, to_closed=True)
            logger.info(f"[Warrior Sync] {symbol}: Exit confirmed by broker")


# =============================================================================
# MAIN SYNC FUNCTION
# =============================================================================


async def sync_with_broker(monitor: "WarriorMonitor") -> None:
    """
    Sync monitor state with Alpaca broker positions.
    
    Fixes state drift where:
    - Partial orders submitted but not filled
    - Positions closed manually at broker
    - Shares differ between monitor and broker
    
    Args:
        monitor: The WarriorMonitor instance to sync
    """
    if not monitor._get_broker_positions:
        return
    
    try:
        broker_positions = await monitor._get_broker_positions()
        
        # Skip sync if broker returned error (None)
        if broker_positions is None:
            logger.warning("[Warrior Sync] Skipping sync - broker returned error")
            return
        
        # Build lookup: symbol -> broker qty
        broker_map = _build_broker_map(broker_positions)
        
        # Sync each monitored position
        await _sync_monitored_positions(monitor, broker_map)
        
        # Check for orphaned broker positions and auto-recover
        await _recover_orphaned_positions(monitor, broker_positions, broker_map)
        
        # Confirm pending exits that are now fully closed at broker
        await _confirm_completed_exits(monitor, broker_map)
        
    except Exception as e:
        logger.error(f"[Warrior Sync] Error syncing with broker: {e}")
