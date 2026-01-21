"""
Warrior Scaling Module

Handles scaling-in logic for Warrior Trading positions.
Extracted from warrior_monitor.py for improved modularity.

Ross Cameron Scaling Methodology:
- Add shares on pullbacks to support
- Only scale when position is working (above stop)
- Move stop to breakeven after successful scale
"""

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Optional, Dict

from nexus2.utils.time_utils import now_et
from nexus2.domain.automation.warrior_types import WarriorPosition

if TYPE_CHECKING:
    from nexus2.domain.automation.warrior_monitor import WarriorMonitor

logger = logging.getLogger(__name__)


# =============================================================================
# SCALE OPPORTUNITY DETECTION
# =============================================================================


async def check_scale_opportunity(
    monitor: "WarriorMonitor",
    position: WarriorPosition,
    current_price: Decimal,
) -> Optional[Dict]:
    """
    Check if position qualifies for scaling in (Ross Cameron methodology).
    
    Criteria:
    1. Scaling enabled and position not at max scale count
    2. RVOL strong enough (volume confirmation)
    3. Price at support zone (pullback, can be below entry)
    4. Support holding (not breaking down)
    
    Returns dict with scale signal details if opportunity detected, else None.
    """
    s = monitor.settings
    
    if not s.enable_scaling:
        return None
    
    if position.scale_count >= s.max_scale_count:
        return None
    
    # Check if price is at support (technical stop is our support level)
    # Allow scaling if price is near or at support but not below it
    support = position.technical_stop or position.mental_stop
    
    if not support or support <= 0:
        return None
    
    # SAFETY: Skip scaling if position is pending exit (prevents wash trade errors)
    symbol = position.symbol
    if monitor._is_pending_exit(symbol):
        logger.debug(f"[Warrior Scale] {symbol}: Skipping - pending exit in progress")
        return None
    
    # SAFETY: Skip scaling if price is too close to stop (< 1% buffer)
    # This prevents submitting buy orders right before stop is hit
    stop_buffer_pct = (current_price - support) / current_price * 100 if current_price > 0 else 0
    if stop_buffer_pct < 1.0:
        logger.debug(f"[Warrior Scale] {symbol}: Skipping - price too close to stop ({stop_buffer_pct:.1f}% buffer)")
        return None
    
    # SAFETY: Skip scaling if we recently attempted (60-second cooldown to prevent spam)
    if position.last_scale_attempt:
        cooldown_seconds = 60
        elapsed = (now_et() - position.last_scale_attempt).total_seconds()
        if elapsed < cooldown_seconds:
            logger.debug(f"[Warrior Scale] {symbol}: Skipping - cooldown ({cooldown_seconds - elapsed:.0f}s remaining)")
            return None
    
    # Price must be above support (not breaking down)
    if current_price < support:
        return None
    
    # Check if this is a pullback opportunity
    # Price should be between support and entry (or above if allow_scale_below_entry is False)
    is_pullback_zone = current_price <= position.entry_price or s.allow_scale_below_entry
    
    if not is_pullback_zone:
        return None
    
    # Calculate scale size
    add_shares = int(position.original_shares * s.scale_size_pct / 100)
    if add_shares < 1:
        add_shares = 1
    
    logger.info(
        f"[Warrior Scale] {position.symbol}: Scale opportunity detected - "
        f"price=${current_price}, support=${support}, add_shares={add_shares}"
    )
    
    return {
        "position_id": position.position_id,
        "symbol": position.symbol,
        "add_shares": add_shares,
        "price": float(current_price),
        "support": float(support),
        "scale_count": position.scale_count + 1,
    }


# =============================================================================
# SCALE EXECUTION
# =============================================================================


