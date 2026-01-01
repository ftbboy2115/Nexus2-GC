"""
Unit Tests for MA Affinity Module

Tests for KK-style MA affinity analysis:
- MAAffinityData dataclass
- Consolidation detection
- MA touch counting  
- Violation tracking
- MA selection logic
"""

import pytest
from decimal import Decimal
from datetime import date

from nexus2.domain.automation.ma_affinity import (
    MAAffinityData,
    detect_consolidation_start,
    count_ma_touches,
    count_violations,
    select_trailing_ma_from_affinity,
)


# ============================================================================
# MAAffinityData Tests
# ============================================================================

class TestMAAffinityData:
    """Tests for MAAffinityData dataclass."""
    
    def test_default_values(self):
        """Test default MAAffinityData values."""
        affinity = MAAffinityData()
        assert affinity.affinity_ma == "unknown"
        assert affinity.ema_10_touches == 0
        assert affinity.sma_10_touches == 0
        assert affinity.ema_20_touches == 0
        assert affinity.sma_20_touches == 0
        assert affinity.violations == 0
        assert affinity.adr_percent == 0.0
        assert affinity.consolidation_days == 0
    
    def test_with_values(self):
        """Test MAAffinityData with explicit values."""
        affinity = MAAffinityData(
            affinity_ma="10",
            ema_10_touches=5,
            sma_10_touches=3,
            violations=1,
            adr_percent=6.5,
        )
        assert affinity.affinity_ma == "10"
        assert affinity.ema_10_touches == 5
        assert affinity.sma_10_touches == 3
        assert affinity.violations == 1
        assert affinity.adr_percent == 6.5
    
    def test_to_dict(self):
        """Test to_dict method."""
        affinity = MAAffinityData(affinity_ma="20", violations=2)
        d = affinity.to_dict()
        assert d["affinity_ma"] == "20"
        assert d["violations"] == 2
        assert "ema_10_touches" in d


# ============================================================================
# select_trailing_ma_from_affinity Tests
# ============================================================================

class TestSelectTrailingMAFromAffinity:
    """Tests for MA selection priority logic."""
    
    def test_priority_1_explicit_affinity_10(self):
        """Priority 1: Explicit affinity_ma='10' → LOWER_10."""
        affinity = MAAffinityData(affinity_ma="10", adr_percent=3.0)
        result = select_trailing_ma_from_affinity(affinity)
        assert result == "LOWER_10"
    
    def test_priority_1_explicit_affinity_20(self):
        """Priority 1: Explicit affinity_ma='20' → LOWER_20."""
        affinity = MAAffinityData(affinity_ma="20", adr_percent=7.0)
        result = select_trailing_ma_from_affinity(affinity)
        assert result == "LOWER_20"
    
    def test_priority_2_choppy_overrides_adr(self):
        """Priority 2: Choppy (2+ violations) → LOWER_20 even with high ADR."""
        affinity = MAAffinityData(affinity_ma="unknown", violations=2, adr_percent=8.0)
        result = select_trailing_ma_from_affinity(affinity)
        assert result == "LOWER_20"
    
    def test_priority_2_choppy_with_3_violations(self):
        """Priority 2: More violations still → LOWER_20."""
        affinity = MAAffinityData(affinity_ma="unknown", violations=3, adr_percent=10.0)
        result = select_trailing_ma_from_affinity(affinity)
        assert result == "LOWER_20"
    
    def test_priority_3_fast_stock_high_adr(self):
        """Priority 3: High ADR (≥5%) → LOWER_10."""
        affinity = MAAffinityData(affinity_ma="unknown", adr_percent=6.0)
        result = select_trailing_ma_from_affinity(affinity)
        assert result == "LOWER_10"
    
    def test_priority_3_slow_stock_low_adr(self):
        """Priority 3: Low ADR (<5%) → LOWER_20."""
        affinity = MAAffinityData(affinity_ma="unknown", adr_percent=3.5)
        result = select_trailing_ma_from_affinity(affinity)
        assert result == "LOWER_20"
    
    def test_priority_3_borderline_adr(self):
        """Priority 3: Exactly 5% ADR → LOWER_10."""
        affinity = MAAffinityData(affinity_ma="unknown", adr_percent=5.0)
        result = select_trailing_ma_from_affinity(affinity)
        assert result == "LOWER_10"
    
    def test_fallback_zero_adr(self):
        """Fallback: Zero ADR → LOWER_20 (safer default)."""
        affinity = MAAffinityData()
        result = select_trailing_ma_from_affinity(affinity)
        assert result == "LOWER_20"
    
    def test_single_violation_not_choppy(self):
        """1 violation is not choppy, falls through to ADR check."""
        affinity = MAAffinityData(affinity_ma="unknown", violations=1, adr_percent=7.0)
        result = select_trailing_ma_from_affinity(affinity)
        # 1 violation is not choppy, ADR 7% → LOWER_10
        assert result == "LOWER_10"


