"""
KK-Style Scanner Tests

Comprehensive mock tests that verify KK-aligned trading logic:
- Quality score filtering
- Stop distance (ATR) filtering
- Tier classification
- Rejection reason tracking
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, patch

from nexus2.domain.automation.unified_scanner import (
    UnifiedScannerService,
    UnifiedScanSettings,
    ScanMode,
    ScanDiagnostics,
    ScanRejection,
)
from nexus2.domain.automation.signals import Signal, SetupType


class TestKKStyleQualityFiltering:
    """Tests for KK-style quality score filtering."""
    
    def test_signal_passes_min_quality(self):
        """Signal with quality >= 7 passes filter."""
        signal = Signal(
            symbol="NVDA",
            setup_type=SetupType.EP,
            entry_price=Decimal("500"),
            tactical_stop=Decimal("490"),  # 2% stop
            quality_score=8,  # Above threshold
            tier="FOCUS",
            rs_percentile=85,
            adr_percent=4.0,
            atr_at_entry=Decimal("12"),  # Stop = 10/12 = 0.83 ATR
        )
        
        assert signal.is_valid(min_quality=7) == True
    
    def test_signal_fails_min_quality(self):
        """Signal with quality < 7 fails filter."""
        signal = Signal(
            symbol="WEAK",
            setup_type=SetupType.BREAKOUT,
            entry_price=Decimal("100"),
            tactical_stop=Decimal("97"),
            quality_score=5,  # Below threshold
            tier="WIDE",
            rs_percentile=60,
            adr_percent=3.0,
            atr_at_entry=Decimal("4"),
        )
        
        assert signal.is_valid(min_quality=7) == False
        
    def test_rejection_reason_quality_too_low(self):
        """get_rejection_reason returns quality_too_low for low quality signal."""
        signal = Signal(
            symbol="JUNK",
            setup_type=SetupType.EP,
            entry_price=Decimal("50"),
            tactical_stop=Decimal("48"),
            quality_score=4,
            tier="WIDE",
            rs_percentile=40,
            adr_percent=2.0,
        )
        
        reason = signal.get_rejection_reason(min_quality=7)
        assert reason is not None
        assert reason[0] == "quality_too_low"
        assert reason[1] == 7  # threshold
        assert reason[2] == 4  # actual


class TestKKStyleStopFiltering:
    """Tests for KK-style ATR-based stop filtering."""
    
    def test_stop_within_1_atr_passes(self):
        """Stop distance <= 1.0 ATR passes filter."""
        signal = Signal(
            symbol="TIGHT",
            setup_type=SetupType.EP,
            entry_price=Decimal("100"),
            tactical_stop=Decimal("98"),  # $2 stop
            quality_score=8,
            tier="FOCUS",
            rs_percentile=80,
            adr_percent=4.0,
            atr_at_entry=Decimal("3"),  # 2/3 = 0.67 ATR
        )
        
        assert signal.stop_atr == pytest.approx(0.67, rel=0.1)
        assert signal.is_valid(stop_mode="atr", max_stop_atr=1.0) == True
    
    def test_stop_over_1_atr_fails(self):
        """Stop distance > 1.0 ATR fails filter."""
        signal = Signal(
            symbol="WIDE",
            setup_type=SetupType.BREAKOUT,
            entry_price=Decimal("100"),
            tactical_stop=Decimal("95"),  # $5 stop
            quality_score=8,
            tier="FOCUS",
            rs_percentile=80,
            adr_percent=4.0,
            atr_at_entry=Decimal("3"),  # 5/3 = 1.67 ATR
        )
        
        assert signal.stop_atr == pytest.approx(1.67, rel=0.1)
        assert signal.is_valid(stop_mode="atr", max_stop_atr=1.0) == False
    
    def test_rejection_reason_stop_too_wide(self):
        """get_rejection_reason returns stop_too_wide_atr for wide stop."""
        signal = Signal(
            symbol="BAGGY",
            setup_type=SetupType.EP,
            entry_price=Decimal("100"),
            tactical_stop=Decimal("94"),  # $6 stop
            quality_score=9,
            tier="FOCUS",
            rs_percentile=90,
            adr_percent=5.0,
            atr_at_entry=Decimal("4"),  # 6/4 = 1.5 ATR
        )
        
        reason = signal.get_rejection_reason(stop_mode="atr", max_stop_atr=1.0)
        assert reason is not None
        assert reason[0] == "stop_too_wide_atr"
        assert reason[1] == 1.0  # threshold
        assert reason[2] == pytest.approx(1.5, rel=0.1)  # actual


class TestKKStyleTierClassification:
    """Tests for tier classification (FOCUS, WIDE, SKIP)."""
    
    def test_focus_tier_passes(self):
        """FOCUS tier signals pass filter."""
        signal = Signal(
            symbol="TOP",
            setup_type=SetupType.EP,
            entry_price=Decimal("200"),
            tactical_stop=Decimal("196"),
            quality_score=9,
            tier="FOCUS",
            rs_percentile=95,
            adr_percent=5.0,
            atr_at_entry=Decimal("5"),
        )
        
        assert signal.is_valid() == True
    
    def test_wide_tier_passes(self):
        """WIDE tier signals pass filter."""
        signal = Signal(
            symbol="OK",
            setup_type=SetupType.BREAKOUT,
            entry_price=Decimal("150"),
            tactical_stop=Decimal("147"),
            quality_score=7,
            tier="WIDE",
            rs_percentile=70,
            adr_percent=3.5,
            atr_at_entry=Decimal("4"),
        )
        
        assert signal.is_valid() == True
    
    def test_skip_tier_fails(self):
        """SKIP tier signals fail filter."""
        signal = Signal(
            symbol="GARBAGE",
            setup_type=SetupType.EP,
            entry_price=Decimal("25"),
            tactical_stop=Decimal("24"),
            quality_score=7,  # Quality OK
            tier="SKIP",  # But tier is SKIP
            rs_percentile=30,
            adr_percent=2.0,
        )
        
        assert signal.is_valid() == False
    
    def test_rejection_reason_tier_skip(self):
        """get_rejection_reason returns tier_not_focus_wide for SKIP tier."""
        signal = Signal(
            symbol="TRASH",
            setup_type=SetupType.BREAKOUT,
            entry_price=Decimal("10"),
            tactical_stop=Decimal("9.5"),
            quality_score=8,
            tier="SKIP",
            rs_percentile=20,
            adr_percent=1.5,
        )
        
        reason = signal.get_rejection_reason()
        assert reason is not None
        assert reason[0] == "tier_not_focus_wide"


class TestKKStylePositionSizing:
    """Tests for KK-style position sizing based on tactical stop."""
    
    def test_share_calculation_from_risk(self):
        """Position size calculated from fixed dollar risk."""
        signal = Signal(
            symbol="MSFT",
            setup_type=SetupType.EP,
            entry_price=Decimal("400"),
            tactical_stop=Decimal("395"),  # $5 risk per share
            quality_score=9,
            tier="FOCUS",
            rs_percentile=90,
            adr_percent=3.0,
        )
        
        # $250 risk / $5 per share = 50 shares
        shares = signal.calculate_shares(Decimal("250"))
        assert shares == 50
    
    def test_share_calculation_rounds_down(self):
        """Position size rounds down to whole shares."""
        signal = Signal(
            symbol="GOOGL",
            setup_type=SetupType.BREAKOUT,
            entry_price=Decimal("150"),
            tactical_stop=Decimal("147"),  # $3 risk per share
            quality_score=8,
            tier="FOCUS",
            rs_percentile=85,
            adr_percent=3.5,
        )
        
        # $250 risk / $3 per share = 83.33 -> 83 shares
        shares = signal.calculate_shares(Decimal("250"))
        assert shares == 83


class TestScanDiagnostics:
    """Tests for scan diagnostics tracking."""
    
    def test_diagnostics_structure(self):
        """ScanDiagnostics has correct fields."""
        diag = ScanDiagnostics(
            scanner="ep",
            enabled=True,
            candidates_found=10,
            candidates_passed=3,
            rejections=[
                ScanRejection(symbol="NVDA", reason="stop_too_wide_atr", threshold=1.0, actual_value=1.5),
            ],
        )
        
        assert diag.scanner == "ep"
        assert diag.enabled == True
        assert diag.candidates_found == 10
        assert diag.candidates_passed == 3
        assert len(diag.rejections) == 1
        assert diag.rejections[0].symbol == "NVDA"
    
    def test_rejection_structure(self):
        """ScanRejection captures all filtering info."""
        rej = ScanRejection(
            symbol="AAPL",
            reason="quality_too_low",
            threshold=7,
            actual_value=5,
        )
        
        assert rej.symbol == "AAPL"
        assert rej.reason == "quality_too_low"
        assert rej.threshold == 7
        assert rej.actual_value == 5
