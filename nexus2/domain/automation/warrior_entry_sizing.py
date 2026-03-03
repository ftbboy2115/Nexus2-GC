"""
Warrior Entry Sizing

Pure extraction of position sizing logic from warrior_engine_entry.py::enter_position.
Calculates position size, stop price, and profit target based on risk parameters.

NOTE: Original functions remain in warrior_engine_entry.py.
      These are EXTRACTED COPIES for refactoring phase.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Optional, Tuple

from nexus2.domain.automation.warrior_engine_types import WatchedCandidate

if TYPE_CHECKING:
    from nexus2.domain.automation.warrior_engine import WarriorEngine


logger = logging.getLogger(__name__)


# =============================================================================
# POSITION SIZING HELPERS
# =============================================================================


async def calculate_stop_price(
    engine: "WarriorEngine",
    symbol: str,
    entry_price: Decimal,
) -> Tuple[Optional[Decimal], str, Optional[Decimal]]:
    """
    Calculate stop price using consolidation low methodology.
    
    Uses the lowest low of the last 5 candles as the stop basis.
    A downstream cap (base_hit_max_stop_cents) limits the max stop distance
    for base_hit trades to prevent bag holding on wide premarket ranges.
    
    Args:
        engine: The WarriorEngine instance
        symbol: Stock symbol
        entry_price: Entry price for the trade
    
    Returns:
        (mental_stop, stop_method, candle_low) or (None, "failed", None)
    """
    mental_stop = None
    stop_method = "fallback_15c"
    calculated_candle_low = None
    
    if not engine._get_intraday_bars:
        return None, "no_bars_callback", None
    
    try:
        candles = await engine._get_intraday_bars(symbol, "1min", limit=5)
        if candles and len(candles) >= 1:
            # MULTI-CANDLE LOW: Use lowest low of last 5 candles (consolidation support)
            consolidation_low = min(Decimal(str(c.low)) for c in candles)
            entry_candle_low = Decimal(str(candles[-1].low))
            
            # Use consolidation low as support, with 2¢ buffer
            calculated_candle_low = consolidation_low
            mental_stop = consolidation_low - Decimal("0.02")
            stop_method = "consolidation_low"
            
            # Cap stop distance if it exceeds max_stop_pct
            stop_distance_pct = (entry_price - mental_stop) / entry_price
            max_pct = Decimal(str(engine.config.max_stop_pct))
            if stop_distance_pct > max_pct:
                original_stop = mental_stop
                mental_stop = (entry_price * (1 - max_pct)).quantize(Decimal("0.01"))
                stop_method = "consolidation_low_capped"
                logger.warning(
                    f"[Warrior Entry] {symbol}: WIDE STOP CAPPED "
                    f"${original_stop:.2f} → ${mental_stop:.2f} "
                    f"({stop_distance_pct:.1%} → {max_pct:.1%})"
                )
            
            logger.info(
                f"[Warrior Entry] {symbol}: Stop ${mental_stop:.2f} via {stop_method} "
                f"(5-bar low=${consolidation_low:.2f}, entry bar=${entry_candle_low:.2f})"
            )
            
            return mental_stop, stop_method, calculated_candle_low
    except Exception as e:
        logger.warning(f"[Warrior Entry] {symbol}: Entry candle stop calc failed: {e}")
    
    return None, "failed", None


def calculate_position_size(
    engine: "WarriorEngine",
    watched: WatchedCandidate,
    entry_price: Decimal,
    mental_stop: Decimal,
) -> int:
    """
    Calculate position size based on risk per trade.
    
    Args:
        engine: The WarriorEngine instance
        watched: The watched candidate
        entry_price: Entry price
        mental_stop: Stop loss price
    
    Returns:
        Number of shares to buy (0 if invalid)
    """
    symbol = watched.candidate.symbol
    
    # Ensure Decimal arithmetic for risk calculation
    entry_decimal = Decimal(str(entry_price)) if not isinstance(entry_price, Decimal) else entry_price
    mental_stop_decimal = Decimal(str(mental_stop)) if not isinstance(mental_stop, Decimal) else mental_stop
    risk_per_share = entry_decimal - mental_stop_decimal
    
    if risk_per_share <= 0:
        logger.warning(f"[Warrior Entry] {symbol}: Invalid risk calculation")
        return 0
    
    shares = int(engine.config.risk_per_trade / risk_per_share)
    
    # Cap by max capital
    max_shares = int(engine.config.max_capital / entry_decimal)
    shares = min(shares, max_shares)
    
    # Apply testing limits
    if engine.config.max_shares_per_trade is not None:
        shares = min(shares, engine.config.max_shares_per_trade)
    if engine.config.max_value_per_trade is not None:
        max_by_value = int(engine.config.max_value_per_trade / entry_decimal)
        shares = min(shares, max_by_value)
    
    # ICEBREAKER: 50% size for high-score Chinese stocks
    # (Ross Cameron, Jan 20 TWWG: "breaking the ice with smaller positions")
    if getattr(watched.candidate, 'is_icebreaker', False):
        original_shares = shares
        shares = max(1, int(shares * 0.5))  # 50% reduction
        logger.info(
            f"[Warrior Entry] {symbol}: ICEBREAKER 50% size ({original_shares} -> {shares} shares)"
        )
    
    return shares


def calculate_profit_target(
    entry_price: Decimal,
    mental_stop_cents: Decimal,
    profit_target_r: Decimal,
) -> Decimal:
    """
    Calculate profit target based on entry price and R multiple.
    
    Args:
        entry_price: Entry price
        mental_stop_cents: Stop distance in cents
        profit_target_r: R multiple for profit target
    
    Returns:
        Target price
    """
    return entry_price + (mental_stop_cents / 100 * profit_target_r)


def calculate_limit_price(
    entry_price: Decimal,
    current_ask: Optional[Decimal],
) -> Decimal:
    """
    Calculate limit price for order submission.
    
    Uses current ask if available, otherwise falls back to percentage offset.
    
    Args:
        entry_price: Entry price
        current_ask: Current ask price from quote (if available)
    
    Returns:
        Limit price for order
    """
    limit_offset = Decimal("0.05")  # 5 cents offset when ask is available
    
    if current_ask and current_ask > 0:
        # Use current ask price (more accurate for fast movers)
        limit_price = (current_ask + limit_offset).quantize(Decimal("0.01"))
        logger.info(
            f"Limit based on ask ${current_ask:.2f} + ${limit_offset} = ${limit_price:.2f}"
        )
    else:
        # Fallback: 1.5% above entry price (scales better for runners)
        # This handles pre-market when Alpaca doesn't provide bid/ask
        fallback_multiplier = Decimal("1.015")  # 1.5% above entry
        limit_price = (entry_price * fallback_multiplier).quantize(Decimal("0.01"))
        logger.info(
            f"Limit based on entry ${entry_price:.2f} x 1.015 = ${limit_price:.2f} (no bid/ask)"
        )
    
    return limit_price
