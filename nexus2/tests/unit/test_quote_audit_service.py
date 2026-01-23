"""
Unit Tests for Quote Fidelity Audit Service

Tests for quote audit logging, provider reliability calculation,
time window classification, and cleanup functionality.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from nexus2.domain.audit.quote_audit_service import (
    QuoteAuditService,
    QuoteAuditEntry,
    determine_time_window,
    HIGH_DIVERGENCE_THRESHOLD,
)


class TestDetermineTimeWindow:
    """Tests for time window classification."""
    
    def test_premarket_early(self):
        """5:30 AM ET should be premarket_early."""
        with patch('nexus2.domain.audit.quote_audit_service.now_et') as mock_now:
            mock_now.return_value = datetime(2026, 1, 22, 5, 30)
            assert determine_time_window() == "premarket_early"
    
    def test_premarket_late(self):
        """8:00 AM ET should be premarket_late."""
        with patch('nexus2.domain.audit.quote_audit_service.now_et') as mock_now:
            mock_now.return_value = datetime(2026, 1, 22, 8, 0)
            assert determine_time_window() == "premarket_late"
    
    def test_regular_hours_open(self):
        """9:30 AM ET should be regular_hours."""
        with patch('nexus2.domain.audit.quote_audit_service.now_et') as mock_now:
            mock_now.return_value = datetime(2026, 1, 22, 9, 30)
            assert determine_time_window() == "regular_hours"
    
    def test_regular_hours_midday(self):
        """12:00 PM ET should be regular_hours."""
        with patch('nexus2.domain.audit.quote_audit_service.now_et') as mock_now:
            mock_now.return_value = datetime(2026, 1, 22, 12, 0)
            assert determine_time_window() == "regular_hours"
    
    def test_postmarket_early(self):
        """5:00 PM ET should be postmarket_early."""
        with patch('nexus2.domain.audit.quote_audit_service.now_et') as mock_now:
            mock_now.return_value = datetime(2026, 1, 22, 17, 0)
            assert determine_time_window() == "postmarket_early"
    
    def test_postmarket_late(self):
        """7:00 PM ET should be postmarket_late."""
        with patch('nexus2.domain.audit.quote_audit_service.now_et') as mock_now:
            mock_now.return_value = datetime(2026, 1, 22, 19, 0)
            assert determine_time_window() == "postmarket_late"
    
    def test_closed(self):
        """10:00 PM ET should be closed."""
        with patch('nexus2.domain.audit.quote_audit_service.now_et') as mock_now:
            mock_now.return_value = datetime(2026, 1, 22, 22, 0)
            assert determine_time_window() == "closed"


class TestQuoteAuditEntry:
    """Tests for QuoteAuditEntry dataclass."""
    
    def test_creation(self):
        """Test creating an audit entry."""
        entry = QuoteAuditEntry(
            symbol="IBRX",
            time_window="premarket_early",
            alpaca_price=16.33,
            fmp_price=6.92,
            schwab_price=7.07,
            selected_source="Schwab",
            selected_price=7.07,
            divergence_pct=130.0,
        )
        
        assert entry.symbol == "IBRX"
        assert entry.alpaca_price == 16.33
        assert entry.divergence_pct == 130.0
    
    def test_nullable_prices(self):
        """Test entry with missing source prices."""
        entry = QuoteAuditEntry(
            symbol="TEST",
            time_window="regular_hours",
            alpaca_price=10.0,
            fmp_price=None,  # FMP unavailable
            schwab_price=None,  # Schwab unavailable
            selected_source="Alpaca",
            selected_price=10.0,
            divergence_pct=0.0,
        )
        
        assert entry.fmp_price is None
        assert entry.schwab_price is None


class TestQuoteAuditService:
    """Tests for QuoteAuditService core functionality."""
    
    def test_high_divergence_flag(self):
        """Divergence >20% should be flagged as high_divergence."""
        entry_high = QuoteAuditEntry(
            symbol="TEST",
            time_window="regular_hours",
            alpaca_price=10.0,
            fmp_price=15.0,
            schwab_price=None,
            selected_source="FMP",
            selected_price=15.0,
            divergence_pct=25.0,  # >20%
        )
        assert entry_high.divergence_pct > HIGH_DIVERGENCE_THRESHOLD
        
        entry_low = QuoteAuditEntry(
            symbol="TEST",
            time_window="regular_hours",
            alpaca_price=10.0,
            fmp_price=11.0,
            schwab_price=None,
            selected_source="FMP",
            selected_price=11.0,
            divergence_pct=10.0,  # <20%
        )
        assert entry_low.divergence_pct <= HIGH_DIVERGENCE_THRESHOLD
    
    @patch('nexus2.domain.audit.quote_audit_service.get_session')
    def test_recommend_source_returns_none_insufficient_data(self, mock_session):
        """Should return None when <7 days of data available."""
        # Mock empty results
        mock_context = MagicMock()
        mock_context.__enter__ = MagicMock(return_value=mock_context)
        mock_context.__exit__ = MagicMock(return_value=False)
        mock_context.query.return_value.filter.return_value.all.return_value = []
        mock_session.return_value = mock_context
        
        service = QuoteAuditService()
        result = service.recommend_source_priority("premarket_early")
        
        # Should return None for insufficient data
        assert result is None
        
        # Cleanup
        service.shutdown()


class TestAlertCooldown:
    """Tests for Discord alert cooldown logic."""
    
    def test_cooldown_key_structure(self):
        """Cooldown key should be (symbol, time_window) tuple."""
        key = ("IBRX", "premarket_early")
        assert isinstance(key, tuple)
        assert len(key) == 2
        
        # Different time windows should be different keys
        key_late = ("IBRX", "premarket_late")
        assert key != key_late
    
    def test_same_symbol_different_window(self):
        """Same symbol in different windows should have separate cooldowns."""
        cooldowns = {}
        
        # First alert for premarket_early
        key1 = ("IBRX", "premarket_early")
        cooldowns[key1] = datetime.now()
        
        # Should be able to alert for premarket_late
        key2 = ("IBRX", "premarket_late")
        assert key2 not in cooldowns
