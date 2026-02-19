"""
Tests for Position Monitor

Tests KK-style stop-loss, trailing stops, and partial exit logic.
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch
from zoneinfo import ZoneInfo

from nexus2.domain.automation.monitor import (
    PositionMonitor,
    ExitSignal,
    ExitReason,
)


# =============================================================================
# Helper
# =============================================================================

def _run(coro):
    """Helper to run async code in sync tests."""
    return asyncio.run(coro)


# =============================================================================
# ExitSignal Tests
# =============================================================================

class TestExitSignal:
    """Tests for ExitSignal dataclass."""
    
    def test_create_stop_hit_signal(self):
        """Can create exit signal for stop hit."""
        signal = ExitSignal(
            position_id="pos-123",
            symbol="NVDA",
            reason=ExitReason.STOP_HIT,
            exit_price=Decimal("450.00"),
            shares_to_exit=100,
            pnl_estimate=Decimal("-500.00"),
        )
        
        assert signal.symbol == "NVDA"
        assert signal.reason == ExitReason.STOP_HIT
        assert signal.pnl_estimate == Decimal("-500.00")
        assert signal.generated_at is not None
    
    def test_all_exit_reasons(self):
        """All exit reasons are defined."""
        assert ExitReason.STOP_HIT.value == "stop_hit"
        assert ExitReason.PROFIT_TARGET.value == "profit_target"
        assert ExitReason.TRAILING_STOP.value == "trailing_stop"
        assert ExitReason.PARTIAL_EXIT.value == "partial_exit"
        assert ExitReason.MANUAL.value == "manual"


# =============================================================================
# PositionMonitor Init Tests
# =============================================================================

class TestPositionMonitorInit:
    """Tests for PositionMonitor initialization."""
    
    def test_default_config(self):
        """Default config has KK-style settings."""
        monitor = PositionMonitor()
        
        assert monitor.check_interval == 60
        assert monitor.enable_trailing_stops == True
        assert monitor.enable_partial_exits == True
        assert monitor.breakeven_threshold_r == 1.0
        assert monitor.kk_style_partials == True
        assert monitor.partial_exit_days == 3
        assert monitor.partial_exit_fraction == 0.5
    
    def test_custom_config(self):
        """Can customize monitor settings."""
        monitor = PositionMonitor(
            check_interval_seconds=30,
            breakeven_threshold_r=0.5,
            partial_exit_days=5,
        )
        
        assert monitor.check_interval == 30
        assert monitor.breakeven_threshold_r == 0.5
        assert monitor.partial_exit_days == 5


# =============================================================================
# Stop-Loss Logic Tests
# =============================================================================

class TestStopLossLogic:
    """Tests for stop-loss detection."""
    
    @pytest.fixture
    def monitor(self):
        """Create monitor with mocked callbacks."""
        m = PositionMonitor(check_interval_seconds=1)
        m.set_callbacks(
            get_positions=AsyncMock(),
            get_price=AsyncMock(),
            execute_exit=AsyncMock(),
        )
        return m
    
    def test_stop_hit_triggers_exit(self, monitor):
        """Price at or below stop triggers exit signal."""
        position = {
            "id": "pos-123",
            "symbol": "NVDA",
            "entry_price": "500.00",
            "current_stop": "480.00",
            "initial_stop": "480.00",
            "remaining_shares": 100,
        }
        
        monitor._get_price = AsyncMock(return_value=Decimal("479.00"))  # Below stop
        
        signal = _run(monitor._evaluate_position(position))
        
        assert signal is not None
        assert signal.reason == ExitReason.STOP_HIT
        assert signal.shares_to_exit == 100
        assert signal.exit_price == Decimal("479.00")
    
    def test_price_above_stop_no_exit(self, monitor):
        """Price above stop does not trigger exit."""
        position = {
            "id": "pos-123",
            "symbol": "NVDA",
            "entry_price": "500.00",
            "current_stop": "480.00",
            "initial_stop": "480.00",
            "remaining_shares": 100,
        }
        
        monitor._get_price = AsyncMock(return_value=Decimal("510.00"))  # Above stop
        
        signal = _run(monitor._evaluate_position(position))
        
        assert signal is None
    
    def test_position_without_stop_skipped(self, monitor):
        """Positions without stops are not evaluated."""
        position = {
            "id": "pos-123",
            "symbol": "NVDA",
            "entry_price": "500.00",
            "current_stop": None,
            "initial_stop": None,
            "remaining_shares": 100,
        }
        
        signal = _run(monitor._evaluate_position(position))
        
        assert signal is None
    
    def test_zero_shares_skipped(self, monitor):
        """Positions with zero shares are skipped."""
        position = {
            "id": "pos-123",
            "symbol": "NVDA",
            "entry_price": "500.00",
            "current_stop": "480.00",
            "initial_stop": "480.00",
            "remaining_shares": 0,
        }
        
        signal = _run(monitor._evaluate_position(position))
        
        assert signal is None


# =============================================================================
# KK-Style Partial Exit Tests
# =============================================================================

class TestKKPartialExit:
    """Tests for KK-style day-based partial exits."""
    
    @pytest.fixture
    def monitor(self):
        """Create monitor with KK-style partials enabled."""
        m = PositionMonitor(
            kk_style_partials=True,
            partial_exit_days=3,
            partial_exit_fraction=0.5,
        )
        m.set_callbacks(
            get_positions=AsyncMock(),
            get_price=AsyncMock(),
            execute_exit=AsyncMock(),
            update_stop=AsyncMock(),
        )
        return m
    
    def test_day_3_in_profit_triggers_partial(self, monitor):
        """Day 3+ and in profit triggers partial exit."""
        et = ZoneInfo("America/New_York")
        opened_at = datetime.now(et) - timedelta(days=4)
        
        position = {
            "id": "pos-123",
            "symbol": "NVDA",
            "entry_price": "500.00",
            "current_stop": "480.00",
            "initial_stop": "480.00",
            "opened_at": opened_at,
            "remaining_shares": 100,
            "partial_taken": False,
        }
        
        current_price = Decimal("550.00")  # In profit
        
        signal = _run(monitor._check_partial_exit(
            position, current_price, Decimal("500.00"), 100, 2.5
        ))
        
        assert signal is not None
        assert signal.reason == ExitReason.PARTIAL_EXIT
        assert signal.shares_to_exit == 50  # 50% of 100
        assert signal.days_held >= 3
    
    def test_day_1_no_partial(self, monitor):
        """Day 1 does not trigger partial exit."""
        et = ZoneInfo("America/New_York")
        opened_at = datetime.now(et) - timedelta(days=1)
        
        position = {
            "id": "pos-123",
            "symbol": "NVDA",
            "entry_price": "500.00",
            "opened_at": opened_at,
            "remaining_shares": 100,
            "partial_taken": False,
        }
        
        current_price = Decimal("550.00")  # In profit
        
        signal = _run(monitor._check_partial_exit(
            position, current_price, Decimal("500.00"), 100, 2.5
        ))
        
        assert signal is None
    
    def test_day_3_underwater_no_partial(self, monitor):
        """Day 3 but underwater does not trigger partial."""
        et = ZoneInfo("America/New_York")
        opened_at = datetime.now(et) - timedelta(days=4)
        
        position = {
            "id": "pos-123",
            "symbol": "NVDA",
            "entry_price": "500.00",
            "opened_at": opened_at,
            "remaining_shares": 100,
            "partial_taken": False,
        }
        
        current_price = Decimal("490.00")  # Below entry (underwater)
        
        signal = _run(monitor._check_partial_exit(
            position, current_price, Decimal("500.00"), 100, -0.5
        ))
        
        assert signal is None
    
    def test_partial_already_taken_no_repeat(self, monitor):
        """Partial already taken does not trigger another."""
        et = ZoneInfo("America/New_York")
        opened_at = datetime.now(et) - timedelta(days=4)
        
        position = {
            "id": "pos-123",
            "symbol": "NVDA",
            "entry_price": "500.00",
            "opened_at": opened_at,
            "remaining_shares": 50,
            "partial_taken": True,  # Already taken
        }
        
        current_price = Decimal("600.00")  # Very profitable
        
        signal = _run(monitor._check_partial_exit(
            position, current_price, Decimal("500.00"), 50, 5.0
        ))
        
        assert signal is None


# =============================================================================
# Status Tests
# =============================================================================

class TestPositionMonitorStatus:
    """Tests for get_status method."""
    
    def test_initial_status(self):
        """Status shows initial state."""
        monitor = PositionMonitor()
        status = monitor.get_status()
        
        assert status["running"] == False
        assert status["checks_run"] == 0
        assert status["exits_triggered"] == 0
        assert status["settings"]["kk_style_partials"] == True
    
    def test_status_after_checks(self):
        """Status updates after running checks."""
        monitor = PositionMonitor()
        monitor.checks_run = 5
        monitor.exits_triggered = 2
        monitor._running = True
        
        status = monitor.get_status()
        
        assert status["running"] == True
        assert status["checks_run"] == 5
        assert status["exits_triggered"] == 2


# =============================================================================
# Start/Stop Tests
# =============================================================================

class TestStartStop:
    """Tests for start/stop functionality."""
    
    def test_start_returns_status(self):
        """Start returns status dict."""
        monitor = PositionMonitor()
        monitor.set_callbacks(get_positions=AsyncMock(return_value=[]))
        
        # Mock market calendar at the import source
        with patch("nexus2.adapters.market_data.market_calendar.get_market_calendar") as mock_cal:
            mock_cal.return_value.is_market_open.return_value = False
            
            result = _run(monitor.start())
            
            assert result["status"] == "started"
            assert result["mode"] == "polling"
            
            _run(monitor.stop())
    
    def test_stop_when_already_stopped(self):
        """Stop when already stopped returns already_stopped."""
        monitor = PositionMonitor()
        
        result = _run(monitor.stop())
        
        assert result["status"] == "already_stopped"