# ============================================================================
# detect_consolidation_start Tests
# ============================================================================

class TestDetectConsolidationStart:
    """Tests for consolidation detection logic."""
    
    def test_insufficient_data_returns_zero(self):
        """Too few bars → return 0."""
        prices = [{"close": 100.0}] * 5
        result = detect_consolidation_start(prices)
        assert result == 0
    
    def test_empty_prices_returns_zero(self):
        """Empty price history → return 0."""
        result = detect_consolidation_start([])
        assert result == 0
    
    def test_detects_30_percent_move(self):
        """30% move detected → returns consolidation days."""
        # Create 30%+ move: start at 100, end at 130
        # Most recent first (reverse chronological)
        prices = []
        for i in range(60):
            if i < 30:
                prices.append({"close": 130.0})  # Recent - high
            else:
                prices.append({"close": 100.0})  # Earlier - low
        
        result = detect_consolidation_start(prices, min_move_percent=30.0)
        # Should find the move started around day 30
        assert result >= 30
    
    def test_no_big_move_uses_default(self):
        """No 30%+ move → use default 40 day consolidation."""
        # Flat prices
        prices = [{"close": 100.0}] * 60
        result = detect_consolidation_start(prices, min_move_percent=30.0)
        # Should default to 40 days
        assert result == 40


# ============================================================================
# count_ma_touches Tests
# ============================================================================

class TestCountMATouches:
    """Tests for MA touch counting."""
    
    def test_touch_within_threshold(self):
        """Price within 1% of MA counts as touch."""
        # MA at 100, price lows at 99.5, 100.5, 101.0 (all within 1%)
        prices = [
            {"close": 102.0, "low": 99.5},   # 0.5% from 100 = touch
            {"close": 101.0, "low": 100.5},  # 0.5% from 100 = touch
            {"close": 103.0, "low": 101.0},  # 1.0% from 100 = touch
        ]
        ma_values = [100.0, 100.0, 100.0]
        
        count = count_ma_touches(prices, ma_values, touch_threshold=0.01)
        assert count == 3
    
    def test_no_touches_outside_threshold(self):
        """Price > 1% from MA doesn't count as touch."""
        prices = [
            {"close": 110.0, "low": 108.0},  # 8% from 100
            {"close": 115.0, "low": 112.0},  # 12% from 100
        ]
        ma_values = [100.0, 100.0]
        
        count = count_ma_touches(prices, ma_values, touch_threshold=0.01)
        assert count == 0
    
    def test_mismatched_lengths_returns_zero(self):
        """Mismatched prices/ma_values → return 0."""
        prices = [{"close": 100.0}] * 5
        ma_values = [100.0] * 3
        
        count = count_ma_touches(prices, ma_values)
        assert count == 0


# ============================================================================
# count_violations Tests
# ============================================================================

class TestCountViolations:
    """Tests for MA violation counting."""
    
    def test_violation_pattern(self):
        """Close below MA then above = 1 violation."""
        prices = [
            {"close": 95.0},   # Below 100
            {"close": 105.0},  # Above 100 after being below
        ]
        ma_values = [100.0, 100.0]
        
        count = count_violations(prices, ma_values)
        assert count == 1
    
    def test_multiple_violations(self):
        """Multiple below/above cycles = multiple violations."""
        prices = [
            {"close": 95.0},   # Below
            {"close": 105.0},  # Above (1)
            {"close": 95.0},   # Below
            {"close": 105.0},  # Above (2)
        ]
        ma_values = [100.0, 100.0, 100.0, 100.0]
        
        count = count_violations(prices, ma_values)
        assert count == 2
    
    def test_no_violations_always_above(self):
        """Always above MA = 0 violations."""
        prices = [
            {"close": 105.0},
            {"close": 110.0},
            {"close": 108.0},
        ]
        ma_values = [100.0, 100.0, 100.0]
        
        count = count_violations(prices, ma_values)
        assert count == 0
    
    def test_stays_below_no_recovery(self):
        """Below MA but never recovers = 0 violations."""
        prices = [
            {"close": 95.0},
            {"close": 92.0},
            {"close": 90.0},
        ]
        ma_values = [100.0, 100.0, 100.0]
        
        count = count_violations(prices, ma_values)
        assert count == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
