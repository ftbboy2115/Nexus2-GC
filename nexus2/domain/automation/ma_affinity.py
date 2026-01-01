"""
MA Affinity Analysis Module

KK-style consolidation detection and MA affinity analysis.
Determines whether a stock respects the 10 or 20 MA during consolidation
to inform trailing stop selection.

Key concepts:
- Consolidation detection: Find where the pre-breakout base started
- MA "surfing": Count touches/bounces off 10 vs 20 MA
- Violations: Count closes below MA followed by recovery (choppiness indicator)
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class MAAffinityData:
    """
    MA affinity analysis result.
    
    Used to determine which MA a stock was "surfing" during consolidation,
    which informs trailing stop selection (10 vs 20 MA).
    """
    affinity_ma: str = "unknown"  # "10", "20", or "unknown"
    
    # Touch counts (price within 1% of MA)
    ema_10_touches: int = 0
    sma_10_touches: int = 0
    ema_20_touches: int = 0
    sma_20_touches: int = 0
    
    # Violation count (close below MA then recovered = choppy)
    violations: int = 0
    
    # ADR for fallback selection
    adr_percent: float = 0.0
    
    # Consolidation period detected
    consolidation_days: int = 0
    
    def to_dict(self) -> dict:
        return {
            "affinity_ma": self.affinity_ma,
            "ema_10_touches": self.ema_10_touches,
            "sma_10_touches": self.sma_10_touches,
            "ema_20_touches": self.ema_20_touches,
            "sma_20_touches": self.sma_20_touches,
            "violations": self.violations,
            "adr_percent": self.adr_percent,
            "consolidation_days": self.consolidation_days,
        }


def detect_consolidation_start(
    prices: List[dict],
    min_move_percent: float = 30.0,
    max_lookback_weeks: int = 12,
) -> int:
    """
    Detect where the pre-breakout consolidation started.
    
    KK methodology: Look for a significant move (30%+ gain) followed by
    an "orderly pullback" consolidation of 2-8 weeks.
    
    Args:
        prices: List of price bars, most recent first (reverse chronological)
                Each bar: {"close": float, "high": float, "low": float, "date": str}
        min_move_percent: Minimum % move to consider "significant" (default 30%)
        max_lookback_weeks: Maximum weeks to look back (default 12 = 60 trading days)
        
    Returns:
        Number of trading days of consolidation (0 if not detected)
    """
    if not prices or len(prices) < 20:
        return 0
    
    max_days = min(len(prices), max_lookback_weeks * 5)  # 5 trading days per week
    
    # Start from entry (most recent) and walk backwards
    entry_price = float(prices[0]["close"])
    
    consolidation_days = 0
    found_move_start = False
    
    for i in range(1, max_days):
        bar = prices[i]
        price = float(bar["close"])
        
        # Calculate move from this point to entry
        move_percent = ((entry_price - price) / price) * 100
        
        # If we find where price was 30%+ lower, that's where the move started
        if move_percent >= min_move_percent:
            consolidation_days = i
            found_move_start = True
            break
    
    if not found_move_start:
        # No significant move found, use max 8 weeks (40 trading days)
        consolidation_days = min(len(prices) - 1, 40)
    
    logger.debug(f"[MAAffinity] Consolidation detected: {consolidation_days} days")
    return consolidation_days


def count_ma_touches(
    prices: List[dict],
    ma_values: List[float],
    touch_threshold: float = 0.01,  # 1% of price
) -> int:
    """
    Count how many times price touched (came within threshold of) MA values.
    
    A "touch" = price low went within 1% of MA value during the day.
    
    Args:
        prices: List of price bars with "low", "close" fields
        ma_values: List of MA values corresponding to each price bar
        touch_threshold: Fraction of price to count as "touch" (0.01 = 1%)
        
    Returns:
        Number of touches
    """
    if len(prices) != len(ma_values):
        return 0
    
    touches = 0
    for i, bar in enumerate(prices):
        if ma_values[i] is None:
            continue
            
        low = float(bar.get("low", bar.get("close", 0)))
        ma = float(ma_values[i])
        
        if ma <= 0:
            continue
        
        # Touch = price low came within threshold of MA
        threshold_value = ma * touch_threshold
        if abs(low - ma) <= threshold_value:
            touches += 1
    
    return touches


def count_violations(
    prices: List[dict],
    ma_values: List[float],
) -> int:
    """
    Count MA violations (close below MA followed by recovery above).
    
    A violation suggests choppy price action / poor MA respect.
    2+ violations = choppy character → use wider 20 MA for trailing.
    
    Args:
        prices: List of price bars with "close" field
        ma_values: List of MA values (use lower of 10 EMA/SMA)
        
    Returns:
        Number of violations
    """
    if len(prices) < 2 or len(prices) != len(ma_values):
        return 0
    
    violations = 0
    below_ma = False
    
    for i, bar in enumerate(prices):
        if ma_values[i] is None:
            continue
            
        close = float(bar["close"])
        ma = float(ma_values[i])
        
        if close < ma:
            below_ma = True
        elif below_ma and close >= ma:
            # Recovered from below - count as violation
            violations += 1
            below_ma = False
    
    return violations


async def analyze_ma_affinity(
    symbol: str,
    prices: List[dict],
    get_ema: callable,
    get_sma: callable,
    get_adr_percent: callable,
    consolidation_days: int = None,
) -> MAAffinityData:
    """
    Analyze MA affinity for a symbol during its consolidation period.
    
    Determines whether price "surfed" the 10 or 20 MA, which informs
    trailing stop selection.
    
    Args:
        symbol: Stock symbol
        prices: List of price bars (most recent first)
        get_ema: Async callable (symbol, period) -> value
        get_sma: Async callable (symbol, period) -> value
        get_adr_percent: Async callable (symbol, period) -> ADR%
        consolidation_days: Override consolidation period (auto-detect if None)
        
    Returns:
        MAAffinityData with affinity determination
    """
    result = MAAffinityData()
    
    if not prices or len(prices) < 10:
        logger.warning(f"[MAAffinity] Insufficient price data for {symbol}")
        return result
    
    # Detect consolidation period if not provided
    if consolidation_days is None:
        consolidation_days = detect_consolidation_start(prices)
    
    result.consolidation_days = consolidation_days
    
    # Limit to consolidation period
    analysis_prices = prices[:consolidation_days] if consolidation_days > 0 else prices[:40]
    
    # Get current MA values for touch detection
    # Note: We need historical MA values, but for now use current as approximation
    # TODO: Enhance with historical MA calculation
    try:
        ema_10 = await get_ema(symbol, 10) if get_ema else None
        sma_10 = await get_sma(symbol, 10) if get_sma else None
        ema_20 = await get_ema(symbol, 20) if get_ema else None
        sma_20 = await get_sma(symbol, 20) if get_sma else None
        
        # Create approximate MA value lists (constant for now)
        ema_10_values = [ema_10] * len(analysis_prices) if ema_10 else []
        sma_10_values = [sma_10] * len(analysis_prices) if sma_10 else []
        ema_20_values = [ema_20] * len(analysis_prices) if ema_20 else []
        sma_20_values = [sma_20] * len(analysis_prices) if sma_20 else []
        
        # Count touches for each MA
        if ema_10_values:
            result.ema_10_touches = count_ma_touches(analysis_prices, ema_10_values)
        if sma_10_values:
            result.sma_10_touches = count_ma_touches(analysis_prices, sma_10_values)
        if ema_20_values:
            result.ema_20_touches = count_ma_touches(analysis_prices, ema_20_values)
        if sma_20_values:
            result.sma_20_touches = count_ma_touches(analysis_prices, sma_20_values)
        
        # Count violations using lower of 10 EMA/SMA
        if ema_10_values or sma_10_values:
            lower_10_values = []
            for i in range(len(analysis_prices)):
                e10 = ema_10_values[i] if i < len(ema_10_values) else None
                s10 = sma_10_values[i] if i < len(sma_10_values) else None
                if e10 and s10:
                    lower_10_values.append(min(float(e10), float(s10)))
                elif e10:
                    lower_10_values.append(float(e10))
                elif s10:
                    lower_10_values.append(float(s10))
                else:
                    lower_10_values.append(None)
            
            result.violations = count_violations(analysis_prices, lower_10_values)
        
    except Exception as e:
        logger.warning(f"[MAAffinity] Error getting MA data for {symbol}: {e}")
    
    # Get ADR% for fallback
    try:
        if get_adr_percent:
            adr = await get_adr_percent(symbol, 20)
            result.adr_percent = float(adr) if adr else 0.0
    except Exception as e:
        logger.warning(f"[MAAffinity] Error getting ADR for {symbol}: {e}")
    
    # Determine affinity
    touches_10 = result.ema_10_touches + result.sma_10_touches
    touches_20 = result.ema_20_touches + result.sma_20_touches
    
    if touches_10 > touches_20 * 1.5:  # 50% more touches = clear affinity
        result.affinity_ma = "10"
    elif touches_20 > touches_10 * 1.5:
        result.affinity_ma = "20"
    else:
        result.affinity_ma = "unknown"
    
    logger.info(
        f"[MAAffinity] {symbol}: affinity={result.affinity_ma}, "
        f"touches_10={touches_10}, touches_20={touches_20}, "
        f"violations={result.violations}, ADR={result.adr_percent:.1f}%"
    )
    
    return result


def select_trailing_ma_from_affinity(affinity: MAAffinityData) -> str:
    """
    Select trailing MA type based on affinity analysis.
    
    Priority order (KK-style):
    1. MA affinity from consolidation surfing
    2. Choppiness (violations) → wider MA
    3. ADR% threshold (5%)
    
    Returns:
        "LOWER_10" or "LOWER_20"
    """
    # Priority 1: Known affinity
    if affinity.affinity_ma == "10":
        return "LOWER_10"
    elif affinity.affinity_ma == "20":
        return "LOWER_20"
    
    # Priority 2: Choppy stocks get wider MA
    if affinity.violations >= 2:
        return "LOWER_20"
    
    # Priority 3: ADR-based (default logic)
    if affinity.adr_percent >= 5.0:
        return "LOWER_10"  # Fast mover
    else:
        return "LOWER_20"  # Slower stock
