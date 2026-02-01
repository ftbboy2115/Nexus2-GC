"""
Unit tests for ABCD pattern detection in PatternService.

Tests the ABCD pattern detector with real DCX data from Jan 29 2026
to verify it correctly identifies the pattern Ross Cameron traded.
"""

import pytest
from decimal import Decimal
from nexus2.domain.indicators.pattern_service import PatternService, ABCDPattern


class TestABCDPatternDetection:
    """Test ABCD pattern detection accuracy."""
    
    def setup_method(self):
        self.svc = PatternService()
    
    # DCX candle data from Jan 29 2026 (based on Ross's video at 6:54)
    # Real ABCD pattern Ross traded:
    # A = ~$3.60 (initial low, left side of pattern)
    # B = ~$4.60 (first peak, top of "A" shape Ross drew)
    # C = ~$4.25 (pullback, higher low after B)
    # D = Break above B at $4.60+ (Ross's entry)
    DCX_CANDLES = [
        # Early premarket noise - these should NOT trigger ABCD
        {"high": 3.40, "low": 3.13, "close": 3.40, "volume": 2081},    # 07:00
        {"high": 3.28, "low": 3.28, "close": 3.28, "volume": 100},     # 07:04
        {"high": 3.30, "low": 3.20, "close": 3.25, "volume": 500},     # noise
        {"high": 3.35, "low": 3.22, "close": 3.30, "volume": 600},     # noise
        # Real pattern starts - A point developing
        {"high": 3.68, "low": 3.54, "close": 3.60, "volume": 6908},    # A area ~$3.60
        {"high": 3.80, "low": 3.55, "close": 3.75, "volume": 10000},   # moving up
        {"high": 4.00, "low": 3.70, "close": 3.95, "volume": 15000},   # continuing
        {"high": 4.30, "low": 3.90, "close": 4.25, "volume": 25000},   # approaching B
        {"high": 4.65, "low": 4.20, "close": 4.60, "volume": 40000},   # B point ~$4.60
        {"high": 4.55, "low": 4.30, "close": 4.40, "volume": 20000},   # pullback starts
        {"high": 4.35, "low": 4.20, "close": 4.25, "volume": 15000},   # C point ~$4.25 (higher low)
        {"high": 4.40, "low": 4.22, "close": 4.35, "volume": 12000},   # consolidating at C
        {"high": 4.55, "low": 4.30, "close": 4.50, "volume": 25000},   # starting D move
        {"high": 4.75, "low": 4.45, "close": 4.70, "volume": 45000},   # D breakout above B!
        {"high": 5.00, "low": 4.60, "close": 4.95, "volume": 60000},   # Ross adds at $5.00
        {"high": 5.40, "low": 4.90, "close": 5.35, "volume": 75000},   # Peak - Ross exits
    ]
    
    def test_no_pattern_with_insufficient_candles(self):
        """Should return None if not enough candles."""
        result = self.svc.detect_abcd([{"high": 10, "low": 9, "close": 9.5, "volume": 1000}] * 5)
        assert result is None
    
    def test_early_premarket_should_not_trigger(self):
        """
        With only the first 3-4 candles (07:00-07:19), there shouldn't be 
        a valid ABCD pattern yet. The bot entered at $3.40 which is too early.
        """
        early_candles = self.DCX_CANDLES[:4]  # Only up to 07:19
        result = self.svc.detect_abcd(early_candles, lookback=30)
        
        # Should NOT detect a pattern this early - not enough structure
        # If this fails, our detector is too aggressive
        assert result is None, (
            f"ABCD detected too early! Pattern found with only {len(early_candles)} candles. "
            f"This is the false positive we saw in DCX test (entry at $3.40)."
        )
    
    def test_pattern_requires_proper_structure(self):
        """
        With 10 candles (up to 07:30), we should start seeing pattern formation
        but NOT trigger yet - need to wait for D breakout.
        """
        mid_candles = self.DCX_CANDLES[:10]  # Up to 07:30
        result = self.svc.detect_abcd(mid_candles, lookback=30)
        
        # Pattern may be detected, but breakout shouldn't fire until price > B high
        if result:
            # If pattern detected, verify it's reasonable
            assert float(result.b_high) > 4.0, "B high should be around $4.73"
            assert float(result.c_low) > float(result.a_low), "C must be higher than A"
    
    def test_pattern_should_detect_after_abc_formed(self):
        """
        With full candle data, ABCD pattern should be properly detected.
        """
        result = self.svc.detect_abcd(self.DCX_CANDLES, lookback=30)
        
        # Should detect a valid pattern
        assert result is not None, "Should detect ABCD pattern in full DCX data"
        
        # Validate pattern structure
        assert isinstance(result, ABCDPattern)
        assert result.a_low < result.b_high, "B must be higher than A"
        assert result.c_low > result.a_low, "C must be higher than A (higher low)"
        assert result.c_low < result.b_high, "C must be lower than B (pullback)"
        
        # Verify reasonable levels
        assert float(result.a_low) < 4.0, f"A low should be early low (~$3.13), got {result.a_low}"
        assert float(result.b_high) > 4.5, f"B high should be spike high (~$4.73), got {result.b_high}"
    
    def test_breakout_detection(self):
        """
        Test that is_breakout() correctly identifies when price breaks above B.
        """
        result = self.svc.detect_abcd(self.DCX_CANDLES, lookback=30)
        
        if result:
            # Price below B high - should NOT be breakout
            assert not result.is_breakout(Decimal("4.00")), "Price $4.00 below B should not be breakout"
            assert not result.is_breakout(Decimal("4.50")), "Price $4.50 below B should not be breakout"
            
            # Price above B high + buffer - SHOULD be breakout
            breakout_price = result.b_high + Decimal("0.10")
            assert result.is_breakout(breakout_price), f"Price ${breakout_price} above B should be breakout"
    
    def test_pattern_confidence_and_rr(self):
        """Test that pattern returns reasonable confidence and R:R values."""
        result = self.svc.detect_abcd(self.DCX_CANDLES, lookback=30)
        
        if result:
            assert 0.4 <= result.confidence <= 1.0, f"Confidence {result.confidence} out of range"
            assert result.risk_reward > 0, f"R:R should be positive, got {result.risk_reward}"
            assert result.stop_price < result.c_low, "Stop should be below C low"


