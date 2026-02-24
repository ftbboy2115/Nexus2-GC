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
    # Fix 5A: Skip wall-clock cooldown in sim mode (all bars process in ~1s, cooldown blocks everything)
    if position.last_scale_attempt and not (s.enable_improved_scaling and monitor.sim_mode):
        cooldown_seconds = 60
        elapsed = (now_et() - position.last_scale_attempt).total_seconds()
        if elapsed < cooldown_seconds:
            logger.debug(f"[Warrior Scale] {symbol}: Skipping - cooldown ({cooldown_seconds - elapsed:.0f}s remaining)")
            return None
    
    # SAFETY: Skip scaling if position was recently recovered from broker sync
    # This prevents wash trade errors when orphan cleanup and scale race during restart
    # Fix 5A: Skip recovery grace in sim mode (no broker sync race in sim)
    if position.recovered_at and not (s.enable_improved_scaling and monitor.sim_mode):
        recovery_grace_seconds = 10  # Align with Ross's 10-second chart
        elapsed = (now_et() - position.recovered_at).total_seconds()
        if elapsed < recovery_grace_seconds:
            logger.debug(f"[Warrior Scale] {symbol}: Skipping - recovery grace period ({recovery_grace_seconds - elapsed:.0f}s remaining)")
            return None
    
    # Price must be above support (not breaking down)
    if current_price < support:
        return None
    
    # === TRACE LOGGING: Full state snapshot before pullback zone check ===
    exit_mode = getattr(position, 'exit_mode_override', None)
    partial = getattr(position, 'partial_taken', False)
    logger.info(
        f"[Warrior Scale TRACE] {symbol}: CHECKPOINT — "
        f"price=${current_price}, entry=${position.entry_price}, support=${support}, "
        f"shares={position.shares}, original_shares={getattr(position, 'original_shares', '?')}, "
        f"scale_count={position.scale_count}, partial_taken={partial}, "
        f"exit_mode_override={exit_mode}, "
        f"high_since_entry=${getattr(position, 'high_since_entry', '?')}, "
        f"current_stop=${position.current_stop}, "
        f"candle_trail_stop={getattr(position, 'candle_trail_stop', None)}"
    )
    
    # Check if this is a pullback opportunity
    # Fix 5B: Proper pullback zone logic (Ross scales on pullbacks to support,
    # not at any price). Price must have pulled back toward support.
    if s.enable_improved_scaling:
        # Pullback zone = within 50% of entry-to-support range, measured from entry down.
        # E.g., entry=$3.22, support=$2.72 (50¢ range) → scale zone = $2.97 and below
        # (pulled back at least 25¢ from entry, but still above support)
        support_distance = position.entry_price - support
        if support_distance > 0:
            pullback_threshold = position.entry_price - (support_distance * Decimal("0.5"))
            is_pullback_zone = current_price <= pullback_threshold and current_price > support
        else:
            is_pullback_zone = False
        logger.info(
            f"[Warrior Scale TRACE] {symbol}: PULLBACK CHECK — "
            f"support_distance=${support_distance:.4f}, "
            f"pullback_threshold=${pullback_threshold if support_distance > 0 else 'N/A'}, "
            f"is_pullback_zone={is_pullback_zone}"
        )
    else:
        # Original (broken) logic: always True when allow_scale_below_entry=True
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
        "trigger": "pullback",  # Distinguish from momentum adds
    }


# =============================================================================
# MOMENTUM ADD DETECTION (Ross Cameron breakout continuation)
# =============================================================================


