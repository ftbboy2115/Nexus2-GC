"""
Tests for HTF (High-Tight Flag) Scanner Service

Tests KK-style HTF pattern detection:
- +90% pole move
- ≤25% flag pullback
- Entry/stop zone calculation
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, patch

from nexus2.domain.scanner.htf_scanner_service import (
    HTFScannerService,
    HTFScanSettings,
    HTFStatus,
    HTFCandidate,
)


class TestHTFScanSettings:
    """Tests for HTF scan settings."""
    
    def test_default_settings(self):
        """Default settings match KK methodology."""
        settings = HTFScanSettings()
        
        assert settings.min_move_pct == Decimal("90.0")  # +90% pole
        assert settings.max_pullback_pct == Decimal("25.0")  # 25% flag
        assert settings.min_price == Decimal("4.0")
        assert settings.min_dollar_vol == Decimal("5000000")
        assert settings.lookback_days == 60
    
    def test_custom_settings(self):
        """Can customize HTF settings."""
        settings = HTFScanSettings(
            min_move_pct=Decimal("100.0"),  # Stricter: 100%
            max_pullback_pct=Decimal("20.0"),  # Tighter flag
        )
        
        assert settings.min_move_pct == Decimal("100.0")
        assert settings.max_pullback_pct == Decimal("20.0")


class TestHTFCandidate:
    """Tests for HTF candidate model."""
    
    def test_risk_reward_calculation(self):
        """Risk/reward ratio calculates correctly."""
        candidate = HTFCandidate(
            symbol="TEST",
            name="Test Stock",
            price=Decimal("100"),
            move_pct=Decimal("100"),  # 100% move
            pullback_pct=Decimal("10"),
            highest_high=Decimal("110"),
            lowest_low=Decimal("50"),
            dollar_volume=Decimal("10000000"),
            entry_price=Decimal("108"),
            stop_price=Decimal("100"),
        )
        
        # Risk = 108 - 100 = 8
        # Target (2x move) = 108 + 108 = 216
        # Reward = 216 - 108 = 108
        # R:R = 108 / 8 = 13.5
        rr = candidate.risk_reward_ratio
        assert rr is not None
        assert rr > 10  # Should be very favorable
    
    def test_risk_reward_none_without_stop(self):
        """R:R is None if stop not defined."""
        candidate = HTFCandidate(
            symbol="TEST",
            name="Test",
            price=Decimal("100"),
            move_pct=Decimal("100"),
            pullback_pct=Decimal("10"),
            highest_high=Decimal("110"),
            lowest_low=Decimal("50"),
            dollar_volume=Decimal("10000000"),
        )
        
        assert candidate.risk_reward_ratio is None


class TestHTFScannerService:
    """Tests for HTF scanner service."""
    
    @pytest.fixture
    def mock_market_data(self):
        """Create mock market data adapter."""
        mock = Mock()
        mock.get_company_name.return_value = "Test Company"
        return mock
    
    @pytest.fixture
    def scanner(self, mock_market_data):
        """Create scanner with mock data."""
        return HTFScannerService(market_data=mock_market_data)
    
    def test_evaluate_passing_htf(self, scanner, mock_market_data):
        """Detects valid HTF pattern."""
        # Create price history showing +100% move with 10% pullback
        # Low of 50, high of 110, current at 100
        mock_market_data.get_historical_prices.return_value = [
            {"date": f"2024-01-{i:02d}", "open": 50 + i, "high": 50 + i + 1, "low": 50 + i - 1, "close": 50 + i, "volume": 1000000}
            for i in range(1, 30)
        ] + [
            {"date": f"2024-02-{i:02d}", "open": 100 + i, "high": 110, "low": 95, "close": 100, "volume": 1000000}
            for i in range(1, 35)
        ]
        
        candidate = scanner._evaluate_symbol("TEST")
        
        assert candidate is not None
        assert candidate.symbol == "TEST"
        assert candidate.move_pct >= Decimal("90")  # Meets minimum
        assert candidate.pullback_pct <= Decimal("25")  # Within flag range
    
    def test_reject_insufficient_move(self, scanner, mock_market_data):
        """Rejects stocks with <90% move."""
        # Small move: 50 to 70 = +40%
        mock_market_data.get_historical_prices.return_value = [
            {"date": f"2024-01-{i:02d}", "open": 50, "high": 70, "low": 50, "close": 60, "volume": 1000000}
            for i in range(1, 65)
        ]
        
        candidate = scanner._evaluate_symbol("WEAK")
        
        assert candidate is None
    
    def test_reject_deep_pullback(self, scanner, mock_market_data):
        """Rejects stocks with >25% pullback."""
        # Big move but deep pullback: High 200, current 140 = -30%
        mock_market_data.get_historical_prices.return_value = [
            {"date": f"2024-01-{i:02d}", "open": 50, "high": 200, "low": 50, "close": 140, "volume": 1000000}
            for i in range(1, 65)
        ]
        
        candidate = scanner._evaluate_symbol("DEEP")
        
        assert candidate is None
    
    def test_reject_low_price(self, scanner, mock_market_data):
        """Rejects stocks below minimum price."""
        mock_market_data.get_historical_prices.return_value = [
            {"date": f"2024-01-{i:02d}", "open": 1, "high": 3, "low": 1, "close": 2.5, "volume": 10000000}
            for i in range(1, 65)
        ]
        
        candidate = scanner._evaluate_symbol("CHEAP")
        
        assert candidate is None
    
    def test_reject_low_volume(self, scanner, mock_market_data):
        """Rejects stocks with low dollar volume."""
        mock_market_data.get_historical_prices.return_value = [
            {"date": f"2024-01-{i:02d}", "open": 5, "high": 15, "low": 5, "close": 14, "volume": 100}  # Very low
            for i in range(1, 65)
        ]
        
        candidate = scanner._evaluate_symbol("ILLIQUID")
        
        assert candidate is None
    
    def test_blacklist_ticker(self, scanner, mock_market_data):
        """Rejects blacklisted tickers."""
        candidate = scanner._evaluate_symbol("PLBY")
        
        assert candidate is None
        # Should not even call market data
        mock_market_data.get_historical_prices.assert_not_called()
    
    def test_get_htf_trend_api(self, scanner, mock_market_data):
        """get_htf_trend returns legacy-compatible format."""
        # Valid HTF setup
        mock_market_data.get_historical_prices.return_value = [
            {"date": f"2024-01-{i:02d}", "open": 50 + i, "high": 50 + i + 1, "low": 50 + i - 1, "close": 50 + i, "volume": 1000000}
            for i in range(1, 30)
        ] + [
            {"date": f"2024-02-{i:02d}", "open": 100, "high": 110, "low": 95, "close": 100, "volume": 1000000}
            for i in range(1, 35)
        ]
        
        result = scanner.get_htf_trend("TEST", sector="Technology")
        
        assert result["htf_trend"] == "HTF"
        assert result["htf_trend_score"] is not None
        assert result["htf_trend_score"] > 0
        assert result["htf_raw"] is not None
        assert result["htf_raw"]["symbol"] == "TEST"
        assert result["htf_raw"]["sector"] == "Technology"
    
    def test_get_htf_trend_no_pattern(self, scanner, mock_market_data):
        """get_htf_trend returns None for non-HTF stocks."""
        mock_market_data.get_historical_prices.return_value = [
            {"date": f"2024-01-{i:02d}", "open": 50, "high": 55, "low": 45, "close": 50, "volume": 1000000}
            for i in range(1, 65)
        ]
        
        result = scanner.get_htf_trend("FLAT")
        
        assert result["htf_trend"] is None
        assert result["htf_trend_score"] is None
        assert result["htf_raw"] is None


class TestHTFStatusDetermination:
    """Tests for HTF status logic."""
    
    @pytest.fixture
    def scanner(self):
        mock = Mock()
        mock.get_company_name.return_value = "Test"
        return HTFScannerService(market_data=mock)
    
    def test_status_extended_near_highs(self, scanner):
        """Status is EXTENDED when very near highs (<5% pullback)."""
        scanner.market_data.get_historical_prices.return_value = [
            {"date": f"2024-01-{i:02d}", "open": 50 + i*2, "high": 150, "low": 50, "close": 148, "volume": 1000000}
            for i in range(1, 65)
        ]
        
        candidate = scanner._evaluate_symbol("EXTENDED")
        
        assert candidate is not None
        assert candidate.status == HTFStatus.EXTENDED
    
    def test_status_complete_ideal_pullback(self, scanner):
        """Status is COMPLETE for ideal 5-15% pullback."""
        scanner.market_data.get_historical_prices.return_value = [
            {"date": f"2024-01-{i:02d}", "open": 50 + i*2, "high": 150, "low": 50, "close": 135, "volume": 1000000}
            for i in range(1, 65)
        ]
        
        candidate = scanner._evaluate_symbol("IDEAL")
        
        assert candidate is not None
        assert candidate.status == HTFStatus.COMPLETE
    
    def test_status_forming_deeper_pullback(self, scanner):
        """Status is FORMING for 15-25% pullback."""
        scanner.market_data.get_historical_prices.return_value = [
            {"date": f"2024-01-{i:02d}", "open": 50 + i*2, "high": 150, "low": 50, "close": 120, "volume": 1000000}
            for i in range(1, 65)
        ]
        
        candidate = scanner._evaluate_symbol("FORMING")
        
        assert candidate is not None
        assert candidate.status == HTFStatus.FORMING
