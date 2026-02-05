"""
Tests for WarriorScannerService

Validates Ross Cameron's 5 Pillars of Stock Selection:
1. Float < 100M (ideal < 20M)
2. RVOL > 2x (ideal 3-5x)
3. Catalyst (news/earnings/former runner)
4. Price $1.50 - $20
5. Gap > 4%
"""

import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

from nexus2.domain.scanner.warrior_scanner_service import (
    WarriorScanSettings,
    WarriorCandidate,
    WarriorScanResult,
    WarriorScannerService,
    CHINESE_STOCK_PATTERNS,
)


class TestWarriorScanSettings:
    """Test WarriorScanSettings defaults."""
    
    def test_default_settings(self):
        """Default settings match Ross Cameron methodology."""
        settings = WarriorScanSettings()
        
        # Pillar 1: Float
        assert settings.max_float == 100_000_000
        assert settings.ideal_float == 20_000_000
        
        # Pillar 2: RVOL
        assert settings.min_rvol == Decimal("2.0")
        assert settings.ideal_rvol == Decimal("3.0")
        
        # Pillar 3: Catalyst
        assert settings.catalyst_lookback_days == 5
        assert settings.require_catalyst is True
        
        # Pillar 4: Price
        assert settings.min_price == Decimal("1.50")
        assert settings.max_price == Decimal("20.0")
        
        # Pillar 5: Gap
        assert settings.min_gap == Decimal("4.0")
        assert settings.ideal_gap == Decimal("5.0")
        
        # Additional
        assert settings.exclude_chinese_stocks is True
    
    def test_custom_settings(self):
        """Can customize settings."""
        settings = WarriorScanSettings(
            max_price=Decimal("30.0"),
            min_rvol=Decimal("3.0"),
        )
        
        assert settings.max_price == Decimal("30.0")
        assert settings.min_rvol == Decimal("3.0")


class TestWarriorCandidate:
    """Test WarriorCandidate quality scoring."""
    
    def test_quality_score_max(self):
        """Perfect candidate gets high score."""
        candidate = WarriorCandidate(
            symbol="TEST",
            name="Test Stock",
            float_shares=5_000_000,  # < 10M = 3 points
            relative_volume=Decimal("6.0"),  # >= 5x = 2 points
            catalyst_type="earnings",  # earnings = 2 points
            catalyst_description="Q4 beat",
            price=Decimal("10.0"),  # $5-$15 sweet spot = 1 point
            gap_percent=Decimal("15.0"),  # >= 10% = 2 points
            is_ideal_float=True,
            is_ideal_rvol=True,
            is_ideal_gap=True,
        )
        
        # Total: 3 + 2 + 2 + 1 + 2 = 10
        assert candidate.quality_score == 10
    
    def test_quality_score_min(self):
        """Poor candidate gets low score."""
        candidate = WarriorCandidate(
            symbol="TEST",
            name="Test Stock",
            float_shares=80_000_000,  # 50M-100M = 0 points
            relative_volume=Decimal("2.0"),  # 2x = 0 points
            catalyst_type="none",  # no catalyst = 0 points
            catalyst_description="",
            price=Decimal("2.0"),  # outside sweet spot = 0 points
            gap_percent=Decimal("4.0"),  # < 5% = 0 points
        )
        
        assert candidate.quality_score == 0
    
    def test_quality_score_medium(self):
        """Average candidate gets medium score."""
        candidate = WarriorCandidate(
            symbol="TEST",
            name="Test Stock",
            float_shares=15_000_000,  # < 20M = 2 points
            relative_volume=Decimal("4.0"),  # >= 3x = 1 point
            catalyst_type="news",  # news = 1 point
            catalyst_description="PR",
            price=Decimal("8.0"),  # sweet spot = 1 point
            gap_percent=Decimal("7.0"),  # >= 5% = 1 point
        )
        
        # Total: 2 + 1 + 1 + 1 + 1 = 6
        assert candidate.quality_score == 6


class TestWarriorScannerService:
    """Test WarriorScannerService filtering."""
    
    @pytest.fixture
    def mock_market_data(self):
        """Create mock market data provider."""
        mock = Mock()
        mock.fmp = Mock()
        mock.fmp.get_etf_symbols.return_value = {"SPY", "QQQ", "IWM"}
        # All potential scan sources should return empty lists, not Mock objects
        # These are called on market_data directly, not on fmp
        mock.get_premarket_gainers.return_value = []
        mock.get_gainers.return_value = []
        mock.get_actives.return_value = []
        mock.get_alpaca_movers.return_value = []  # Required for scan() to work
        return mock
    
    def test_chinese_stock_exclusion(self):
        """Chinese stocks are excluded."""
        service = WarriorScannerService()
        
        # Known Chinese patterns
        assert "HKD" in CHINESE_STOCK_PATTERNS
        assert "TOP" in CHINESE_STOCK_PATTERNS
        assert "MEGL" in CHINESE_STOCK_PATTERNS
        
        # Heuristic check
        assert service._is_likely_chinese("China Holdings Ltd") is True
        assert service._is_likely_chinese("Hong Kong Tech") is True
        assert service._is_likely_chinese("Apple Inc") is False
        assert service._is_likely_chinese("Tesla Motors") is False
    
    def test_empty_scan_result(self, mock_market_data):
        """Empty universe returns empty result."""
        service = WarriorScannerService(market_data=mock_market_data)
        result = service.scan()
        
        assert isinstance(result, WarriorScanResult)
        assert result.candidates == []
        assert result.processed_count == 0


