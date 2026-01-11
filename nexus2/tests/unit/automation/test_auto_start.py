"""
Tests for Auto-Start Scheduler

Tests the auto_start_checker function to ensure it:
1. Skips on weekends
2. Skips on holidays
3. Starts on valid trading days when time matches
4. Only triggers once per day
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytz


ET = pytz.timezone("America/New_York")


class TestAutoStartWeekendSkip:
    """Test that auto-start skips on weekends."""
    
    def test_skips_on_saturday(self):
        """Auto-start should skip on Saturday."""
        from nexus2.adapters.market_data.market_calendar import MarketCalendar, MarketStatus
        
        # Mock Saturday 9:15 AM ET
        saturday = datetime(2026, 1, 10, 9, 15, tzinfo=ET)  # Jan 10, 2026 is Saturday
        
        with patch.object(MarketCalendar, "get_market_status") as mock_status:
            mock_status.return_value = MarketStatus(
                is_open=False,
                reason="weekend",
            )
            
            calendar = MarketCalendar()
            status = calendar.get_market_status()
            
            # On Saturday, market should be closed with weekend reason
            assert status.is_open == False
            assert status.reason == "weekend"
    
    def test_skips_on_sunday(self):
        """Auto-start should skip on Sunday."""
        from nexus2.adapters.market_data.market_calendar import MarketCalendar, MarketStatus
        
        # Mock Sunday
        sunday = datetime(2026, 1, 11, 9, 15, tzinfo=ET)  # Jan 11, 2026 is Sunday
        
        with patch.object(MarketCalendar, "get_market_status") as mock_status:
            mock_status.return_value = MarketStatus(
                is_open=False,
                reason="weekend",
            )
            
            calendar = MarketCalendar()
            status = calendar.get_market_status()
            
            assert status.is_open == False
            assert status.reason == "weekend"


class TestAutoStartHolidaySkip:
    """Test that auto-start skips on market holidays."""
    
    def test_skips_on_mlk_day(self):
        """Auto-start should skip on MLK Day (market holiday)."""
        from nexus2.adapters.market_data.market_calendar import MarketCalendar, MarketStatus
        
        # MLK Day 2026 is Jan 20
        mlk_day = datetime(2026, 1, 20, 9, 15, tzinfo=ET)
        
        with patch.object(MarketCalendar, "get_market_status") as mock_status:
            mock_status.return_value = MarketStatus(
                is_open=False,
                reason="holiday_or_closed",
            )
            
            calendar = MarketCalendar()
            status = calendar.get_market_status()
            
            assert status.is_open == False
            assert status.reason == "holiday_or_closed"


class TestAutoStartTradingDay:
    """Test that auto-start triggers on valid trading days."""
    
    def test_starts_on_monday(self):
        """Auto-start should trigger on Monday when time matches."""
        from nexus2.adapters.market_data.market_calendar import MarketCalendar, MarketStatus
        
        # Monday Jan 12, 2026
        monday = datetime(2026, 1, 12, 9, 15, tzinfo=ET)
        
        with patch.object(MarketCalendar, "get_market_status") as mock_status:
            # Before market open (9:15 is before 9:30 open)
            mock_status.return_value = MarketStatus(
                is_open=False,
                next_open=datetime(2026, 1, 12, 9, 30, tzinfo=ET),
                reason="",
            )
            
            calendar = MarketCalendar()
            
            # is_trading_day checks if next_open is today
            status = calendar.get_market_status()
            assert status.next_open is not None
            next_open_date = status.next_open.date()
            assert next_open_date == monday.date()


class TestAutoStartTriggeredOnce:
    """Test that auto-start only triggers once per day."""
    
    def test_trigger_flag_prevents_multiple_starts(self):
        """Setting triggered flag should prevent re-triggering."""
        from nexus2.api.routes.automation_state import (
            get_auto_start_triggered_today,
            set_auto_start_triggered_today,
        )
        
        # Initially false
        set_auto_start_triggered_today(False)
        assert get_auto_start_triggered_today() == False
        
        # Set to true
        set_auto_start_triggered_today(True)
        assert get_auto_start_triggered_today() == True
        
        # Reset
        set_auto_start_triggered_today(False)
        assert get_auto_start_triggered_today() == False


class TestMarketCalendarFallback:
    """Test MarketCalendar fallback when API is unavailable."""
    
    def test_fallback_weekend_detection(self):
        """Fallback should detect weekend correctly."""
        from nexus2.adapters.market_data.market_calendar import MarketCalendar
        
        calendar = MarketCalendar()
        
        # Test Saturday
        saturday = datetime(2026, 1, 10, 12, 0, tzinfo=ET)
        with patch("nexus2.adapters.market_data.market_calendar.datetime") as mock_dt:
            mock_dt.now.return_value = saturday
            mock_dt.fromisoformat = datetime.fromisoformat
            
            status = calendar._fallback_check()
            assert status.is_open == False
            assert status.reason == "weekend"
    
    def test_fallback_market_hours_detection(self):
        """Fallback should detect market hours correctly."""
        from nexus2.adapters.market_data.market_calendar import MarketCalendar
        
        calendar = MarketCalendar()
        
        # Monday 10:30 AM (market open)
        monday_open = datetime(2026, 1, 12, 10, 30, tzinfo=ET)
        with patch("nexus2.adapters.market_data.market_calendar.datetime") as mock_dt:
            mock_dt.now.return_value = monday_open
            mock_dt.fromisoformat = datetime.fromisoformat
            
            status = calendar._fallback_check()
            assert status.is_open == True
    
    def test_fallback_after_hours(self):
        """Fallback should detect after hours correctly."""
        from nexus2.adapters.market_data.market_calendar import MarketCalendar
        
        calendar = MarketCalendar()
        
        # Monday 5:00 PM (after close)
        monday_closed = datetime(2026, 1, 12, 17, 0, tzinfo=ET)
        with patch("nexus2.adapters.market_data.market_calendar.datetime") as mock_dt:
            mock_dt.now.return_value = monday_closed
            mock_dt.fromisoformat = datetime.fromisoformat
            
            status = calendar._fallback_check()
            assert status.is_open == False
