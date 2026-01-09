"""
Warrior Trading Integration Tests

End-to-end tests for the Warrior Trading system:
- Scanner → Engine → Monitor flow
- API endpoint validation
- Position lifecycle
"""

import pytest
from decimal import Decimal
from datetime import datetime, time
from unittest.mock import Mock, patch, AsyncMock

# ============================================================================
# Test: WarriorScannerService Integration
# ============================================================================

class TestWarriorScannerIntegration:
    """Test scanner with mocked market data."""
    
    def test_scanner_settings_defaults(self):
        """Scanner settings should have correct defaults."""
        from nexus2.domain.scanner.warrior_scanner_service import WarriorScanSettings
        
        settings = WarriorScanSettings()
        
        assert settings.max_float == 100_000_000  # 100M
        assert settings.ideal_float == 20_000_000  # 20M
        assert settings.min_rvol == Decimal("2.0")
        assert settings.ideal_rvol == Decimal("3.0")
        assert settings.min_gap == Decimal("4.0")
        assert settings.min_price == Decimal("1.50")
        assert settings.max_price == Decimal("20.0")
        assert settings.exclude_chinese_stocks is True
    
    def test_candidate_quality_score(self):
        """Quality score should reflect how well stock matches ideal criteria."""
        from nexus2.domain.scanner.warrior_scanner_service import WarriorCandidate
        
        # Create an ideal candidate
        ideal = WarriorCandidate(
            symbol="IDEAL",
            name="Ideal Stock Inc",
            price=Decimal("8.50"),
            gap_percent=Decimal("15.0"),  # Ideal gap (>10%)
            relative_volume=Decimal("4.0"),  # Ideal RVOL (3-5x)
            float_shares=10_000_000,  # Ideal float (<20M)
            catalyst_type="earnings",
            catalyst_description="Beat earnings",
        )
        
        score = ideal.quality_score
        
        # Ideal candidate should score high (8+)
        assert score >= 8, f"Ideal candidate scored {score}, expected 8+"
    
    def test_scanner_chinese_stock_exclusion(self):
        """Scanner should filter out likely Chinese stocks by name."""
        from nexus2.domain.scanner.warrior_scanner_service import WarriorScannerService
        
        scanner = WarriorScannerService()
        scanner.settings.exclude_chinese_stocks = True
        
        # These should be flagged as likely Chinese (by keywords in name)
        assert scanner._is_likely_chinese("China Tech Holdings Ltd") is True
        assert scanner._is_likely_chinese("Shanghai Biotech Group Ltd") is True
        assert scanner._is_likely_chinese("Hong Kong Digital") is True
        
        # These should NOT be flagged (no Chinese indicators)
        assert scanner._is_likely_chinese("Apple Inc") is False
        assert scanner._is_likely_chinese("Tesla Inc") is False
        assert scanner._is_likely_chinese("NIO Inc") is False  # Only keyword-based


# ============================================================================
# Test: WarriorMonitor Exit Logic
# ============================================================================

class TestWarriorMonitorIntegration:
    """Test monitor creation and settings."""
    
    def test_monitor_settings_defaults(self):
        """Monitor settings should have correct defaults."""
        from nexus2.domain.automation.warrior_monitor import (
            WarriorMonitor,
            WarriorMonitorSettings,
        )
        
        settings = WarriorMonitorSettings()
        
        assert settings.mental_stop_cents == Decimal("15")
        assert settings.profit_target_r == 2.0
        assert settings.partial_exit_fraction == 0.5
        assert settings.enable_candle_under_candle is True
        assert settings.enable_topping_tail is True
    
    def test_monitor_position_tracking(self):
        """Monitor should track positions via add_position."""
        from nexus2.domain.automation.warrior_monitor import WarriorMonitor
        
        monitor = WarriorMonitor()
        
        # Initially no positions
        assert len(monitor.get_positions()) == 0
        
        # Add a position
        monitor.add_position(
            position_id="test-123",
            symbol="TEST",
            entry_price=Decimal("5.00"),
            shares=100,
            support_level=Decimal("4.80"),
        )
        
        # Should have one position
        positions = monitor.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "TEST"
        assert positions[0].entry_price == Decimal("5.00")
        
        # Mental stop should be entry - 15 cents
        assert positions[0].mental_stop == Decimal("4.85")
    
    def test_monitor_remove_position(self):
        """Monitor should remove positions correctly."""
        from nexus2.domain.automation.warrior_monitor import WarriorMonitor
        
        monitor = WarriorMonitor()
        
        monitor.add_position("test-1", "AAA", Decimal("10.00"), 50)
        monitor.add_position("test-2", "BBB", Decimal("20.00"), 100)
        
        assert len(monitor.get_positions()) == 2
        
        monitor.remove_position("test-1")
        
        assert len(monitor.get_positions()) == 1
        assert monitor.get_positions()[0].symbol == "BBB"
    
    def test_exit_reason_values(self):
        """Exit reasons should have correct enum values."""
        from nexus2.domain.automation.warrior_monitor import WarriorExitReason
        
        assert WarriorExitReason.MENTAL_STOP.value == "mental_stop"
        assert WarriorExitReason.PROFIT_TARGET.value == "profit_target"
        assert WarriorExitReason.CANDLE_UNDER_CANDLE.value == "candle_under_candle"
        assert WarriorExitReason.TOPPING_TAIL.value == "topping_tail"