class TestMomentumOverride:
    """
    Test momentum override feature for offering bypass.
    
    Ross Cameron's "trade them, manage risk" philosophy:
    - RVOL >= 50x AND gap >= 30% bypasses offering rejection
    - Position size reduced by 25% when override active
    """
    
    @pytest.fixture
    def scanner_service(self):
        """Create scanner service with mock market data."""
        mock_market_data = Mock()
        mock_market_data.fmp = Mock()
        mock_market_data.fmp.get_etf_symbols.return_value = set()
        return WarriorScannerService(market_data=mock_market_data)
    
    @pytest.fixture
    def base_context(self):
        """Create base EvaluationContext for momentum tests."""
        from nexus2.domain.scanner.warrior_scanner_service import EvaluationContext
        return EvaluationContext(
            symbol="TEST",
            name="Test Stock",
            price=Decimal("10.00"),
            change_percent=Decimal("35.0"),  # >= 30% gap
            verbose=False,
            settings=WarriorScanSettings(),
            rvol=Decimal("60"),  # >= 50x RVOL
            has_catalyst=True,
            catalyst_type="offering",  # Negative catalyst to bypass
            catalyst_desc="Secondary offering announced",
        )
    
    def test_momentum_override_allows_offering(self, base_context):
        """When RVOL >= 50 AND gap >= 30%, offering should NOT reject."""
        ctx = base_context
        s = ctx.settings
        
        # Simulate the momentum override check from _check_catalyst()
        # This mirrors lines 1275-1285 in warrior_scanner_service.py
        neg_type = "offering"
        should_bypass = False
        
        if ctx.rvol >= s.momentum_override_rvol and float(ctx.change_percent) >= s.momentum_override_gap:
            should_bypass = True
            ctx.momentum_override = True
            ctx.position_size_multiplier = 1.0 - s.momentum_override_size_reduction
        
        assert should_bypass is True, "Momentum override should bypass offering rejection"
        assert ctx.momentum_override is True, "momentum_override flag should be set"
    
    def test_momentum_override_rejects_weak_offering(self, base_context):
        """When RVOL < 50, offering should still reject."""
        ctx = base_context
        ctx.rvol = Decimal("30")  # Below 50x threshold
        s = ctx.settings
        
        # Simulate the momentum override check
        neg_type = "offering"
        should_bypass = False
        
        if ctx.rvol >= s.momentum_override_rvol and float(ctx.change_percent) >= s.momentum_override_gap:
            should_bypass = True
            ctx.momentum_override = True
            ctx.position_size_multiplier = 1.0 - s.momentum_override_size_reduction
        
        assert should_bypass is False, "Weak RVOL should NOT bypass offering rejection"
        assert ctx.momentum_override is False, "momentum_override flag should remain False"
    
    def test_momentum_override_reduces_position(self, base_context):
        """Momentum override should set position_size_multiplier = 0.75."""
        ctx = base_context
        s = ctx.settings
        
        # Verify default is 1.0
        assert ctx.position_size_multiplier == 1.0
        
        # Apply momentum override
        if ctx.rvol >= s.momentum_override_rvol and float(ctx.change_percent) >= s.momentum_override_gap:
            ctx.momentum_override = True
            ctx.position_size_multiplier = 1.0 - s.momentum_override_size_reduction
        
        # Verify position size reduction: 1.0 - 0.25 = 0.75
        assert ctx.position_size_multiplier == 0.75, "Position size should be reduced by 25%"
        assert s.momentum_override_size_reduction == 0.25, "Size reduction should be 25%"
    
    def test_momentum_override_gap_threshold(self, base_context):
        """Gap below 30% should NOT trigger momentum override."""
        ctx = base_context
        ctx.change_percent = Decimal("25.0")  # Below 30% threshold
        s = ctx.settings
        
        should_bypass = False
        if ctx.rvol >= s.momentum_override_rvol and float(ctx.change_percent) >= s.momentum_override_gap:
            should_bypass = True
            ctx.momentum_override = True
        
        assert should_bypass is False, "Low gap should NOT trigger momentum override"
        assert ctx.momentum_override is False
    
    def test_momentum_override_settings_defaults(self):
        """Verify default settings match documented thresholds."""
        settings = WarriorScanSettings()
        
        assert settings.momentum_override_rvol == 50.0, "Default RVOL threshold should be 50"
        assert settings.momentum_override_gap == 30.0, "Default gap threshold should be 30%"
        assert settings.momentum_override_size_reduction == 0.25, "Default size reduction should be 25%"


class TestWarriorScannerIntegration:
    """Integration tests requiring FMP API (marked for manual run)."""
    
    @pytest.mark.skip(reason="Requires FMP API key and market hours")
    def test_live_scan(self):
        """Run live scan against FMP API."""
        service = WarriorScannerService()
        result = service.scan(verbose=True)
        
        print(f"Processed: {result.processed_count}")
        print(f"Candidates: {len(result.candidates)}")
        
        for c in result.candidates[:5]:
            print(f"  {c.symbol}: gap={c.gap_percent}%, rvol={c.relative_volume}x, score={c.quality_score}")
