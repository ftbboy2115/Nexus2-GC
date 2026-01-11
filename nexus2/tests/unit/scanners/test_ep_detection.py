"""
Tests for EP Detection Service

Tests the core EP detection logic with mocked data.
"""

import pytest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import Mock, patch

from nexus2.domain.setup_detection.ep_detection import (
    EPDetectionService,
    EPSettings,
)
from nexus2.domain.setup_detection.ep_models import (
    EPCandidate,
    EPCandidateStatus,
    EPValidationResult,
    CatalystType,
    OpeningRange,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def ep_settings():
    """Default EP settings."""
    return EPSettings(
        min_gap_percent=Decimal("8.0"),
        min_relative_volume=Decimal("2.0"),
        min_price=Decimal("5.0"),
        abs_min_price=Decimal("2.0"),
    )


@pytest.fixture
def ep_service(ep_settings):
    """EP detection service."""
    return EPDetectionService(ep_settings)


@pytest.fixture
def valid_candidate():
    """A valid EP candidate meeting all criteria."""
    return EPCandidate(
        symbol="AAPL",
        catalyst_date=date.today(),
        catalyst_type=CatalystType.EARNINGS,
        catalyst_description="Q4 earnings beat",
        gap_percent=Decimal("12.5"),  # Above 8% min
        prev_close=Decimal("100.00"),
        open_price=Decimal("112.50"),  # 12.5% gap
        pre_market_volume=5_000_000,
        relative_volume=Decimal("3.5"),  # Above 2x min
        atr=Decimal("2.50"),
        adr_percent=Decimal("4.5"),
        status=EPCandidateStatus.PENDING,
    )


# ============================================================================
# Test: create_candidate
# ============================================================================

class TestCreateCandidate:
    """Tests for EPDetectionService.create_candidate()"""
    
    def test_creates_candidate_with_correct_gap(self, ep_service):
        """Gap percentage should be calculated correctly."""
        candidate = ep_service.create_candidate(
            symbol="TEST",
            catalyst_date=date.today(),
            catalyst_type=CatalystType.EARNINGS,
            catalyst_description="Test catalyst",
            prev_close=Decimal("100.00"),
            open_price=Decimal("110.00"),  # 10% gap
            pre_market_volume=1_000_000,
            avg_volume=500_000,
            atr=Decimal("2.0"),
            adr_percent=Decimal("5.0"),
        )
        
        assert candidate.symbol == "TEST"
        assert candidate.gap_percent == Decimal("10.0")
        assert candidate.relative_volume == Decimal("2.0")  # 1M / 500K
        assert candidate.status == EPCandidateStatus.PENDING
    
    def test_calculates_relative_volume(self, ep_service):
        """Relative volume should be pre_market / avg_volume."""
        candidate = ep_service.create_candidate(
            symbol="TEST",
            catalyst_date=date.today(),
            catalyst_type=CatalystType.OTHER,
            catalyst_description="Test",
            prev_close=Decimal("50.00"),
            open_price=Decimal("55.00"),
            pre_market_volume=3_000_000,
            avg_volume=1_000_000,
            atr=Decimal("1.0"),
            adr_percent=Decimal("3.0"),
        )
        
        assert candidate.relative_volume == Decimal("3.0")
    
    def test_handles_zero_avg_volume(self, ep_service):
        """Zero avg volume should not cause division error."""
        candidate = ep_service.create_candidate(
            symbol="TEST",
            catalyst_date=date.today(),
            catalyst_type=CatalystType.OTHER,
            catalyst_description="Test",
            prev_close=Decimal("50.00"),
            open_price=Decimal("55.00"),
            pre_market_volume=1_000_000,
            avg_volume=0,  # Zero
            atr=Decimal("1.0"),
            adr_percent=Decimal("3.0"),
        )
        
        assert candidate.relative_volume == Decimal("0")


# ============================================================================
# Test: validate_candidate
# ============================================================================

class TestValidateCandidate:
    """Tests for EPDetectionService.validate_candidate()"""
    
    def test_valid_candidate_passes(self, ep_service, valid_candidate):
        """Candidate meeting all criteria should be valid."""
        result = ep_service.validate_candidate(valid_candidate)
        assert result == EPValidationResult.VALID
    
    def test_rejects_low_gap(self, ep_service, valid_candidate):
        """Candidate with gap below minimum should be rejected."""
        valid_candidate.gap_percent = Decimal("5.0")  # Below 8%
        result = ep_service.validate_candidate(valid_candidate)
        assert result == EPValidationResult.INVALID_GAP
    
    def test_rejects_low_volume(self, ep_service, valid_candidate):
        """Candidate with RVOL below minimum should be rejected."""
        valid_candidate.relative_volume = Decimal("1.5")  # Below 2x
        result = ep_service.validate_candidate(valid_candidate)
        assert result == EPValidationResult.INVALID_VOLUME
    
    def test_rejects_low_price(self, ep_service, valid_candidate):
        """Candidate below absolute min price should be rejected."""
        valid_candidate.open_price = Decimal("1.50")  # Below $2
        result = ep_service.validate_candidate(valid_candidate)
        assert result == EPValidationResult.INVALID_PRICE
    
    def test_accepts_price_between_thresholds(self, ep_service, valid_candidate):
        """Price between abs_min and min should still be valid."""
        # $3 is between $2 (abs_min) and $5 (min)
        valid_candidate.open_price = Decimal("3.00")
        result = ep_service.validate_candidate(valid_candidate)
        # Should still be valid (abs_min is the hard cutoff)
        assert result == EPValidationResult.VALID


# ============================================================================
# Test: establish_opening_range
# ============================================================================

class TestEstablishOpeningRange:
    """Tests for EPDetectionService.establish_opening_range()"""
    
    def test_sets_opening_range(self, ep_service, valid_candidate):
        """Opening range should be set correctly."""
        updated = ep_service.establish_opening_range(
            valid_candidate,
            high=Decimal("115.00"),
            low=Decimal("110.00"),
            timeframe_minutes=5,
        )
        
        assert updated.opening_range is not None
        assert updated.opening_range.high == Decimal("115.00")
        assert updated.opening_range.low == Decimal("110.00")
        assert updated.opening_range.timeframe_minutes == 5
        assert updated.status == EPCandidateStatus.ACTIVE
    
    def test_uses_default_timeframe(self, ep_service, valid_candidate):
        """Default timeframe from settings should be used."""
        updated = ep_service.establish_opening_range(
            valid_candidate,
            high=Decimal("115.00"),
            low=Decimal("110.00"),
        )
        
        assert updated.opening_range.timeframe_minutes == ep_service.settings.opening_range_minutes


# ============================================================================
# Test: check_orh_break
# ============================================================================

class TestCheckORHBreak:
    """Tests for EPDetectionService.check_orh_break()"""
    
    def test_returns_false_without_opening_range(self, ep_service, valid_candidate):
        """Should return False if no opening range set."""
        assert valid_candidate.opening_range is None
        result = ep_service.check_orh_break(valid_candidate, Decimal("120.00"))
        assert result is False
    
    def test_detects_orh_break(self, ep_service, valid_candidate):
        """Should detect when price breaks ORH."""
        ep_service.establish_opening_range(
            valid_candidate,
            high=Decimal("115.00"),
            low=Decimal("110.00"),
        )
        
        # Price above ORH
        result = ep_service.check_orh_break(valid_candidate, Decimal("116.00"))
        assert result is True
    
    def test_no_break_below_orh(self, ep_service, valid_candidate):
        """Should return False when price below ORH."""
        ep_service.establish_opening_range(
            valid_candidate,
            high=Decimal("115.00"),
            low=Decimal("110.00"),
        )
        
        result = ep_service.check_orh_break(valid_candidate, Decimal("114.00"))
        assert result is False


# ============================================================================
# Test: Range Quality (CLI logic, simulated here)
# ============================================================================

class TestRangeQualityLogic:
    """Tests for range quality filter logic (as used in CLI)."""
    
    def test_calculates_range_position(self):
        """Range position should be calculated correctly."""
        session_high = Decimal("100.00")
        session_low = Decimal("80.00")
        last_price = Decimal("90.00")
        
        range_len = session_high - session_low
        range_position = (last_price - session_low) / range_len
        
        assert range_position == Decimal("0.5")  # 50% of range
    
    def test_rejects_price_in_lower_range(self):
        """Price in lower 40% of range should fail."""
        session_high = Decimal("100.00")
        session_low = Decimal("80.00")
        last_price = Decimal("85.00")  # 25% of range
        
        range_len = session_high - session_low
        range_position = (last_price - session_low) / range_len
        
        assert range_position < Decimal("0.40")  # Should be rejected
    
    def test_accepts_price_in_upper_range(self):
        """Price in upper 60% of range should pass."""
        session_high = Decimal("100.00")
        session_low = Decimal("80.00")
        last_price = Decimal("95.00")  # 75% of range
        
        range_len = session_high - session_low
        range_position = (last_price - session_low) / range_len
        
        assert range_position >= Decimal("0.40")  # Should pass