async def check_momentum_add(
    monitor: "WarriorMonitor",
    position: WarriorPosition,
    current_price: Decimal,
) -> Optional[Dict]:
    """
    Check if position qualifies for a momentum add (Ross Cameron "add on strength").
    
    Ross adds shares as price moves up: e.g., entry at $7.50, add at $10, $11, $12.
    This is INDEPENDENT from pullback scaling — uses its own counter.
    
    Criteria:
    1. enable_momentum_adds is True
    2. Position is green (current_price > entry_price)
    3. momentum_add_count < max_momentum_adds
    4. Price moved up at least momentum_add_interval since last add (or entry)
    5. Position not pending exit
    6. Price not too close to stop (safety buffer)
    
    Returns dict with scale signal details if opportunity detected, else None.
    """
    s = monitor.settings
    
    if not s.enable_momentum_adds:
        return None
    
    if position.momentum_add_count >= s.max_momentum_adds:
        return None
    
    # Must be green (price above entry)
    if current_price <= position.entry_price:
        return None
    
    # SAFETY: Skip if position is pending exit
    symbol = position.symbol
    if monitor._is_pending_exit(symbol):
        logger.debug(f"[Warrior Momentum] {symbol}: Skipping - pending exit")
        return None
    
    # Reference price: last momentum add price, or entry price if no adds yet
    reference_price = position.last_momentum_add_price or position.entry_price
    
    # Check if price has moved up enough since last add
    price_move = current_price - reference_price
    interval = Decimal(str(s.momentum_add_interval))
    
    if price_move < interval:
        return None
    
    # SAFETY: Skip if price is too close to stop (< 1% buffer)
    support = position.technical_stop or position.mental_stop
    if support and support > 0:
        stop_buffer_pct = (current_price - support) / current_price * 100 if current_price > 0 else 0
        if stop_buffer_pct < 1.0:
            logger.debug(
                f"[Warrior Momentum] {symbol}: Skipping - price too close to stop "
                f"({stop_buffer_pct:.1f}% buffer)"
            )
            return None
    
    # SAFETY: Cooldown check — skip if recently attempted (sim mode bypasses this)
    if position.last_scale_attempt and not monitor.sim_mode:
        cooldown_seconds = 60
        elapsed = (now_et() - position.last_scale_attempt).total_seconds()
        if elapsed < cooldown_seconds:
            logger.debug(
                f"[Warrior Momentum] {symbol}: Skipping - cooldown "
                f"({cooldown_seconds - elapsed:.0f}s remaining)"
            )
            return None
    
    # Calculate add size
    add_shares = int(position.original_shares * s.momentum_add_size_pct / 100)
    if add_shares < 1:
        add_shares = 1
    
    logger.info(
        f"[Warrior Momentum] {position.symbol}: Momentum add opportunity - "
        f"price=${current_price} (+${price_move:.2f} since ref=${reference_price}), "
        f"add_shares={add_shares}, momentum_add #{position.momentum_add_count + 1}"
    )
    
    return {
        "position_id": position.position_id,
        "symbol": position.symbol,
        "add_shares": add_shares,
        "price": float(current_price),
        "support": float(support) if support else 0.0,
        "scale_count": position.scale_count + 1,
        "trigger": "momentum",  # Distinguish from pullback
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
        old_shares = position.shares
        old_entry = position.entry_price
        position.scale_count += 1
        position.shares += add_shares
        new_total_shares = position.shares
        
        # Calculate weighted-average entry price (matches _consolidate_existing_position pattern)
        old_cost = old_entry * old_shares
        new_cost = price * add_shares
        new_avg_entry = (old_cost + new_cost) / new_total_shares
        
        # Update position entry price to weighted average
        position.entry_price = new_avg_entry
        
        # Recalculate risk and target based on new average entry
        risk_per_share = new_avg_entry - position.current_stop
        position.risk_per_share = risk_per_share
        
        s = monitor.settings
        if s.profit_target_cents > 0:
            position.profit_target = new_avg_entry + s.profit_target_cents / 100
        else:
            position.profit_target = new_avg_entry + (risk_per_share * Decimal(str(s.profit_target_r)))
        
        # Complete scaling in DB (SCALING → OPEN with updated shares and avg price)
        complete_scaling(position.position_id, new_total_shares, new_avg_price=float(new_avg_entry))
        
        # Log scale event (Trade Events tab visibility)
        trade_event_service.log_warrior_scale_in(
            position_id=position.position_id,
            symbol=symbol,
            add_price=price,
            shares_added=add_shares,
        )
        
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
        
        # === TRACE LOGGING: Full post-scale state ===
        logger.info(
            f"[Warrior Scale TRACE] {symbol}: SCALE EXECUTED — "
            f"scale #{position.scale_count}, "
            f"shares {old_shares} → {position.shares} (+{add_shares}), "
            f"entry_price ${old_entry:.2f} → ${position.entry_price:.2f} (weighted avg), "
            f"current_stop=${position.current_stop}, "
            f"partial_taken={getattr(position, 'partial_taken', '?')}, "
            f"exit_mode_override={getattr(position, 'exit_mode_override', None)}, "
            f"scale_price=${price:.2f}, limit=${limit_price}"
        )
        
        logger.info(
            f"[Warrior Scale] {symbol}: Scale #{position.scale_count} complete - "
            f"now {position.shares} shares"
        )
        
        # Update momentum tracking if this was a momentum add
        if scale_signal.get("trigger") == "momentum":
            position.last_momentum_add_price = price
            position.momentum_add_count += 1
            logger.info(
                f"[Warrior Momentum] {symbol}: Momentum add #{position.momentum_add_count} tracked "
                f"at ${price:.2f}"
            )
        
        return True
        
    except Exception as e:
        logger.error(f"[Warrior Scale] {symbol}: Scale order failed: {e}")
        # Revert to OPEN on exception
        revert_scaling(position.position_id)
        return False
