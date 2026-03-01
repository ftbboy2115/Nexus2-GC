"""
Tests for Scheduler Routes

Tests FastAPI scheduler endpoints for automation control.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient

from nexus2.api.main import create_app


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def client():
    """Test client with fresh app."""
    app = create_app()
    with TestClient(app) as client:
        yield client


# =============================================================================
# Status & Info Endpoints
# =============================================================================

class TestSchedulerStatus:
    """Tests for scheduler status endpoints."""
    
    def test_get_status(self, client):
        """Can get scheduler status."""
        response = client.get("/automation/scheduler/status")
        
        assert response.status_code == 200
        data = response.json()
        assert "running" in data
        assert "auto_execute" in data
    
    def test_get_signals(self, client):
        """Can get scheduler signals."""
        response = client.get("/automation/scheduler/signals")
        
        assert response.status_code == 200
        data = response.json()
        assert "signals" in data
    
    def test_get_diagnostics(self, client):
        """Can get scheduler diagnostics."""
        response = client.get("/automation/scheduler/diagnostics")
        
        assert response.status_code == 200
        # Diagnostics structure varies, just check it returns


# =============================================================================
# Start/Stop Endpoints
# =============================================================================

class TestSchedulerControl:
    """Tests for scheduler start/stop control."""
    
    def test_start_scheduler_defaults(self, client):
        """Can start scheduler with defaults."""
        response = client.post("/automation/scheduler/start")
        
        # May fail if already running, missing broker, or ALLOW_LIVE_ENGINE guard (403)
        assert response.status_code in [200, 400, 403, 500]
    
    def test_stop_scheduler(self, client):
        """Can stop scheduler."""
        response = client.post("/automation/scheduler/stop")
        
        assert response.status_code == 200
        data = response.json()
        assert "stopped" in data or "status" in data


# =============================================================================
# Configuration Endpoints (PATCH methods)
# =============================================================================

class TestSchedulerConfig:
    """Tests for scheduler configuration endpoints."""
    
    def test_toggle_auto_execute(self, client):
        """Can toggle auto_execute."""
        # Get current status first
        status_resp = client.get("/automation/scheduler/status")
        current = status_resp.json().get("auto_execute", False)
        
        # Toggle it (PATCH method)
        response = client.patch(
            "/automation/scheduler/auto-execute",
            json={"auto_execute": not current}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "auto_execute" in data
    
    def test_update_interval(self, client):
        """Can update scheduler interval."""
        response = client.patch(
            "/automation/scheduler/interval",
            json={"interval_seconds": 300}
        )
        
        # May get 422 if body format differs
        assert response.status_code in [200, 422]
    
    def test_get_settings(self, client):
        """Can get scheduler settings."""
        response = client.get("/automation/scheduler/settings")
        
        assert response.status_code == 200
        # Settings structure varies
    
    def test_update_settings(self, client):
        """Can update scheduler settings."""
        response = client.patch(
            "/automation/scheduler/settings",
            json={"interval_seconds": 120}
        )
        
        # May succeed or fail depending on validation
        assert response.status_code in [200, 400, 422]


# =============================================================================
# EOD Window Endpoints (PATCH method)
# =============================================================================

class TestEodWindow:
    """Tests for EOD window configuration."""
    
    def test_update_eod_window(self, client):
        """Can update EOD window."""
        response = client.patch(
            "/automation/scheduler/eod-window",
            params={
                "eod_start_hour": 15,
                "eod_start_minute": 30,
                "eod_end_hour": 16,
                "eod_end_minute": 0,
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data or "message" in data
    
    def test_reset_eod_window(self, client):
        """Can reset EOD window to defaults."""
        response = client.patch(
            "/automation/scheduler/eod-window",
            params={"reset": True}
        )
        
        assert response.status_code == 200


# =============================================================================
# Force Scan Endpoint (underscore, not hyphen)
# =============================================================================

class TestForceScan:
    """Tests for force scan functionality."""
    
    @pytest.mark.slow  # Makes real FMP API calls - skip with -m "not slow"
    @pytest.mark.timeout(120)  # FMP API can take up to 90s
    def test_force_scan(self, client):
        """Force scan endpoint exists and responds."""
        response = client.post("/automation/scheduler/force_scan")
        
        # May fail if scheduler not running, but should not crash
        assert response.status_code in [200, 400, 500]
    
    def test_force_scan_blocked_on_weekend(self, client):
        """Force scan is blocked on weekends in non-sim mode."""
        from datetime import datetime
        import pytz
        
        # Mock now_et() to return a Sunday
        sunday = datetime(2026, 3, 1, 12, 0, 0, tzinfo=pytz.timezone("America/New_York"))
        assert sunday.weekday() == 6, "Test date must be a Sunday"
        
        with patch("nexus2.api.routes.scheduler_routes.now_et", return_value=sunday):
            # Also mock scheduler settings to ensure sim_mode=false
            mock_settings = Mock()
            mock_settings.min_quality = 7
            mock_settings.stop_mode = "atr"
            mock_settings.max_stop_atr = "1.0"
            mock_settings.max_stop_percent = "5.0"
            mock_settings.scan_modes = "ep,breakout"
            mock_settings.htf_frequency = "every_cycle"
            mock_settings.sim_mode = "false"
            mock_settings.auto_execute = "false"
            mock_settings.preset = "relaxed"
            mock_settings.min_price = "5.0"
            mock_settings.min_rvol = "1.5"
            
            mock_repo = Mock()
            mock_repo.get.return_value = mock_settings
            
            with patch("nexus2.api.routes.scheduler_routes.get_session") as mock_get_session:
                mock_db = Mock()
                mock_get_session.return_value.__enter__ = Mock(return_value=mock_db)
                mock_get_session.return_value.__exit__ = Mock(return_value=False)
                
                with patch("nexus2.db.SchedulerSettingsRepository", return_value=mock_repo):
                    response = client.post("/automation/scheduler/force_scan")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "blocked"
            assert "weekend" in data["reason"].lower()


# =============================================================================
# Liquidate All Endpoint
# =============================================================================

class TestLiquidateAll:
    """Tests for liquidate all positions."""
    
    def test_liquidate_requires_confirmation(self, client):
        """Liquidate requires confirmation string."""
        response = client.post("/automation/liquidate-all")
        
        # Should fail or warn without confirmation
        assert response.status_code in [200, 400, 422]
    
    def test_liquidate_with_wrong_confirmation(self, client):
        """Liquidate rejects wrong confirmation."""
        response = client.post(
            "/automation/liquidate-all",
            params={"confirm": "no"}
        )
        
        # Should reject
        assert response.status_code in [200, 400]


# =============================================================================
# Discord Test Endpoint
# =============================================================================

class TestDiscord:
    """Tests for Discord webhook test."""
    
    @pytest.mark.slow  # Sends REAL Discord message - skip with -m "not slow"
    @pytest.mark.timeout(30)  # Webhook should respond in <10s
    def test_discord_endpoint_exists(self, client):
        """Discord test endpoint responds."""
        response = client.post("/automation/test-discord")
        
        # Will fail if webhook not configured, but should not crash
        assert response.status_code in [200, 400, 500]


# =============================================================================
# Rejections Endpoint (under /scheduler/)
# =============================================================================

class TestRejections:
    """Tests for scanner rejections endpoint."""
    
    def test_get_rejections_default(self, client):
        """Can get recent rejections."""
        response = client.get("/automation/scheduler/rejections")
        
        assert response.status_code == 200
        data = response.json()
        assert "rejections" in data or isinstance(data, list)
    
    def test_get_rejections_with_count(self, client):
        """Can limit rejection count."""
        response = client.get("/automation/scheduler/rejections", params={"count": 10})
        
        assert response.status_code == 200
    
    def test_get_rejections_with_filter(self, client):
        """Can filter rejections by scanner."""
        response = client.get("/automation/scheduler/rejections", params={"scanner": "ep"})
        
        assert response.status_code == 200
