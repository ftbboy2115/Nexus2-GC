"""
Tests for Warrior Trading API Routes

Tests the Warrior Trading API endpoints to ensure:
1. Engine control (start/stop/pause/resume)
2. Status and configuration endpoints
3. Simulation mode operations
4. Position and watchlist management
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi.testclient import TestClient


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_warrior_engine():
    """Create a mock WarriorEngine."""
    engine = MagicMock()
    engine.state.name = "STOPPED"
    engine.watchlist = {}
    engine.positions = {}
    engine.stats = {
        "total_entries": 0,
        "total_exits": 0,
        "wins": 0,
        "losses": 0,
        "gross_pnl": 0.0,
    }
    engine.sim_only = True
    engine.config = MagicMock()
    engine.config.risk_per_trade = 100.0
    engine.config.max_positions = 10
    engine.config.max_candidates = 5
    engine.config.orb_enabled = True
    engine.config.pmh_enabled = True
    engine.config.max_daily_loss = 500.0
    engine.config.scanner_interval_minutes = 1
    return engine


@pytest.fixture
def mock_warrior_monitor():
    """Create a mock WarriorMonitor."""
    monitor = MagicMock()
    monitor._running = False
    monitor.positions = {}
    monitor.settings = MagicMock()
    monitor.settings.mental_stop_cents = 15
    monitor.settings.profit_target_r = 2.0
    monitor.settings.profit_target_cents = 0
    monitor.settings.partial_exit_fraction = 0.5
    return monitor


@pytest.fixture
def test_client():
    """Create a test client for the FastAPI app."""
    from nexus2.api.main import app
    return TestClient(app)


# =============================================================================
# ENGINE STATUS TESTS
# =============================================================================

class TestWarriorStatus:
    """Test Warrior status endpoint."""
    
    def test_get_status_returns_engine_state(self, test_client, mock_warrior_engine):
        """GET /warrior/status should return engine state."""
        with patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_warrior_engine):
            response = test_client.get("/warrior/status")
            
            assert response.status_code == 200
            data = response.json()
            assert "state" in data
            assert data["state"] == "STOPPED"
    
    def test_get_status_includes_watchlist(self, test_client, mock_warrior_engine):
        """GET /warrior/status should include watchlist."""
        mock_warrior_engine.watchlist = {
            "AAPL": {"entry_price": 150.0, "stop_price": 145.0}
        }
        
        with patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_warrior_engine):
            response = test_client.get("/warrior/status")
            
            assert response.status_code == 200
            data = response.json()
            assert "watchlist" in data


# =============================================================================
# ENGINE CONTROL TESTS
# =============================================================================

class TestWarriorEngineControl:
    """Test Warrior engine start/stop/pause/resume."""
    
    def test_start_engine_success(self, test_client, mock_warrior_engine):
        """POST /warrior/start should start the engine."""
        mock_warrior_engine.start = MagicMock(return_value={"status": "started"})
        
        with patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_warrior_engine):
            response = test_client.post(
                "/warrior/start",
                json={"sim_only": True, "risk_per_trade": 100.0}
            )
            
            assert response.status_code == 200
            mock_warrior_engine.start.assert_called_once()
    
    def test_stop_engine_success(self, test_client, mock_warrior_engine):
        """POST /warrior/stop should stop the engine."""
        mock_warrior_engine.state.name = "RUNNING"
        mock_warrior_engine.stop = MagicMock(return_value={"status": "stopped"})
        
        with patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_warrior_engine):
            response = test_client.post("/warrior/stop")
            
            assert response.status_code == 200
            mock_warrior_engine.stop.assert_called_once()
    
    def test_pause_engine_success(self, test_client, mock_warrior_engine):
        """POST /warrior/pause should pause the engine."""
        mock_warrior_engine.state.name = "RUNNING"
        mock_warrior_engine.pause = MagicMock(return_value={"status": "paused"})
        
        with patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_warrior_engine):
            response = test_client.post("/warrior/pause")
            
            assert response.status_code == 200
            mock_warrior_engine.pause.assert_called_once()
    
    def test_resume_engine_success(self, test_client, mock_warrior_engine):
        """POST /warrior/resume should resume the engine."""
        mock_warrior_engine.state.name = "PAUSED"
        mock_warrior_engine.resume = MagicMock(return_value={"status": "running"})
        
        with patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_warrior_engine):
            response = test_client.post("/warrior/resume")
            
            assert response.status_code == 200
            mock_warrior_engine.resume.assert_called_once()


# =============================================================================
# CONFIG UPDATE TESTS
# =============================================================================

class TestWarriorConfigUpdate:
    """Test Warrior configuration updates."""
    
    def test_update_config_max_candidates(self, test_client, mock_warrior_engine):
        """PATCH /warrior/config should update max_candidates."""
        with patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_warrior_engine):
            response = test_client.patch(
                "/warrior/config",
                json={"max_candidates": 10}
            )
            
            assert response.status_code == 200
            assert mock_warrior_engine.config.max_candidates == 10
    
    def test_update_config_risk_per_trade(self, test_client, mock_warrior_engine):
        """PATCH /warrior/config should update risk_per_trade."""
        with patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_warrior_engine):
            response = test_client.patch(
                "/warrior/config",
                json={"risk_per_trade": 200.0}
            )
            
            assert response.status_code == 200
            assert mock_warrior_engine.config.risk_per_trade == 200.0
    
    def test_update_config_toggle_orb(self, test_client, mock_warrior_engine):
        """PATCH /warrior/config should toggle ORB entry type."""
        with patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_warrior_engine):
            response = test_client.patch(
                "/warrior/config",
                json={"orb_enabled": False}
            )
            
            assert response.status_code == 200
            assert mock_warrior_engine.config.orb_enabled == False


# =============================================================================
# SIMULATION MODE TESTS
# =============================================================================

class TestWarriorSimulationMode:
    """Test Warrior simulation mode operations."""
    
    def test_get_sim_status_not_enabled(self, test_client):
        """GET /warrior/sim/status should return not enabled."""
        with patch("nexus2.api.routes.warrior_routes.get_warrior_sim_broker", return_value=None):
            response = test_client.get("/warrior/sim/status")
            
            assert response.status_code == 200
            data = response.json()
            assert data["enabled"] == False
    
    def test_enable_sim_mode(self, test_client, mock_warrior_engine):
        """POST /warrior/sim/enable should create MockBroker."""
        with patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_warrior_engine), \
             patch("nexus2.api.routes.warrior_routes.set_warrior_sim_broker") as mock_set_broker:
            
            response = test_client.post(
                "/warrior/sim/enable",
                json={"initial_cash": 25000.0}
            )
            
            assert response.status_code == 200
            mock_set_broker.assert_called_once()
    
    def test_reset_sim_mode(self, test_client, mock_warrior_engine):
        """POST /warrior/sim/reset should reset MockBroker."""
        mock_broker = MagicMock()
        mock_broker.reset = MagicMock()
        
        with patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_warrior_engine), \
             patch("nexus2.api.routes.warrior_routes.get_warrior_sim_broker", return_value=mock_broker), \
             patch("nexus2.api.routes.warrior_routes.set_warrior_sim_broker"):
            
            response = test_client.post(
                "/warrior/sim/reset",
                json={"initial_cash": 25000.0}
            )
            
            assert response.status_code == 200


class TestWarriorSimOrderFlow:
    """Test Warrior simulation order flow."""
    
    def test_submit_sim_order_success(self, test_client):
        """POST /warrior/sim/order should submit to MockBroker."""
        mock_broker = MagicMock()
        mock_broker.set_price = MagicMock()
        mock_broker.submit_order = MagicMock(return_value=MagicMock(
            client_order_id="test-123",
            status="FILLED",
            avg_fill_price=10.50,
            filled_qty=100,
        ))
        mock_broker.get_account = MagicMock(return_value={"cash": 24000})
        
        with patch("nexus2.api.routes.warrior_routes.get_warrior_sim_broker", return_value=mock_broker), \
             patch("nexus2.domain.automation.trade_event_service.TradeEventService") as mock_svc:
            mock_svc.return_value.log_warrior_entry = MagicMock(return_value="event-123")
            
            response = test_client.post(
                "/warrior/sim/order",
                json={
                    "symbol": "TEST",
                    "shares": 100,
                    "stop_price": 10.00,
                    "trigger_type": "orb"
                }
            )
            
            assert response.status_code == 200
            mock_broker.submit_order.assert_called_once()
    
    def test_submit_sim_order_not_enabled(self, test_client):
        """POST /warrior/sim/order should fail if sim not enabled."""
        with patch("nexus2.api.routes.warrior_routes.get_warrior_sim_broker", return_value=None):
            response = test_client.post(
                "/warrior/sim/order",
                json={
                    "symbol": "TEST",
                    "shares": 100,
                    "stop_price": 10.00,
                }
            )
            
            assert response.status_code == 400
            assert "not enabled" in response.json()["detail"].lower()
    
    def test_sell_sim_position_success(self, test_client):
        """POST /warrior/sim/sell should sell position."""
        mock_broker = MagicMock()
        mock_broker.get_positions = MagicMock(return_value={
            "TEST": {"qty": 100, "avg_price": 10.00}
        })
        mock_broker.submit_order = MagicMock(return_value=MagicMock(
            client_order_id="sell-123",
            status="FILLED",
            avg_fill_price=11.00,
            filled_qty=100,
        ))
        mock_broker.get_account = MagicMock(return_value={"cash": 26100})
        
        with patch("nexus2.api.routes.warrior_routes.get_warrior_sim_broker", return_value=mock_broker), \
             patch("nexus2.domain.automation.trade_event_service.TradeEventService") as mock_svc:
            mock_svc.return_value.log_warrior_exit = MagicMock(return_value="exit-123")
            
            response = test_client.post("/warrior/sim/sell/TEST")
            
            assert response.status_code == 200
            mock_broker.submit_order.assert_called_once()


class TestWarriorSimPriceControl:
    """Test Warrior simulation price control."""
    
    def test_set_sim_price_success(self, test_client, mock_warrior_engine, mock_warrior_monitor):
        """POST /warrior/sim/price should update MockBroker price."""
        mock_broker = MagicMock()
        mock_broker.set_price = MagicMock()
        
        with patch("nexus2.api.routes.warrior_routes.get_warrior_sim_broker", return_value=mock_broker), \
             patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_warrior_engine), \
             patch("nexus2.domain.automation.warrior_monitor.get_monitor", return_value=mock_warrior_monitor):
            
            response = test_client.post("/warrior/sim/price/TEST?price=15.50")
            
            assert response.status_code == 200
            mock_broker.set_price.assert_called_with("TEST", 15.50)
    
    def test_set_sim_price_not_enabled(self, test_client):
        """POST /warrior/sim/price should fail if sim not enabled."""
        with patch("nexus2.api.routes.warrior_routes.get_warrior_sim_broker", return_value=None):
            response = test_client.post("/warrior/sim/price/TEST?price=15.50")
            
            assert response.status_code == 400


# =============================================================================
# SCANNER TESTS
# =============================================================================

class TestWarriorScanner:
    """Test Warrior scanner endpoints."""
    
    def test_get_scanner_settings(self, test_client, mock_warrior_engine):
        """GET /warrior/scanner/settings should return current settings."""
        mock_warrior_engine.scanner = MagicMock()
        mock_warrior_engine.scanner.settings = MagicMock()
        mock_warrior_engine.scanner.settings.max_float = 100_000_000
        mock_warrior_engine.scanner.settings.min_rvol = 2.0
        mock_warrior_engine.scanner.settings.min_gap_percent = 4.0
        mock_warrior_engine.scanner.settings.min_price = 1.50
        mock_warrior_engine.scanner.settings.max_price = 20.0
        mock_warrior_engine.scanner.settings.require_catalyst = True
        
        with patch("nexus2.api.routes.warrior_routes.get_engine", return_value=mock_warrior_engine):
            response = test_client.get("/warrior/scanner/settings")
            
            assert response.status_code == 200
            data = response.json()
            assert "max_float" in data
            assert "min_rvol" in data


# =============================================================================
# MONITOR TESTS
# =============================================================================

class TestWarriorMonitor:
    """Test Warrior monitor endpoints."""
    
    def test_get_monitor_settings(self, test_client, mock_warrior_monitor):
        """GET /warrior/monitor/settings should return current settings."""
        with patch("nexus2.domain.automation.warrior_monitor.get_monitor", return_value=mock_warrior_monitor):
            response = test_client.get("/warrior/monitor/settings")
            
            assert response.status_code == 200
            data = response.json()
            assert "mental_stop_cents" in data
            assert data["mental_stop_cents"] == 15
    
    def test_update_monitor_settings(self, test_client, mock_warrior_monitor):
        """PATCH /warrior/monitor/settings should update settings."""
        with patch("nexus2.domain.automation.warrior_monitor.get_monitor", return_value=mock_warrior_monitor):
            response = test_client.patch(
                "/warrior/monitor/settings",
                json={"mental_stop_cents": 20}
            )
            
            assert response.status_code == 200
            assert mock_warrior_monitor.settings.mental_stop_cents == 20