# ============================================================================
# Test: WarriorEngine Trading Window
# ============================================================================

class TestWarriorEngineIntegration:
    """Test engine trading window and state management."""
    
    def test_engine_state_values(self):
        """Engine should have correct state enum values."""
        from nexus2.domain.automation.warrior_engine import WarriorEngineState
        
        assert WarriorEngineState.STOPPED.value == "stopped"
        assert WarriorEngineState.RUNNING.value == "running"
        assert WarriorEngineState.PAUSED.value == "paused"
        assert WarriorEngineState.PREMARKET.value == "premarket"
    
    def test_engine_initial_state(self):
        """Engine should start in STOPPED state."""
        from nexus2.domain.automation.warrior_engine import (
            WarriorEngine,
            WarriorEngineState,
        )
        
        engine = WarriorEngine()
        assert engine.state == WarriorEngineState.STOPPED
    
    def test_engine_config_defaults(self):
        """Engine config should have correct defaults."""
        from nexus2.domain.automation.warrior_engine import WarriorEngineConfig
        from datetime import time as dt_time
        
        config = WarriorEngineConfig()
        
        assert config.market_open == dt_time(9, 30)
        assert config.trading_window_end == dt_time(11, 30)
        assert config.risk_per_trade == Decimal("100")
        assert config.max_positions == 3
        assert config.max_daily_loss == Decimal("300")
        assert config.sim_only is True
    
    def test_engine_entry_trigger_types(self):
        """Entry trigger types should have correct values."""
        from nexus2.domain.automation.warrior_engine import EntryTriggerType
        
        assert EntryTriggerType.ORB.value == "orb"
        assert EntryTriggerType.PMH_BREAK.value == "pmh_break"
        assert EntryTriggerType.BULL_FLAG.value == "bull_flag"
    
    def test_engine_status_structure(self):
        """Engine status should return expected structure."""
        from nexus2.domain.automation.warrior_engine import WarriorEngine
        
        engine = WarriorEngine()
        status = engine.get_status()
        
        assert "state" in status
        assert "trading_window" in status
        assert "market_hours" in status
        assert "watchlist_count" in status
        assert "stats" in status
        assert "config" in status


# ============================================================================
# Test: API Endpoints (requires running server)
# ============================================================================

class TestWarriorAPIIntegration:
    """Test API endpoints - requires server to be running."""
    
    @pytest.mark.skip(reason="Requires running server")
    def test_status_endpoint(self):
        """GET /warrior/status should return engine state."""
        import requests
        
        response = requests.get("http://127.0.0.1:8000/warrior/status")
        assert response.status_code == 200
        
        data = response.json()
        assert "state" in data
        assert "config" in data
        assert "monitor" in data
    
    @pytest.mark.skip(reason="Requires running server")
    def test_scanner_run_endpoint(self):
        """POST /warrior/scanner/run should return candidates."""
        import requests
        
        response = requests.post("http://127.0.0.1:8000/warrior/scanner/run")
        assert response.status_code == 200
        
        data = response.json()
        assert "candidates" in data
        assert "processed_count" in data


# ============================================================================
# Run with: python -m pytest nexus2/tests/test_warrior_integration.py -v
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
