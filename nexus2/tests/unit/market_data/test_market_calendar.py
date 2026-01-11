"""
Tests for Market Calendar

Tests market status, holiday detection, and fallback logic.
"""

import pytest
from datetime import datetime, time
from unittest.mock import Mock, patch, MagicMock
import pytz

from nexus2.adapters.market_data.market_calendar import (
    MarketCalendar,
    MarketStatus,
    get_market_calendar,
)


ET = pytz.timezone("America/New_York")


# =============================================================================
# MarketStatus Tests
# =============================================================================

class TestMarketStatus:
    """Tests for MarketStatus dataclass."""
    
    def test_create_open_status(self):
        """Can create status for open market."""
        status = MarketStatus(is_open=True)
        
        assert status.is_open == True
        assert status.is_early_close == False
        assert status.reason == ""
    
    def test_create_closed_status(self):
        """Can create status for closed market."""
        status = MarketStatus(
            is_open=False,
            reason="holiday_or_closed",
        )
        
        assert status.is_open == False
        assert status.reason == "holiday_or_closed"
    
    def test_early_close_status(self):
        """Can create status for early close."""
        status = MarketStatus(
            is_open=True,
            is_early_close=True,
            reason="early_close",
        )
        
        assert status.is_open == True
        assert status.is_early_close == True
        assert status.reason == "early_close"


# =============================================================================
# Fallback Check Tests
# =============================================================================

class TestFallbackCheck:
    """Tests for fallback market hours check."""
    
    @pytest.fixture
    def calendar(self):
        """Create calendar with dummy credentials."""
        with patch.object(MarketCalendar, '__del__', lambda x: None):
            cal = MarketCalendar(paper=True)
            yield cal
    
    def test_weekend_saturday(self, calendar):
        """Saturday should be closed."""
        # Saturday
        saturday = datetime(2026, 1, 10, 12, 0, 0, tzinfo=ET)  # Saturday noon
        
        with patch("nexus2.adapters.market_data.market_calendar.datetime") as mock_dt:
            mock_dt.now.return_value = saturday
            
            status = calendar._fallback_check()
            
            assert status.is_open == False
            assert status.reason == "weekend"
    
    def test_weekend_sunday(self, calendar):
        """Sunday should be closed."""
        sunday = datetime(2026, 1, 11, 12, 0, 0, tzinfo=ET)  # Sunday noon
        
        with patch("nexus2.adapters.market_data.market_calendar.datetime") as mock_dt:
            mock_dt.now.return_value = sunday
            
            status = calendar._fallback_check()
            
            assert status.is_open == False
            assert status.reason == "weekend"
    
    def test_weekday_market_hours(self, calendar):
        """Weekday during market hours should be open."""
        # Monday at 11:00 AM ET
        monday = datetime(2026, 1, 12, 11, 0, 0, tzinfo=ET)
        
        with patch("nexus2.adapters.market_data.market_calendar.datetime") as mock_dt:
            mock_dt.now.return_value = monday
            
            status = calendar._fallback_check()
            
            assert status.is_open == True
    
    def test_weekday_before_open(self, calendar):
        """Weekday before 9:30 AM should be closed."""
        # Monday at 9:00 AM ET
        monday = datetime(2026, 1, 12, 9, 0, 0, tzinfo=ET)
        
        with patch("nexus2.adapters.market_data.market_calendar.datetime") as mock_dt:
            mock_dt.now.return_value = monday
            
            status = calendar._fallback_check()
            
            assert status.is_open == False
    
    def test_weekday_after_close(self, calendar):
        """Weekday after 4:00 PM should be closed."""
        # Monday at 5:00 PM ET
        monday = datetime(2026, 1, 12, 17, 0, 0, tzinfo=ET)
        
        with patch("nexus2.adapters.market_data.market_calendar.datetime") as mock_dt:
            mock_dt.now.return_value = monday
            
            status = calendar._fallback_check()
            
            assert status.is_open == False
    
    def test_market_open_boundary(self, calendar):
        """9:30 AM should be open."""
        # Monday at 9:30 AM ET
        monday = datetime(2026, 1, 12, 9, 30, 0, tzinfo=ET)
        
        with patch("nexus2.adapters.market_data.market_calendar.datetime") as mock_dt:
            mock_dt.now.return_value = monday
            
            status = calendar._fallback_check()
            
            assert status.is_open == True
    
    def test_market_close_boundary(self, calendar):
        """4:00 PM should be open (inclusive)."""
        # Monday at 4:00 PM ET
        monday = datetime(2026, 1, 12, 16, 0, 0, tzinfo=ET)
        
        with patch("nexus2.adapters.market_data.market_calendar.datetime") as mock_dt:
            mock_dt.now.return_value = monday
            
            status = calendar._fallback_check()
            
            assert status.is_open == True


# =============================================================================
# Cache Tests
# =============================================================================

class TestCache:
    """Tests for market status caching."""
    
    @pytest.fixture
    def calendar(self):
        """Create calendar with dummy credentials."""
        with patch.object(MarketCalendar, '__del__', lambda x: None):
            cal = MarketCalendar(paper=True)
            yield cal
    
    def test_cache_initially_invalid(self, calendar):
        """Cache should be invalid initially."""
        assert calendar._is_cache_valid() == False
    
    def test_cache_valid_after_set(self, calendar):
        """Cache should be valid after setting."""
        calendar._cache = MarketStatus(is_open=True)
        calendar._cache_time = datetime.now()
        
        assert calendar._is_cache_valid() == True
    
    def test_cache_expired(self, calendar):
        """Cache should expire after TTL."""
        calendar._cache = MarketStatus(is_open=True)
        calendar._cache_time = datetime.now()
        calendar._cache_ttl_seconds = 0  # Immediate expiry
        
        import time as time_module
        time_module.sleep(0.1)
        
        assert calendar._is_cache_valid() == False


# =============================================================================
# Singleton Tests
# =============================================================================

class TestSingleton:
    """Tests for singleton pattern."""
    
    def test_get_market_calendar_returns_same_instance(self):
        """Singleton should return same instance."""
        # Reset singleton
        import nexus2.adapters.market_data.market_calendar as mc
        mc._market_calendar = None
        
        with patch.object(MarketCalendar, '__del__', lambda x: None):
            cal1 = get_market_calendar(paper=True)
            cal2 = get_market_calendar(paper=True)
            
            assert cal1 is cal2