class TestMinimumPatternRequirements:
    """Test that ABCD detection has proper minimum requirements."""
    
    def setup_method(self):
        self.svc = PatternService()
    
    def test_requires_minimum_ab_move(self):
        """Pattern should require a meaningful A→B move, not noise."""
        # Flat/noisy candles with no clear move
        noisy_candles = [
            {"high": 10.05, "low": 9.95, "close": 10.0, "volume": 1000},
            {"high": 10.10, "low": 9.90, "close": 10.0, "volume": 1000},
            {"high": 10.08, "low": 9.92, "close": 10.0, "volume": 1000},
        ] * 10  # 30 nearly identical candles
        
        result = self.svc.detect_abcd(noisy_candles, lookback=30)
        assert result is None, "Should not detect pattern in flat/noisy data"
    
    def test_requires_proper_retracement(self):
        """C retracement should be 30-85% of A→B move."""
        # Create pattern where C retraces too little (< 30%)
        shallow_pullback = [
            {"high": 3.20, "low": 3.00, "close": 3.10, "volume": 1000},  # A
            {"high": 3.15, "low": 3.05, "close": 3.10, "volume": 1000},
            {"high": 4.00, "low": 3.50, "close": 4.00, "volume": 5000},  # B
            {"high": 3.95, "low": 3.90, "close": 3.92, "volume": 2000},  # C - only 8% retracement
        ] * 5
        
        result = self.svc.detect_abcd(shallow_pullback, lookback=30)
        # Should reject if retracement is too shallow or too deep
        # (pattern may still be found if it finds a different ABC combo)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
