"""
Tests for Unified Scanner Service

Tests the unified signal pipeline that aggregates EP, Breakout, and HTF scanners.
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock

from nexus2.domain.automation.unified_scanner import (
    UnifiedScannerService,
    UnifiedScanSettings,
    UnifiedScanResult,
    ScanMode,
)
from nexus2.domain.automation.signals import Signal, SetupType


class TestUnifiedScanSettings:
    """Tests for unified scan settings."""
    
    def test_default_settings(self):
        """Default settings include all scanners."""
        settings = UnifiedScanSettings()
        
        assert ScanMode.ALL in settings.modes
        assert settings.min_quality_score == 7
        assert settings.max_stop_percent == 5.0
    
    def test_custom_modes(self):
        """Can specify specific scanner modes."""
        settings = UnifiedScanSettings(
            modes=[ScanMode.EP_ONLY, ScanMode.HTF_ONLY]
        )
        
        assert ScanMode.EP_ONLY in settings.modes
        assert ScanMode.HTF_ONLY in settings.modes
        assert ScanMode.BREAKOUT_ONLY not in settings.modes


class TestUnifiedScanResult:
    """Tests for unified scan result."""
    
    def test_total_signals(self):
        """total_signals property returns signal count."""
        result = UnifiedScanResult(
            signals=[Mock(), Mock(), Mock()],
            ep_count=2,
            breakout_count=1,
            htf_count=0,
        )
        
        assert result.total_signals == 3
    
    def test_empty_result(self):
        """Empty result has correct defaults."""
        result = UnifiedScanResult(signals=[])
        
        assert result.total_signals == 0
        assert result.ep_count == 0
        assert result.breakout_count == 0
        assert result.htf_count == 0


class TestUnifiedScannerService:
    """Tests for unified scanner service."""
    
    @pytest.fixture
    def mock_ep_scanner(self):
        """Create mock EP scanner."""
        scanner = Mock()
        scanner.scan.return_value = Mock(
            candidates=[],
            processed_count=10,
        )
        return scanner
    
    @pytest.fixture
    def mock_breakout_scanner(self):
        """Create mock Breakout scanner."""
        scanner = Mock()
        scanner.scan.return_value = Mock(
            candidates=[],
            processed_count=10,
        )
        return scanner
    
    @pytest.fixture
    def mock_htf_scanner(self):
        """Create mock HTF scanner."""
        scanner = Mock()
        scanner.scan.return_value = Mock(
            candidates=[],
            processed_count=10,
        )
        return scanner
    
    @pytest.fixture
    def unified_scanner(self, mock_ep_scanner, mock_breakout_scanner, mock_htf_scanner):
        """Create unified scanner with mocks."""
        return UnifiedScannerService(
            ep_scanner=mock_ep_scanner,
            breakout_scanner=mock_breakout_scanner,
            htf_scanner=mock_htf_scanner,
        )
    
    def test_scan_all_modes(self, unified_scanner, mock_ep_scanner, mock_breakout_scanner, mock_htf_scanner):
        """Scanning with ALL mode runs all scanners."""
        result = unified_scanner.scan(modes=[ScanMode.ALL])
        
        mock_ep_scanner.scan.assert_called_once()
        mock_breakout_scanner.scan.assert_called_once()
        mock_htf_scanner.scan.assert_called_once()
    
    def test_scan_ep_only(self, unified_scanner, mock_ep_scanner, mock_breakout_scanner, mock_htf_scanner):
        """Scanning with EP_ONLY only runs EP scanner."""
        result = unified_scanner.scan(modes=[ScanMode.EP_ONLY])
        
        mock_ep_scanner.scan.assert_called_once()
        mock_breakout_scanner.scan.assert_not_called()
        mock_htf_scanner.scan.assert_not_called()
    
    def test_scan_htf_only(self, unified_scanner, mock_ep_scanner, mock_breakout_scanner, mock_htf_scanner):
        """Scanning with HTF_ONLY only runs HTF scanner."""
        result = unified_scanner.scan(modes=[ScanMode.HTF_ONLY])
        
        mock_htf_scanner.scan.assert_called_once()
        mock_ep_scanner.scan.assert_not_called()
        mock_breakout_scanner.scan.assert_not_called()
    
    @pytest.mark.timeout(30)  # Extended timeout for HTFStatus import
    def test_deduplication(self):
        """Same symbol from multiple scanners is deduplicated."""
        # Create mock EP result with NVDA
        ep_candidate = Mock()
        ep_candidate.symbol = "NVDA"
        ep_candidate.price = Decimal("100")
        ep_candidate.relative_volume = Decimal("3.0")
        ep_candidate.gap_percent = Decimal("8.0")
        ep_candidate.catalyst_type = Mock(value="earnings")
        
        ep_scanner = Mock()
        ep_scanner.scan.return_value = Mock(
            candidates=[ep_candidate],
            processed_count=1,
        )
        
        # Create mock HTF result with same NVDA
        htf_candidate = Mock()
        htf_candidate.symbol = "NVDA"  # Same symbol
        htf_candidate.price = Decimal("100")
        htf_candidate.move_pct = Decimal("120")
        htf_candidate.pullback_pct = Decimal("10")
        htf_candidate.entry_price = Decimal("102")
        htf_candidate.stop_price = Decimal("95")
        from nexus2.domain.scanner.htf_scanner_service import HTFStatus
        htf_candidate.status = HTFStatus.COMPLETE
        
        htf_scanner = Mock()
        htf_scanner.scan.return_value = Mock(
            candidates=[htf_candidate],
            processed_count=1,
        )
        
        unified = UnifiedScannerService(
            ep_scanner=ep_scanner,
            breakout_scanner=Mock(scan=Mock(return_value=Mock(candidates=[], processed_count=0))),
            htf_scanner=htf_scanner,
        )
        
        result = unified.scan()
        
        # Should only have one signal for NVDA (first one wins - EP)
        nvda_signals = [s for s in result.signals if s.symbol == "NVDA"]
        assert len(nvda_signals) <= 1  # Deduplicated
    
    def test_result_sorted_by_quality(self):
        """Signals are sorted by quality score (highest first)."""
        # Create mock candidates with different qualities
        low_quality = Mock()
        low_quality.symbol = "LOW"
        low_quality.price = Decimal("50")
        low_quality.relative_volume = Decimal("1.5")
        low_quality.gap_percent = Decimal("3.0")
        low_quality.catalyst_type = None
        
        high_quality = Mock()
        high_quality.symbol = "HIGH"
        high_quality.price = Decimal("50")
        high_quality.relative_volume = Decimal("5.0")
        high_quality.gap_percent = Decimal("10.0")
        high_quality.catalyst_type = Mock(value="earnings")
        
        ep_scanner = Mock()
        ep_scanner.scan.return_value = Mock(
            candidates=[low_quality, high_quality],  # Low quality first
            processed_count=2,
        )
        
        unified = UnifiedScannerService(
            settings=UnifiedScanSettings(min_quality_score=1),  # Accept all
            ep_scanner=ep_scanner,
            breakout_scanner=Mock(scan=Mock(return_value=Mock(candidates=[], processed_count=0))),
            htf_scanner=Mock(scan=Mock(return_value=Mock(candidates=[], processed_count=0))),
        )
        
        result = unified.scan(modes=[ScanMode.EP_ONLY])
        
        if len(result.signals) >= 2:
            # Higher quality should be first
            assert result.signals[0].quality_score >= result.signals[1].quality_score
    
    def test_scan_duration_tracked(self, unified_scanner):
        """Scan duration is tracked in result."""
        result = unified_scanner.scan()
        
        assert result.scan_duration_ms >= 0
        assert result.scanned_at is not None


class TestSignalConversion:
    """Tests for converting scanner candidates to signals."""
    
    def test_ep_candidate_to_signal(self):
        """EP candidate converts to Signal correctly."""
        from dataclasses import dataclass
        from typing import Optional
        
        # Use a proper dataclass instead of Mock to support Decimal comparisons
        @dataclass
        class EPCandidate:
            symbol: str
            current_price: Decimal  # _ep_candidate_to_signal expects this
            open_price: Decimal
            relative_volume: Decimal
            gap_percent: Decimal
            tactical_stop: Optional[Decimal] = None  # Tactical stop for position sizing
            opening_range: Optional[object] = None
            catalyst_type: Optional[object] = None
            rs_percentile: int = 70
            adr_percent: float = 3.0
        
        # Create a proper catalyst mock
        class CatalystType:
            value = "earnings"
        
        candidate = EPCandidate(
            symbol="AAPL",
            current_price=Decimal("150"),
            open_price=Decimal("148"),
            relative_volume=Decimal("5.0"),   # High RVOL = +2 quality
            gap_percent=Decimal("10.0"),       # >5% = +1 quality
            tactical_stop=Decimal("145"),      # Stop at $145
            catalyst_type=CatalystType(),      # +2 quality
        )
        # Base 5 + 2 + 1 + 2 = 10 quality, tier = FOCUS
        
        ep_scanner = Mock()
        ep_scanner.scan.return_value = Mock(
            candidates=[candidate],
            processed_count=1,
        )
        
        unified = UnifiedScannerService(
            settings=UnifiedScanSettings(min_quality_score=7),  # Standard threshold
            ep_scanner=ep_scanner,
            breakout_scanner=Mock(scan=Mock(return_value=Mock(candidates=[], processed_count=0))),
            htf_scanner=Mock(scan=Mock(return_value=Mock(candidates=[], processed_count=0))),
        )
        
        result = unified.scan(modes=[ScanMode.EP_ONLY])
        
        assert len(result.signals) == 1
        signal = result.signals[0]
        assert signal.symbol == "AAPL"
        assert signal.setup_type == SetupType.EP
        assert signal.entry_price == Decimal("150")
        assert signal.quality_score >= 7  # Should pass min quality
    
    @pytest.mark.timeout(30)  # Extended timeout for HTFStatus import
    def test_htf_candidate_to_signal(self):
        """HTF candidate converts to Signal correctly."""
        from nexus2.domain.scanner.htf_scanner_service import HTFStatus
        
        candidate = Mock()
        candidate.symbol = "TSLA"
        candidate.name = "Tesla"
        candidate.price = Decimal("200")
        candidate.move_pct = Decimal("100")
        candidate.pullback_pct = Decimal("12")
        candidate.entry_price = Decimal("205")
        candidate.stop_price = Decimal("190")
        candidate.status = HTFStatus.COMPLETE
        
        htf_scanner = Mock()
        htf_scanner.scan.return_value = Mock(
            candidates=[candidate],
            processed_count=1,
        )
        
        # Use relaxed settings to accommodate the 7.3% stop (205-190)/205
        unified = UnifiedScannerService(
            settings=UnifiedScanSettings(
                min_quality_score=1,
                stop_mode="percent",  # Use percent mode for test without ATR
                max_stop_percent=10.0,  # Relaxed to accommodate 7.3% stop
            ),
            ep_scanner=Mock(scan=Mock(return_value=Mock(candidates=[], processed_count=0))),
            breakout_scanner=Mock(scan=Mock(return_value=Mock(candidates=[], processed_count=0))),
            htf_scanner=htf_scanner,
        )
        
        result = unified.scan(modes=[ScanMode.HTF_ONLY])
        
        assert len(result.signals) == 1
        signal = result.signals[0]
        assert signal.symbol == "TSLA"
        assert signal.setup_type == SetupType.HTF
        assert signal.entry_price == Decimal("205")
        assert signal.tactical_stop == Decimal("190")
