"""
Stop Calculator

Calculates technical stop levels using Ross Cameron methodology:
- Swing low (primary)
- Below VWAP
- Below 9 EMA
"""

from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
import logging

from .technical_service import get_technical_service

logger = logging.getLogger(__name__)


class StopCalculator:
    """
    Calculate technical stop levels for Warrior positions.
    
    Stop priority (highest valid wins):
    1. Swing low (lowest low of last N candles) - 2¢ buffer
    2. Below VWAP - 3¢ buffer
    3. Below 9 EMA - 2¢ buffer
    4. Fallback: 2% below entry
    """
    
    def __init__(self):
        self.technical = get_technical_service()
    
    def calculate_stop(
        self,
        candles: List[Dict[str, Any]],
        entry_price: Decimal,
        method: str = "swing_low",
    ) -> Optional[Decimal]:
        """
        Calculate stop price using specified method.
        
        Args:
            candles: List of candle dicts
            entry_price: Entry price for the position
            method: One of "swing_low", "vwap", "ema", "fallback"
        
        Returns:
            Stop price or None if calculation fails
        """
        if not candles:
            return None
        
        if method == "swing_low":
            swing_low = self.technical.get_swing_low(candles, lookback=5)
            if swing_low and swing_low < entry_price:
                return swing_low - Decimal("0.02")  # 2¢ buffer below
        
        elif method == "vwap":
            snapshot = self.technical.get_snapshot("", candles, entry_price)
            if snapshot.vwap and snapshot.vwap < entry_price:
                return snapshot.vwap - Decimal("0.03")  # 3¢ buffer below
        
        elif method == "ema":
            snapshot = self.technical.get_snapshot("", candles, entry_price)
            if snapshot.ema_9 and snapshot.ema_9 < entry_price:
                return snapshot.ema_9 - Decimal("0.02")  # 2¢ buffer below
        
        elif method == "fallback":
            return entry_price * Decimal("0.98")  # 2% below
        
        return None
    
    def get_best_stop(
        self,
        candles: List[Dict[str, Any]],
        entry_price: Decimal,
        symbol: str = "",
    ) -> Tuple[Decimal, str]:
        """
        Get the best (highest valid) stop level.
        
        Ross Cameron's approach: use the tightest technical stop
        that respects proper support levels.
        
        Args:
            candles: List of candle dicts
            entry_price: Entry price
            symbol: Symbol for logging
        
        Returns:
            Tuple of (stop_price, method_used)
        """
        candidates: List[Tuple[Decimal, str]] = []
        
        # 1. Swing Low (primary - Ross uses this most)
        swing_stop = self.calculate_stop(candles, entry_price, "swing_low")
        if swing_stop and swing_stop < entry_price:
            candidates.append((swing_stop, "swing_low"))
        
        # 2. VWAP
        vwap_stop = self.calculate_stop(candles, entry_price, "vwap")
        if vwap_stop and vwap_stop < entry_price:
            candidates.append((vwap_stop, "vwap"))
        
        # 3. 9 EMA
        ema_stop = self.calculate_stop(candles, entry_price, "ema")
        if ema_stop and ema_stop < entry_price:
            candidates.append((ema_stop, "ema"))
        
        if candidates:
            # Return highest (tightest) stop - minimize risk
            best = max(candidates, key=lambda x: x[0])
            logger.debug(
                f"[StopCalc] {symbol}: Candidates {[(str(s), m) for s, m in candidates]}, "
                f"best={best[1]} @ ${best[0]}"
            )
            return best
        
        # Fallback: 2% below entry
        fallback_stop = entry_price * Decimal("0.98")
        logger.debug(f"[StopCalc] {symbol}: No technical stops, using 2% fallback @ ${fallback_stop}")
        return (fallback_stop, "fallback_2pct")
    
    def is_below_stop(
        self,
        current_price: Decimal,
        stop_price: Decimal,
    ) -> bool:
        """Check if current price is below stop (invalidated)."""
        return current_price <= stop_price


# Singleton instance
_stop_calculator: Optional[StopCalculator] = None


def get_stop_calculator() -> StopCalculator:
    """Get or create singleton StopCalculator."""
    global _stop_calculator
    if _stop_calculator is None:
        _stop_calculator = StopCalculator()
    return _stop_calculator
