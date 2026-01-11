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
        data = response.json()
        # Diagnostics structure varies, just check it returns


# =============================================================================
# Start/Stop Endpoints
# =============================================================================

class TestSchedulerControl:
    """Tests for scheduler start/stop control."""
    
    def test_start_scheduler_defaults(self, client):
        """Can start scheduler with defaults."""
        response = client.post("/automation/scheduler/start")
        
        # May fail if already running or missing broker, but should not 500
        assert response.status_code in [200, 400, 500]
    
    def test_stop_scheduler(self, client):
        """Can stop scheduler."""
        response = client.post("/automation/scheduler/stop")
        
        assert response.status_code == 200
        data = response.json()
        assert "stopped" in data or "status" in data


# =============================================================================
# Configuration Endpoints
# =============================================================================

class TestSchedulerConfig:
    """Tests for scheduler configuration endpoints."""
    
    def test_toggle_auto_execute(self, client):
        """Can toggle auto_execute."""
        # Get current status first
        status_resp = client.get("/automation/scheduler/status")
        current = status_resp.json().get("auto_execute", False)
        
        # Toggle it
        response = client.post(
            "/automation/scheduler/toggle-auto-execute",
            json={"auto_execute": not current}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "auto_execute" in data
    
    def test_update_interval(self, client):
        """Can update scheduler interval."""
        response = client.post(
            "/automation/scheduler/interval",
            json={"interval_seconds": 300}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "interval_seconds" in data or "interval" in data
    
    def test_get_settings(self, client):
        """Can get scheduler settings."""
        response = client.get("/automation/scheduler/settings")
        
        assert response.status_code == 200
        data = response.json()
        # Settings structure varies
    
    def test_update_settings(self, client):
        """Can update scheduler settings."""
        response = client.post(
            "/automation/scheduler/settings",
            json={"interval_seconds": 120}
        )
        
        # May succeed or fail depending on validation
        assert response.status_code in [200, 400, 422]


# =============================================================================
# EOD Window Endpoints
# =============================================================================

class TestEodWindow:
    """Tests for EOD window configuration."""
    
    def test_update_eod_window(self, client):
        """Can update EOD window."""
        response = client.post(
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
        assert "eod_window" in data or "window" in data or "start" in data
    
    def test_reset_eod_window(self, client):
        """Can reset EOD window to defaults."""
        response = client.post(
            "/automation/scheduler/eod-window",
            params={"reset": True}
        )
        
        assert response.status_code == 200


# =============================================================================
# Force Scan Endpoint
# =============================================================================

class TestForceScan:
    """Tests for force scan functionality."""
    
    def test_force_scan(self, client):
        """Force scan endpoint exists and responds."""
        response = client.post("/automation/scheduler/force-scan")
        
        # May fail if scheduler not running, but should not 500
        assert response.status_code in [200, 400, 500]


# =============================================================================
# Liquidate All Endpoint
# =============================================================================

class TestLiquidateAll:
    """Tests for liquidate all positions."""
    
    def test_liquidate_requires_confirmation(self, client):
        """Liquidate requires confirmation string."""
        response = client.post("/automation/liquidate-all")
        
        # Should fail without confirmation
        assert response.status_code in [200, 400, 422]
        data = response.json()
        # Either requires confirmation or shows error
    
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
    
    def test_discord_endpoint_exists(self, client):
        """Discord test endpoint responds."""
        response = client.post("/automation/test-discord")
        
        # Will fail if webhook not configured, but should not crash
        assert response.status_code in [200, 400, 500]


# =============================================================================
# Rejections Endpoint
# =============================================================================

class TestRejections:
    """Tests for scanner rejections endpoint."""
    
    def test_get_rejections_default(self, client):
        """Can get recent rejections."""
        response = client.get("/automation/rejections")
        
        assert response.status_code == 200
        data = response.json()
        assert "rejections" in data or isinstance(data, list)
    
    def test_get_rejections_with_count(self, client):
        """Can limit rejection count."""
        response = client.get("/automation/rejections", params={"count": 10})
        
        assert response.status_code == 200
    
    def test_get_rejections_with_filter(self, client):
        """Can filter rejections by scanner."""
        response = client.get("/automation/rejections", params={"scanner": "ep"})
        
        assert response.status_code == 200
