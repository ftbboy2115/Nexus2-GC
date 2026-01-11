"""
Tests for Position Sizing Service
"""

import pytest
from decimal import Decimal

from nexus2.domain.risk.models import RiskContext, SizingMode
from nexus2.domain.risk.position_sizing import PositionSizingService
from nexus2.settings.risk_settings import RiskSettings, PerformanceSettings


@pytest.fixture
def risk_settings():
    return RiskSettings()


@pytest.fixture
def performance_settings():
    return PerformanceSettings()


@pytest.fixture
def sizing_service(risk_settings, performance_settings):
    return PositionSizingService(
        risk_settings=risk_settings,
        performance_settings=performance_settings,
    )


@pytest.fixture
def risk_context():
    return RiskContext(
        account_value=Decimal("100_000"),
        risk_per_trade_dollars=Decimal("250"),
        max_position_pct=Decimal("30"),
        max_open_heat_pct=Decimal("10"),
        current_open_heat=Decimal("3"),  # 3% currently at risk
        rrr_last_20=Decimal("2.5"),  # Good performance
        sizing_multiplier=Decimal("1.0"),
    )


class TestPositionSizing:
    """Tests for position sizing."""
    
    def test_basic_position_size(self, sizing_service, risk_context):
        """Basic position sizing from fixed-dollar risk."""
        result = sizing_service.calculate_position_size(
            symbol="NVDA",
            entry_price=Decimal("100.00"),
            stop_price=Decimal("98.00"),  # $2 stop
            risk_context=risk_context,
            atr=Decimal("3.00"),  # ATR is $3, stop is $2 (OK)
        )
        
        # $250 risk / $2 stop = 125 shares
        assert result.shares == 125
        assert result.is_valid
        assert result.risk_dollars == Decimal("250")
    
    def test_stop_distance_validation(self, sizing_service, risk_context):
        """Stop wider than 1x ATR should fail validation."""
        result = sizing_service.calculate_position_size(
            symbol="WIDE",
            entry_price=Decimal("100.00"),
            stop_price=Decimal("94.00"),  # $6 stop
            risk_context=risk_context,
            atr=Decimal("3.00"),  # ATR is $3, stop is 2x ATR (FAIL)
        )
        
        assert not result.is_valid
        assert any("ATR" in e for e in result.validation_errors)
    
    def test_invalid_stop_above_entry(self, sizing_service, risk_context):
        """Stop above entry should be invalid."""
        result = sizing_service.calculate_position_size(
            symbol="BAD",
            entry_price=Decimal("100.00"),
            stop_price=Decimal("101.00"),  # Stop above entry!
            risk_context=risk_context,
            atr=Decimal("3.00"),
        )
        
        assert not result.is_valid
        assert result.shares == 0
    
    def test_reduced_sizing_low_rrr(self, sizing_service, performance_settings):
        """Low RRR should reduce position size."""
        # RRR < 1 should use reduced multiplier
        adjusted = sizing_service.adjust_for_performance(
            base_risk=Decimal("250"),
            rrr=Decimal("0.5"),  # Cold streak
        )
        
        expected = Decimal("250") * performance_settings.reduced_multiplier
        assert adjusted == expected
    
    def test_full_sizing_high_rrr(self, sizing_service):
        """High RRR should use full position size."""
        adjusted = sizing_service.adjust_for_performance(
            base_risk=Decimal("250"),
            rrr=Decimal("3.0"),  # Hot streak
        )
        
        assert adjusted == Decimal("250")  # Full risk
    
    def test_position_pct_validation(self, sizing_service, risk_context):
        """Position exceeding max % should fail."""
        result = sizing_service.calculate_position_size(
            symbol="HUGE",
            entry_price=Decimal("1000.00"),  # Expensive stock
            stop_price=Decimal("999.00"),    # Tight stop
            risk_context=risk_context,
            atr=Decimal("5.00"),
        )
        
        # $250 / $1 = 250 shares = $250,000 position = 250% of account!
        # Should fail max position validation
        assert not result.is_valid
        assert any("position" in e.lower() for e in result.validation_errors)


class TestRiskContext:
    """Tests for RiskContext."""
    
    def test_sizing_mode_full(self):
        """High RRR should give FULL sizing mode."""
        ctx = RiskContext(
            account_value=Decimal("100_000"),
            risk_per_trade_dollars=Decimal("250"),
            max_position_pct=Decimal("30"),
            max_open_heat_pct=Decimal("10"),
            current_open_heat=Decimal("5"),
            rrr_last_20=Decimal("2.5"),
            sizing_multiplier=Decimal("1.0"),
        )
        assert ctx.sizing_mode == SizingMode.FULL
    
    def test_sizing_mode_reduced(self):
        """Low RRR should give REDUCED sizing mode."""
        ctx = RiskContext(
            account_value=Decimal("100_000"),
            risk_per_trade_dollars=Decimal("250"),
            max_position_pct=Decimal("30"),
            max_open_heat_pct=Decimal("10"),
            current_open_heat=Decimal("5"),
            rrr_last_20=Decimal("0.5"),  # Cold
            sizing_multiplier=Decimal("0.5"),
        )
        assert ctx.sizing_mode == SizingMode.REDUCED