async def execute_scale_in(
    monitor: "WarriorMonitor",
    position: WarriorPosition,
    scale_signal: Dict,
) -> bool:
    """
    Execute a scale-in order (Ross Cameron methodology).
    
    1. Set SCALING status (PSM transition)
    2. Submit buy order for additional shares
    3. Update position state (scale_count, shares)
    4. Move stop to breakeven (if enabled)
    5. Complete scaling (PSM transition back to OPEN)
    
    Returns True if scale was executed successfully.
    """
    from nexus2.domain.automation.trade_event_service import trade_event_service
    
    if not monitor._submit_scale_order:
        logger.warning(f"[Warrior Scale] {position.symbol}: No scale order callback configured")
        return False
    
    # Early market check - block scaling on holidays/weekends
    if not monitor.sim_mode:
        from nexus2.adapters.market_data.market_calendar import get_market_calendar
        calendar = get_market_calendar(paper=True)
        status = calendar.get_market_status()
        if not status.is_open:
            reason = status.reason or "market_closed"
            logger.info(f"[Warrior Scale] {position.symbol}: Skipping scale - market closed ({reason})")
            return False
    
    symbol = position.symbol
    add_shares = scale_signal["add_shares"]
    price = Decimal(str(scale_signal["price"]))
    
    # Set SCALING status before submitting order (PSM validates transition)
    from nexus2.db.warrior_db import set_scaling_status, complete_scaling, revert_scaling
    if not set_scaling_status(position.position_id):
        logger.warning(f"[Warrior Scale] {symbol}: Cannot scale - PSM transition blocked")
        return False
    
    try:
        # FRESH QUOTE CHECK: Get real-time quote with bid/ask for accurate limit price
        # This prevents using stale ~$9.20 prices when market is actually at $8.60
        fresh_quote = None
        limit_price = None
        
        if monitor._get_quote_with_spread:
            try:
                spread_data = await monitor._get_quote_with_spread(symbol)
                if spread_data:
                    ask = spread_data.get("ask")
                    bid = spread_data.get("bid")
                    quote_price = spread_data.get("price")
                    
                    # Validate quote freshness - if bid/ask is available, quote is real-time
                    if ask and ask > 0:
                        # Use ask + 2 cents for buy limit (ensures fill at real price)
                        limit_price = (Decimal(str(ask)) + Decimal("0.02")).quantize(Decimal("0.01"))
                        logger.info(f"[Warrior Scale] {symbol}: Using fresh ask ${ask:.2f} → limit ${limit_price}")
                    elif bid and bid > 0 and quote_price and quote_price > 0:
                        # No ask available - use mid-point
                        mid = (Decimal(str(bid)) + Decimal(str(quote_price))) / 2
                        limit_price = (mid + Decimal("0.03")).quantize(Decimal("0.01"))
                        logger.info(f"[Warrior Scale] {symbol}: Using midpoint ${mid:.2f} → limit ${limit_price}")
            except Exception as e:
                logger.warning(f"[Warrior Scale] {symbol}: Fresh quote failed: {e}")
        
        # Fallback: Use passed-in price (may be stale) - add warning
        if limit_price is None:
            # SAFETY CHECK: Compare passed-in price vs entry price
            # If > 10% different from entry, skip scale (likely stale quote)
            price_diff_pct = abs(float(price) - float(position.entry_price)) / float(position.entry_price) * 100
            if price_diff_pct > 10:
                logger.warning(
                    f"[Warrior Scale] {symbol}: STALE QUOTE SUSPECTED - "
                    f"quote ${price:.2f} is {price_diff_pct:.1f}% from entry ${position.entry_price:.2f}, skipping"
                )
                revert_scaling(position.position_id)
                return False
            
            limit_price = (price + Decimal("0.03")).quantize(Decimal("0.01"))
            logger.warning(f"[Warrior Scale] {symbol}: Using fallback price ${price:.2f} → limit ${limit_price} (no fresh quote)")
        
        logger.info(
            f"[Warrior Scale] {symbol}: Submitting scale order - "
            f"{add_shares} shares @ limit ${limit_price}"
        )
        
        # Mark attempt timestamp (for cooldown on retry)
        position.last_scale_attempt = now_et()
        
        order_result = await monitor._submit_scale_order(
            symbol=symbol,
            shares=add_shares,
            side="buy",
            order_type="limit",
            limit_price=float(limit_price),
        )
        
        if order_result is None:
            # Check if market is closed (holiday/weekend)
            from nexus2.adapters.market_data.market_calendar import get_market_calendar
            cal = get_market_calendar(paper=True)
            market_status = cal.get_market_status()
            if not market_status.is_open:
                reason = market_status.reason or "market_closed"
                logger.warning(f"[Warrior Scale] {symbol}: Scale order rejected - market closed ({reason})")
            else:
                logger.warning(f"[Warrior Scale] {symbol}: Scale order returned None (unknown reason)")
            # Revert to OPEN since order couldn't be submitted
            revert_scaling(position.position_id)
            return False
        
        # Update position state
        position.scale_count += 1
        position.shares += add_shares
        new_total_shares = position.shares
        
        # Complete scaling in DB (SCALING → OPEN with updated shares)
        complete_scaling(position.position_id, new_total_shares)
        
        # Move stop to breakeven (original entry price)
        if monitor.settings.move_stop_to_breakeven_after_scale:
            old_stop = position.current_stop
            position.current_stop = position.entry_price
            
            if monitor._update_stop:
                await monitor._update_stop(position.position_id, position.entry_price)
            
            # Log event
            trade_event_service.log_warrior_stop_update(
                position_id=position.position_id,
                symbol=symbol,
                old_stop=old_stop,
                new_stop=position.entry_price,
                reason="scale_breakeven",
            )
            
            logger.info(
                f"[Warrior Scale] {symbol}: Stop moved to breakeven ${position.entry_price} "
                f"(was ${old_stop})"
            )
        
        logger.info(
            f"[Warrior Scale] {symbol}: Scale #{position.scale_count} complete - "
            f"now {position.shares} shares"
        )
        
        return True
        
    except Exception as e:
        logger.error(f"[Warrior Scale] {symbol}: Scale order failed: {e}")
        # Revert to OPEN on exception
        revert_scaling(position.position_id)
        return False
