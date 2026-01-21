"""
Unit tests for IPO Service.

Tests:
- IPO date calculation (days since IPO)
- Tiered score boost (0-1: +3, 2-7: +2, 8-14: +1)
- Cache operations
- Recent IPO detection
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
from pathlib import Path
import json
import tempfile

from nexus2.domain.automation.ipo_service import IPOService, get_ipo_service


class TestIPOService:
    """Test IPO Service functionality."""
    
    @pytest.fixture
    def ipo_service(self, tmp_path):
        """Create IPO service with temp cache file."""
        with patch('nexus2.domain.automation.ipo_service.IPO_CACHE_FILE', tmp_path / "ipo_cache.json"):
            service = IPOService()
            yield service
    
    def test_get_days_since_ipo_today(self, ipo_service):
        """Test IPO from today returns 0 days."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        ipo_service._cache = {"NEWIPO": today}
        
        days = ipo_service.get_days_since_ipo("NEWIPO")
        assert days == 0
    
    def test_get_days_since_ipo_yesterday(self, ipo_service):
        """Test IPO from yesterday returns 1 day."""
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        ipo_service._cache = {"YEST": yesterday}
        
        days = ipo_service.get_days_since_ipo("YEST")
        assert days == 1
    
    def test_get_days_since_ipo_week_ago(self, ipo_service):
        """Test IPO from 7 days ago."""
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        ipo_service._cache = {"WEEK": week_ago}
        
        days = ipo_service.get_days_since_ipo("WEEK")
        assert days == 7
    
    def test_get_days_since_ipo_not_found(self, ipo_service):
        """Test non-IPO symbol returns None."""
        ipo_service._cache = {}
        
        days = ipo_service.get_days_since_ipo("AAPL")
        assert days is None
    
    def test_is_recent_ipo_true(self, ipo_service):
        """Test recent IPO detection."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        ipo_service._cache = {"NEW": today}
        
        assert ipo_service.is_recent_ipo("NEW") is True
        assert ipo_service.is_recent_ipo("NEW", max_days=0) is True
    
    def test_is_recent_ipo_false_old(self, ipo_service):
        """Test old IPO not considered recent."""
        old = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
        ipo_service._cache = {"OLD": old}
        
        assert ipo_service.is_recent_ipo("OLD") is False
        assert ipo_service.is_recent_ipo("OLD", max_days=14) is False
    
    def test_is_recent_ipo_false_not_ipo(self, ipo_service):
        """Test non-IPO returns False."""
        assert ipo_service.is_recent_ipo("AAPL") is False


class TestIPOScoreBoost:
    """Test tiered IPO score boost logic."""
    
    @pytest.fixture
    def ipo_service(self, tmp_path):
        """Create IPO service with temp cache file."""
        with patch('nexus2.domain.automation.ipo_service.IPO_CACHE_FILE', tmp_path / "ipo_cache.json"):
            service = IPOService()
            yield service
    
    def test_score_boost_day_0(self, ipo_service):
        """Day 0 IPO = +3 boost."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        ipo_service._cache = {"DAY0": today}
        
        assert ipo_service.get_ipo_score_boost("DAY0") == 3
    
    def test_score_boost_day_1(self, ipo_service):
        """Day 1 IPO = +3 boost."""
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        ipo_service._cache = {"DAY1": yesterday}
        
        assert ipo_service.get_ipo_score_boost("DAY1") == 3
    
    def test_score_boost_day_2(self, ipo_service):
        """Day 2 IPO = +2 boost."""
        two_days = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%d")
        ipo_service._cache = {"DAY2": two_days}
        
        assert ipo_service.get_ipo_score_boost("DAY2") == 2
    
    def test_score_boost_day_7(self, ipo_service):
        """Day 7 IPO = +2 boost."""
        week = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        ipo_service._cache = {"DAY7": week}
        
        assert ipo_service.get_ipo_score_boost("DAY7") == 2
    
    def test_score_boost_day_8(self, ipo_service):
        """Day 8 IPO = +1 boost."""
        eight_days = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%d")
        ipo_service._cache = {"DAY8": eight_days}
        
        assert ipo_service.get_ipo_score_boost("DAY8") == 1
    
    def test_score_boost_day_14(self, ipo_service):
        """Day 14 IPO = +1 boost."""
        two_weeks = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")
        ipo_service._cache = {"DAY14": two_weeks}
        
        assert ipo_service.get_ipo_score_boost("DAY14") == 1
    
    def test_score_boost_day_15(self, ipo_service):
        """Day 15 IPO = +0 boost (no longer fresh)."""
        fifteen = (datetime.now(timezone.utc) - timedelta(days=15)).strftime("%Y-%m-%d")
        ipo_service._cache = {"DAY15": fifteen}
        
        assert ipo_service.get_ipo_score_boost("DAY15") == 0
    
    def test_score_boost_not_ipo(self, ipo_service):
        """Non-IPO = +0 boost."""
        ipo_service._cache = {}
        
        assert ipo_service.get_ipo_score_boost("AAPL") == 0


class TestIPOCache:
    """Test IPO cache persistence."""
    
    def test_cache_save_and_load(self, tmp_path):
        """Test cache saves and loads correctly."""
        cache_file = tmp_path / "ipo_cache.json"
        
        with patch('nexus2.domain.automation.ipo_service.IPO_CACHE_FILE', cache_file):
            with patch('nexus2.domain.automation.ipo_service.DATA_DIR', tmp_path):
                # Create service and add data
                service = IPOService()
                service._cache = {"TEST": "2026-01-20"}
                service._last_refresh = datetime(2026, 1, 20, 12, 0, 0, tzinfo=timezone.utc)
                service._save_cache()
                
                # Create new service and verify load
                service2 = IPOService()
                assert "TEST" in service2._cache
                assert service2._cache["TEST"] == "2026-01-20"
    
    def test_get_recent_ipos(self, tmp_path):
        """Test getting list of recent IPOs."""
        with patch('nexus2.domain.automation.ipo_service.IPO_CACHE_FILE', tmp_path / "ipo_cache.json"):
            service = IPOService()
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
            month_ago = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
            
            service._cache = {
                "NEW": today,
                "WEEK": week_ago,
                "OLD": month_ago,
            }
            
            recent = service.get_recent_ipos(max_days=14)
            symbols = [r["symbol"] for r in recent]
            
            assert "NEW" in symbols
            assert "WEEK" in symbols
            assert "OLD" not in symbols  # Too old
    
    def test_get_status(self, tmp_path):
        """Test status returns correct info."""
        with patch('nexus2.domain.automation.ipo_service.IPO_CACHE_FILE', tmp_path / "ipo_cache.json"):
            service = IPOService()
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            service._cache = {"IPO1": today, "IPO2": today}
            service._last_refresh = datetime.now(timezone.utc)
            
            status = service.get_status()
            
            assert status["cache_size"] == 2
            assert status["last_refresh"] is not None
            assert "recent_ipos_14d" in status
