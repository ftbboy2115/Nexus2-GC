"""
Pattern Detection Service

Ross Cameron pattern detection for Warrior Trading.
Currently supports:
- Inverted Head & Shoulders (bullish reversal)
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class InvertedHSPattern:
    r"""
    Inverted Head & Shoulders pattern data.
    
    Bullish reversal pattern:
        neckline ──────────────────
           /\                    /\
          /  \                  /  \
         /    \                /    \
        /      \     /\       /      \
    LS           \  /  \  RS          breakout
                 \/    \/
                HEAD
    """
    left_shoulder_low: Decimal
    head_low: Decimal
    right_shoulder_low: Decimal
    neckline: Decimal
    confidence: float  # 0.0-1.0 based on symmetry and pattern quality
    
    # Additional context
    left_shoulder_idx: int  # Candle index of LS
    head_idx: int  # Candle index of Head
    right_shoulder_idx: int  # Candle index of RS
    
    def is_breakout(self, current_price: Decimal, buffer_cents: int = 5) -> bool:
        """Check if price has broken above neckline with buffer."""
        buffer = Decimal(str(buffer_cents)) / 100
        return current_price > self.neckline + buffer


class PatternService:
    """
    Pattern detection service for Warrior Trading methodology.
    
    Provides pattern detection for:
    - Inverted Head & Shoulders (bullish reversal)
    """
    
    def detect_inverted_hs(
        self,
        candles: List[Dict[str, Any]],
        lookback: int = 20,
    ) -> Optional[InvertedHSPattern]:
        """
        Detect inverted Head & Shoulders pattern in recent candles.
        
        Pattern rules (from Ross Cameron methodology):
        - Head must be the lowest of 3 swing lows
        - Right shoulder must be higher than Head (shallower pullback)
        - Left and Right shoulders should be roughly symmetric
        - Neckline connects the highs between shoulders and head
        
        Args:
            candles: List of candle dicts with 'high', 'low', 'close', 'volume'
            lookback: Number of candles to analyze
            
        Returns:
            InvertedHSPattern if detected, None otherwise
        """
        if not candles or len(candles) < 10:
            logger.debug("[Pattern] Not enough candles for inverted H&S detection")
            return None
        
        # Use only recent candles within lookback
        recent = candles[-lookback:] if len(candles) > lookback else candles
        
        # Find swing lows (local minima) - use window=2 for better sensitivity
        swing_lows = self._find_swing_lows(recent, window=2)
        
        if len(swing_lows) < 3:
            logger.debug(f"[Pattern] Only found {len(swing_lows)} swing lows, need at least 3")
            return None
        
        # Try to form inverted H&S with the 3 most recent swing lows
        # Pattern: LS, Head (lowest), RS
        for i in range(len(swing_lows) - 2):
            ls_idx, ls_low = swing_lows[i]
            
            for j in range(i + 1, len(swing_lows) - 1):
                head_idx, head_low = swing_lows[j]
                
                for k in range(j + 1, len(swing_lows)):
                    rs_idx, rs_low = swing_lows[k]
                    
                    # Validate pattern
                    pattern = self._validate_inverted_hs(
                        recent,
                        ls_idx, ls_low,
                        head_idx, head_low, 
                        rs_idx, rs_low
                    )
                    
                    if pattern:
                        return pattern
        
        return None
    
    def _find_swing_lows(
        self,
        candles: List[Dict[str, Any]],
        window: int = 3,
    ) -> List[Tuple[int, Decimal]]:
        """
        Find swing lows (local minima) in candle data.
        
        A swing low is a candle with lower 'low' than the surrounding candles.
        
        Args:
            candles: List of candle dicts
            window: Number of candles on each side to compare
            
        Returns:
            List of (index, low_price) tuples
        """
        swing_lows = []
        
        for i in range(window, len(candles) - window):
            current_low = Decimal(str(candles[i].get('low', 0)))
            
            is_swing_low = True
            for j in range(i - window, i):
                if Decimal(str(candles[j].get('low', 0))) <= current_low:
                    is_swing_low = False
                    break
            
            if is_swing_low:
                for j in range(i + 1, i + window + 1):
                    if Decimal(str(candles[j].get('low', 0))) <= current_low:
                        is_swing_low = False
                        break
            
            if is_swing_low:
                swing_lows.append((i, current_low))
        
        return swing_lows
    
    def _find_swing_highs(
        self,
        candles: List[Dict[str, Any]],
        start_idx: int,
        end_idx: int,
    ) -> List[Tuple[int, Decimal]]:
        """
        Find swing highs (local maxima) between two indices.
        
        Args:
            candles: List of candle dicts
            start_idx: Start index (inclusive)
            end_idx: End index (inclusive)
            
        Returns:
            List of (index, high_price) tuples
        """
        swing_highs = []
        
        for i in range(start_idx + 1, end_idx):
            current_high = Decimal(str(candles[i].get('high', 0)))
            prev_high = Decimal(str(candles[i - 1].get('high', 0)))
            next_high = Decimal(str(candles[i + 1].get('high', 0))) if i + 1 <= end_idx else Decimal('0')
            
            if current_high > prev_high and current_high >= next_high:
                swing_highs.append((i, current_high))
        
        return swing_highs
    
    def _validate_inverted_hs(
        self,
        candles: List[Dict[str, Any]],
        ls_idx: int,
        ls_low: Decimal,
        head_idx: int,
        head_low: Decimal,
        rs_idx: int,
        rs_low: Decimal,
    ) -> Optional[InvertedHSPattern]:
        """
        Validate if the three swing lows form a valid inverted H&S pattern.
        
        Validation rules:
        1. Head must be lowest of the three
        2. Right shoulder must be higher than head (shallower pullback showing buying pressure)
        3. Left and right shoulders should be roughly symmetric (within 30% tolerance)
        4. Proper spacing between the three points
        
        Args:
            candles: List of candle dicts
            ls_idx, ls_low: Left shoulder index and price
            head_idx, head_low: Head index and price
            rs_idx, rs_low: Right shoulder index and price
            
        Returns:
            InvertedHSPattern if valid, None otherwise
        """
        # Rule 1: Head must be the lowest
        if head_low >= ls_low or head_low >= rs_low:
            return None
        
        # Rule 2: Right shoulder must be higher than head
        # (This shows buying pressure increasing - shallower pullback)
        if rs_low <= head_low:
            return None
        
        # Rule 3: Symmetry check - LS and RS should be within 30% of each other
        ls_depth = ls_low - head_low  # How far LS is from head
        rs_depth = rs_low - head_low  # How far RS is from head
        
        if ls_depth == 0:
            return None  # Avoid division by zero
        
        symmetry_ratio = float(rs_depth) / float(ls_depth)
        symmetry_tolerance = 0.40  # 40% tolerance (relaxed for real-world patterns)
        
        if not (1 - symmetry_tolerance <= symmetry_ratio <= 1 + symmetry_tolerance):
            logger.debug(
                f"[Pattern] Inverted H&S rejected - symmetry {symmetry_ratio:.2f} "
                f"outside tolerance (0.60-1.40)"
            )
            return None
        
        # Rule 4: Proper spacing (at least 2 candles between each point)
        if head_idx - ls_idx < 2 or rs_idx - head_idx < 2:
            return None
        
        # Calculate neckline (connect highs between LS-Head and Head-RS)
        # Find the highest high between LS and Head
        ls_head_highs = self._find_swing_highs(candles, ls_idx, head_idx)
        # Find the highest high between Head and RS  
        head_rs_highs = self._find_swing_highs(candles, head_idx, rs_idx)
        
        # Neckline is the average of the two highest highs, or the lower of the two
        left_neckline = max([h[1] for h in ls_head_highs]) if ls_head_highs else Decimal('0')
        right_neckline = max([h[1] for h in head_rs_highs]) if head_rs_highs else Decimal('0')
        
        if left_neckline == 0 or right_neckline == 0:
            # Fallback: use the max high between the shoulders
            neckline = max(
                Decimal(str(candles[i].get('high', 0)))
                for i in range(ls_idx, rs_idx + 1)
            )
        else:
            # Use the lower of the two neckline points for conservative entry
            neckline = min(left_neckline, right_neckline)
        
        # Calculate confidence score (0.0 - 1.0)
        # Based on: symmetry, depth ratio, volume patterns
        confidence = self._calculate_confidence(
            ls_low, head_low, rs_low, symmetry_ratio
        )
        
        logger.info(
            f"[Pattern] Inverted H&S DETECTED - LS=${ls_low:.2f} @ idx {ls_idx}, "
            f"Head=${head_low:.2f} @ idx {head_idx}, RS=${rs_low:.2f} @ idx {rs_idx}, "
            f"Neckline=${neckline:.2f}, Confidence={confidence:.2f}"
        )
        
        return InvertedHSPattern(
            left_shoulder_low=ls_low,
            head_low=head_low,
            right_shoulder_low=rs_low,
            neckline=neckline,
            confidence=confidence,
            left_shoulder_idx=ls_idx,
            head_idx=head_idx,
            right_shoulder_idx=rs_idx,
        )
    
    def _calculate_confidence(
        self,
        ls_low: Decimal,
        head_low: Decimal,
        rs_low: Decimal,
        symmetry_ratio: float,
    ) -> float:
        """
        Calculate confidence score for the pattern.
        
        Factors:
        - Symmetry: How equal are LS and RS depths
        - RS higher than LS: Shows increasing buying pressure
        - Head depth: Deeper head = stronger reversal signal
        """
        # Start with base confidence
        confidence = 0.5
        
        # Symmetry bonus (perfect = 1.0, max bonus = 0.25)
        symmetry_score = 1.0 - abs(1.0 - symmetry_ratio)
        confidence += symmetry_score * 0.25
        
        # RS higher than LS bonus (shows buying pressure increasing)
        if rs_low > ls_low:
            # The more RS is above LS, the better (up to 10%)
            rs_lift = float((rs_low - ls_low) / ls_low) * 100
            confidence += min(rs_lift / 10, 0.15)  # Max 0.15 bonus
        
        # Pattern clarity (head significantly lower than shoulders)
        avg_shoulder = (float(ls_low) + float(rs_low)) / 2
        head_depth_pct = (avg_shoulder - float(head_low)) / avg_shoulder * 100
        if head_depth_pct >= 2:  # At least 2% deeper
            confidence += min(head_depth_pct / 10, 0.10)  # Max 0.10 bonus
        
        return min(confidence, 1.0)


# Singleton instance
_pattern_service: Optional[PatternService] = None


def get_pattern_service() -> PatternService:
    """Get or create singleton PatternService."""
    global _pattern_service
    if _pattern_service is None:
        _pattern_service = PatternService()
    return _pattern_service
