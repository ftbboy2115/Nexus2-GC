"""
Tests for Warrior Trading API Routes

Tests the Warrior Trading API endpoints to ensure:
1. Endpoints exist and respond correctly
2. Simulation mode operations work
3. Error handling for edge cases
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi.testclient import TestClient


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def test_client():
    """Create a test client for the FastAPI app."""
    from nexus2.api.main import app
    return TestClient(app)


@pytest.fixture
def mock_engine():
    """Create a properly mocked WarriorEngine."""
    engine = MagicMock()
    
    # Mock get_status to return a proper dict
    engine.get_status.return_value = {
        "engine_state": "STOPPED",
        "sim_only": True,
        "watchlist": [],
        "watchlist_count": 0,  # Required by /watchlist endpoint
        "positions": [],
        "stats": {"total_entries": 0, "wins": 0, "losses": 0},
        "config": {"max_candidates": 5, "risk_per_trade": 100.0},
    }
    
    # Mock async methods
    engine.start = AsyncMock(return_value={"status": "started", "state": "RUNNING"})
    engine.stop = AsyncMock(return_value={"status": "stopped", "state": "STOPPED"})
    engine.pause = AsyncMock(return_value={"status": "paused", "state": "PAUSED"})
    engine.resume = AsyncMock(return_value={"status": "resumed", "state": "RUNNING"})
    
    # Config object
    engine.config = MagicMock()
    engine.config.sim_only = True
    engine.config.risk_per_trade = Decimal("100.0")
    engine.config.max_positions = 10
    engine.config.max_candidates = 5
    engine._get_quote = MagicMock()
    
    return engine


# =============================================================================
# STATUS ENDPOINT TESTS
# =============================================================================

class TestWarriorStatusEndpoint:
    """Test GET /warrior/status endpoint."""
    
    def test_status_endpoint_exists(self, test_client, mock_engine):
        """GET /warrior/status should return 200."""
        with patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_engine):
            response = test_client.get("/warrior/status")
            assert response.status_code == 200
    
    def test_status_returns_dict(self, test_client, mock_engine):
        """GET /warrior/status should return a dict with expected keys."""
        with patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_engine):
            response = test_client.get("/warrior/status")
            data = response.json()
            
            assert isinstance(data, dict)
            assert "engine_state" in data
            assert "sim_only" in data


# =============================================================================
# ENGINE CONTROL TESTS
# =============================================================================

class TestWarriorEngineControlEndpoints:
    """Test engine control endpoints."""
    
    def test_start_endpoint_exists(self, test_client, mock_engine):
        """POST /warrior/start should exist."""
        with patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_engine):
            response = test_client.post("/warrior/start", json={})
            assert response.status_code == 200
    
    def test_stop_endpoint_exists(self, test_client, mock_engine):
        """POST /warrior/stop should exist."""
        with patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_engine):
            response = test_client.post("/warrior/stop")
            assert response.status_code == 200
    
    def test_pause_endpoint_exists(self, test_client, mock_engine):
        """POST /warrior/pause should exist."""
        with patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_engine):
            response = test_client.post("/warrior/pause")
            assert response.status_code == 200
    
    def test_resume_endpoint_exists(self, test_client, mock_engine):
        """POST /warrior/resume should exist."""
        with patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_engine):
            response = test_client.post("/warrior/resume")
            assert response.status_code == 200
    
    def test_start_calls_engine_start(self, test_client, mock_engine):
        """POST /warrior/start should call engine.start()."""
        with patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_engine):
            test_client.post("/warrior/start", json={"sim_only": True})
            mock_engine.start.assert_called_once()
    
    def test_stop_calls_engine_stop(self, test_client, mock_engine):
        """POST /warrior/stop should call engine.stop()."""
        with patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_engine):
            test_client.post("/warrior/stop")
            mock_engine.stop.assert_called_once()


# =============================================================================
# SIMULATION MODE TESTS
# =============================================================================

class TestWarriorSimulationEndpoints:
    """Test simulation mode endpoints."""
    
    def test_sim_status_not_enabled(self, test_client):
        """GET /warrior/sim/status should handle not enabled."""
        with patch("nexus2.api.routes.warrior_routes.get_warrior_sim_broker", return_value=None):
            response = test_client.get("/warrior/sim/status")
            assert response.status_code == 200
            data = response.json()
            # Check response indicates sim not enabled
            assert data.get("sim_enabled") == False or "enabled" not in data or data.get("status") == "disabled"
    
    def test_sim_enable_creates_broker(self, test_client, mock_engine):
        """POST /warrior/sim/enable should create MockBroker."""
        with patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_engine), \
             patch("nexus2.api.routes.warrior_routes.set_warrior_sim_broker") as mock_set, \
             patch("nexus2.api.routes.warrior_routes.get_warrior_sim_broker", return_value=None):
            
            response = test_client.post("/warrior/sim/enable", json={"initial_cash": 25000.0})
            assert response.status_code == 200
            mock_set.assert_called_once()
    
    def test_sim_order_requires_enabled(self, test_client):
        """POST /warrior/sim/order should require sim enabled."""
        with patch("nexus2.api.routes.warrior_routes.get_warrior_sim_broker", return_value=None):
            response = test_client.post(
                "/warrior/sim/order",
                json={"symbol": "TEST", "shares": 100, "stop_price": 10.0}
            )
            # Should fail because sim not enabled
            assert response.status_code == 400 or response.status_code == 422


class TestWarriorSimOrderSubmission:
    """Test simulation order submission."""
    
    def test_sim_order_submits_to_broker(self, test_client):
        """POST /warrior/sim/order should submit to MockBroker when enabled."""
        mock_broker = MagicMock()
        mock_broker.set_price = MagicMock()
        mock_broker.get_price = MagicMock(return_value=10.50)
        mock_broker.submit_bracket_order = MagicMock(return_value=MagicMock(
            client_order_id="test-123",
            status="FILLED",
            avg_fill_price=10.50,
            filled_qty=100,
            is_accepted=True,
        ))
        mock_broker.get_account = MagicMock(return_value={"cash": 24000, "pnl": 0})
        mock_broker.get_positions = MagicMock(return_value={})
        
        with patch("nexus2.api.routes.warrior_routes.get_warrior_sim_broker", return_value=mock_broker), \
             patch("nexus2.domain.automation.trade_event_service.trade_event_service") as mock_svc:
            mock_svc.log_warrior_entry = MagicMock(return_value="event-123")
            
            response = test_client.post(
                "/warrior/sim/order",
                json={"symbol": "TEST", "shares": 100, "stop_price": 10.0, "trigger_type": "orb"}
            )
            
            # Should succeed
            assert response.status_code == 200
            mock_broker.submit_bracket_order.assert_called_once()


class TestWarriorSimPriceUpdate:
    """Test simulation price updates."""
    
    def test_sim_price_requires_enabled(self, test_client):
        """POST /warrior/sim/price/{symbol} should require sim enabled."""
        with patch("nexus2.api.routes.warrior_routes.get_warrior_sim_broker", return_value=None):
            response = test_client.post("/warrior/sim/price/TEST?price=15.50")
            # Should fail gracefully
            assert response.status_code in [400, 404]


# =============================================================================
# SCANNER SETTINGS TESTS
# =============================================================================

class TestWarriorScannerSettings:
    """Test scanner settings endpoints."""
    
    def test_get_scanner_settings_exists(self, test_client, mock_engine):
        """GET /warrior/scanner/settings should exist."""
        mock_engine.scanner = MagicMock()
        mock_engine.scanner.settings = MagicMock()
        mock_engine.scanner.settings.max_float = 100_000_000
        mock_engine.scanner.settings.min_rvol = 2.0
        mock_engine.scanner.settings.min_gap_percent = 4.0
        mock_engine.scanner.settings.min_price = 1.50
        mock_engine.scanner.settings.max_price = 20.0
        mock_engine.scanner.settings.require_catalyst = True
        
        with patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_engine):
            response = test_client.get("/warrior/scanner/settings")
            assert response.status_code == 200


# =============================================================================
# DIAGNOSTIC ENDPOINT TESTS
# =============================================================================

class TestWarriorDiagnostics:
    """Test diagnostics endpoint."""
    
    def test_diagnostics_endpoint_exists(self, test_client, mock_engine):
        """GET /warrior/diagnostics should exist."""
        # Mock all required attributes
        mock_engine.scanner = MagicMock()
        mock_engine.scanner.last_scan_time = None
        mock_engine.scanner.last_results = []
        mock_engine.scanner.rejection_stats = {}
        mock_engine._monitor = MagicMock()
        mock_engine._monitor._running = False
        
        with patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_engine):
            response = test_client.get("/warrior/diagnostics")
            assert response.status_code == 200


# =============================================================================
# POSITIONS & WATCHLIST TESTS
# =============================================================================

class TestWarriorPositionsAndWatchlist:
    """Test positions and watchlist endpoints."""
    
    def test_get_positions_exists(self, test_client, mock_engine):
        """GET /warrior/positions should exist."""
        mock_engine.positions = {}
        mock_engine._get_quote = AsyncMock(return_value=10.0)
        
        with patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_engine):
            response = test_client.get("/warrior/positions")
            assert response.status_code == 200
    
    def test_get_watchlist_exists(self, test_client, mock_engine):
        """GET /warrior/watchlist should exist and return data."""
        mock_engine.watchlist = {"TEST": {"entry": 10.0}}
        
        with patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_engine):
            response = test_client.get("/warrior/watchlist")
            # Just verify endpoint exists and returns 200
            assert response.status_code == 200
