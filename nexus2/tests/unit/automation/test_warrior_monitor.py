"""
Tests for Warrior Position Monitor

Tests Ross Cameron-style exit rules:
- Mental stops (10-20 cents)
- Technical stops (support levels)
- Character exits (candle-under-candle, topping tail)
- 2:1 R profit target partials
- After-hours exit logic
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch
from zoneinfo import ZoneInfo

from nexus2.domain.automation.warrior_monitor import (
    WarriorMonitor,
    WarriorMonitorSettings,
    WarriorPosition,
    WarriorExitSignal,
    WarriorExitReason,
    get_warrior_monitor,
)


# =============================================================================
# Helper
# =============================================================================

def _run(coro):
    """Helper to run async code in sync tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


# =============================================================================
# WarriorExitReason Tests
# =============================================================================

class TestWarriorExitReason:
    """Tests for WarriorExitReason enum."""
    
    def test_all_exit_reasons_defined(self):
        """All Warrior exit reasons are defined."""
        assert WarriorExitReason.MENTAL_STOP.value == "mental_stop"
        assert WarriorExitReason.TECHNICAL_STOP.value == "technical_stop"
        assert WarriorExitReason.CANDLE_UNDER_CANDLE.value == "candle_under_candle"
        assert WarriorExitReason.TOPPING_TAIL.value == "topping_tail"
        assert WarriorExitReason.PROFIT_TARGET.value == "profit_target"
        assert WarriorExitReason.PARTIAL_EXIT.value == "partial_exit"
        assert WarriorExitReason.AFTER_HOURS_EXIT.value == "after_hours_exit"


# =============================================================================
# WarriorMonitorSettings Tests
# =============================================================================

class TestWarriorMonitorSettings:
    """Tests for settings dataclass."""
    
    def test_default_settings(self):
        """Default settings follow Ross Cameron rules."""
        s = WarriorMonitorSettings()
        
        assert s.mental_stop_cents == Decimal("15")
        assert s.use_technical_stop == True
        assert s.profit_target_r == 2.0
        assert s.partial_exit_fraction == 0.5
        assert s.enable_candle_under_candle == True
        assert s.enable_topping_tail == True
        assert s.check_interval_seconds == 2  # Fast polling
    
    def test_custom_settings(self):
        """Can customize settings."""
        s = WarriorMonitorSettings(
            mental_stop_cents=Decimal("20"),
            profit_target_cents=Decimal("25"),  # Fixed cents instead of R
        )
        
        assert s.mental_stop_cents == Decimal("20")
        assert s.profit_target_cents == Decimal("25")


# =============================================================================
# Position Management Tests
# =============================================================================

class TestPositionManagement:
    """Tests for add/remove position logic."""
    
    @pytest.fixture
    def monitor(self):
        """Create monitor with mocked callbacks."""
        with patch("nexus2.domain.automation.warrior_monitor.trade_event_service"):
            m = WarriorMonitor()
            m.set_callbacks(
                get_price=AsyncMock(),
                execute_exit=AsyncMock(),
            )
            yield m
    
    def test_add_position_calculates_stops(self, monitor):
        """Adding position calculates mental stop and target."""
        position = monitor.add_position(
            position_id="pos-123",
            symbol="AAPL",
            entry_price=Decimal("150.00"),
            shares=100,
        )
        
        # Mental stop: $150.00 - $0.15 = $149.85
        assert position.mental_stop == Decimal("149.85")
        assert position.current_stop == Decimal("149.85")
        
        # Risk per share: $0.15
        assert position.risk_per_share == Decimal("0.15")
        
        # Profit target (2:1 R): $150.00 + $0.30 = $150.30
        assert position.profit_target == Decimal("150.30")
    
    def test_add_position_with_support(self, monitor):
        """Adding position with support level uses tighter stop."""
        position = monitor.add_position(
            position_id="pos-123",
            symbol="AAPL",
            entry_price=Decimal("150.00"),
            shares=100,
            support_level=Decimal("149.95"),  # Tighter than mental
        )
        
        # Technical stop: $149.95 - $0.05 = $149.90
        assert position.technical_stop == Decimal("149.90")
        
        # Current stop uses tighter of mental ($149.85) vs technical ($149.90)
        # Technical is tighter (higher) so use technical
        assert position.current_stop == Decimal("149.90")
    
    def test_remove_position(self, monitor):
        """Can remove position from monitoring."""
        monitor.add_position("pos-123", "AAPL", Decimal("150.00"), 100)
        
        assert len(monitor.get_positions()) == 1
        
        result = monitor.remove_position("pos-123")
        
        assert result == True
        assert len(monitor.get_positions()) == 0
    
    def test_remove_nonexistent_position(self, monitor):
        """Removing nonexistent position returns False."""
        result = monitor.remove_position("nonexistent")
        
        assert result == False


# =============================================================================
# Mental Stop Tests
# =============================================================================

class TestMentalStop:
    """Tests for mental stop exit logic."""
    
    @pytest.fixture
    def monitor(self):
        """Create monitor with position."""
        with patch("nexus2.domain.automation.warrior_monitor.trade_event_service"):
            m = WarriorMonitor()
            m.set_callbacks(
                get_price=AsyncMock(),
                execute_exit=AsyncMock(),
            )
            m.add_position("pos-123", "AAPL", Decimal("150.00"), 100)
            yield m
    
    def test_price_below_stop_triggers_exit(self, monitor):
        """Price at or below stop triggers mental stop exit."""
        monitor._get_price = AsyncMock(return_value=Decimal("149.80"))
        
        position = list(monitor._positions.values())[0]
        signal = _run(monitor._evaluate_position(position))
        
        assert signal is not None
        assert signal.reason == WarriorExitReason.MENTAL_STOP
        assert signal.shares_to_exit == 100
    
    def test_price_above_stop_no_exit(self, monitor):
        """Price above stop but below target does not trigger exit."""
        # Price between stop ($149.85) and target ($150.30) = no exit
        monitor._get_price = AsyncMock(return_value=Decimal("150.10"))
        
        position = list(monitor._positions.values())[0]
        signal = _run(monitor._evaluate_position(position))
        
        assert signal is None


# =============================================================================
# Profit Target / Partial Exit Tests
# =============================================================================

class TestProfitTarget:
    """Tests for profit target and partial exit logic."""
    
    @pytest.fixture
    def monitor(self):
        """Create monitor with position."""
        with patch("nexus2.domain.automation.warrior_monitor.trade_event_service"):
            m = WarriorMonitor()
            m.set_callbacks(
                get_price=AsyncMock(),
                execute_exit=AsyncMock(),
                update_stop=AsyncMock(),
            )
            m.add_position("pos-123", "AAPL", Decimal("150.00"), 100)
            yield m
    
    @pytest.fixture
    def mock_trading_hours(self):
        """Mock datetime to simulate trading hours (2:00 PM ET)."""
        et = ZoneInfo("America/New_York")
        mock_dt = datetime(2026, 1, 12, 14, 0, 0, tzinfo=et)  # 2:00 PM ET
        with patch("nexus2.domain.automation.warrior_monitor.datetime") as mock_datetime:
            mock_datetime.now.return_value = mock_dt
            mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)
            yield mock_datetime
    
    def test_profit_target_triggers_partial(self, monitor, mock_trading_hours):
        """Hitting profit target triggers partial exit."""
        # Target is $150.30 (2:1 R)
        monitor._get_price = AsyncMock(return_value=Decimal("150.35"))
        
        position = list(monitor._positions.values())[0]
        signal = _run(monitor._evaluate_position(position))
        
        assert signal is not None
        assert signal.reason == WarriorExitReason.PARTIAL_EXIT
        assert signal.shares_to_exit == 50  # 50% of 100
    
    def test_partial_taken_no_repeat(self, monitor, mock_trading_hours):
        """Partial already taken does not trigger again."""
        monitor._get_price = AsyncMock(return_value=Decimal("150.50"))
        
        position = list(monitor._positions.values())[0]
        position.partial_taken = True
        
        signal = _run(monitor._evaluate_position(position))
        
        # No signal because partial already taken
        assert signal is None


# =============================================================================
# Status Tests
# =============================================================================

class TestWarriorMonitorStatus:
    """Tests for get_status method."""
    
    def test_initial_status(self):
        """Status shows initial state."""
        monitor = WarriorMonitor()
        status = monitor.get_status()
        
        assert status["running"] == False
        assert status["positions_count"] == 0
        assert status["checks_run"] == 0
        assert status["exits_triggered"] == 0
        assert status["realized_pnl_today"] == 0.0
    
    def test_daily_pnl_reset(self):
        """Daily PnL resets on new day."""
        monitor = WarriorMonitor()
        monitor._add_realized_pnl(Decimal("100.00"))
        
        assert monitor.realized_pnl_today == Decimal("100.00")
        
        monitor.reset_daily_pnl()
        
        assert monitor.realized_pnl_today == Decimal("0")


# =============================================================================
# Start/Stop Tests
# =============================================================================

class TestWarriorStartStop:
    """Tests for start/stop functionality."""
    
    def test_start_returns_status(self):
        """Start returns status dict."""
        monitor = WarriorMonitor()
        
        with patch("nexus2.adapters.market_data.market_calendar.get_market_calendar") as mock_cal:
            mock_cal.return_value.is_market_open.return_value = False
            
            result = _run(monitor.start())
            
            assert result["status"] == "started"
            assert result["interval"] == 2
            
            _run(monitor.stop())
    
    def test_double_start_returns_already_running(self):
        """Starting twice returns already_running."""
        monitor = WarriorMonitor()
        monitor._running = True
        
        result = _run(monitor.start())
        
        assert result["status"] == "already_running"
    
    def test_stop_when_not_running(self):
        """Stop when not running returns already_stopped."""
        monitor = WarriorMonitor()
        
        result = _run(monitor.stop())
        
        assert result["status"] == "already_stopped"


# =============================================================================
# Singleton Tests
# =============================================================================

class TestWarriorSingleton:
    """Tests for singleton pattern."""
    
    def test_get_warrior_monitor_returns_same_instance(self):
        """Singleton returns same instance."""
        import nexus2.domain.automation.warrior_monitor as wm
        wm._warrior_monitor = None
        
        m1 = get_warrior_monitor()
        m2 = get_warrior_monitor()
        
        assert m1 is m2


# =============================================================================
# 2-Strike Rule Tests (Jan 2026)
# =============================================================================

class TestTwoStrikeRule:
    """Tests for 2-strike rule - blocks entry after 2 stop-outs on same symbol."""
    
    @pytest.fixture
    def monitor(self):
        """Create monitor with mocked callbacks."""
        with patch("nexus2.domain.automation.warrior_monitor.trade_event_service"):
            m = WarriorMonitor()
            m.set_callbacks(
                get_price=AsyncMock(),
                execute_exit=AsyncMock(),
            )
            yield m
    
    def test_record_symbol_fail_callback_wired(self, monitor):
        """record_symbol_fail callback can be set."""
        fail_recorder = Mock()
        monitor.set_callbacks(record_symbol_fail=fail_recorder)
        
        assert monitor._record_symbol_fail == fail_recorder
    
    def test_mental_stop_triggers_fail_callback(self, monitor):
        """Mental stop exit triggers record_symbol_fail callback."""
        fail_recorder = Mock()
        monitor.set_callbacks(record_symbol_fail=fail_recorder)
        
        # Add position
        monitor.add_position("pos-123", "OSS", Decimal("10.00"), 100)
        
        # Create stop exit signal
        signal = WarriorExitSignal(
            position_id="pos-123",
            symbol="OSS",
            reason=WarriorExitReason.MENTAL_STOP,
            exit_price=Decimal("9.85"),
            shares_to_exit=100,
            pnl_estimate=Decimal("-15.00"),
        )
        
        # Handle exit
        _run(monitor._handle_exit(signal))
        
        # Verify fail was recorded
        fail_recorder.assert_called_once_with("OSS")
    
    def test_technical_stop_triggers_fail_callback(self, monitor):
        """Technical stop exit triggers record_symbol_fail callback."""
        fail_recorder = Mock()
        monitor.set_callbacks(record_symbol_fail=fail_recorder)
        
        monitor.add_position("pos-123", "AAPL", Decimal("150.00"), 100)
        
        signal = WarriorExitSignal(
            position_id="pos-123",
            symbol="AAPL",
            reason=WarriorExitReason.TECHNICAL_STOP,
            exit_price=Decimal("149.80"),
            shares_to_exit=100,
            pnl_estimate=Decimal("-20.00"),
        )
        
        _run(monitor._handle_exit(signal))
        
        fail_recorder.assert_called_once_with("AAPL")
    
    def test_partial_exit_does_not_trigger_fail(self, monitor):
        """Partial profit exit does NOT trigger fail callback."""
        fail_recorder = Mock()
        monitor.set_callbacks(record_symbol_fail=fail_recorder)
        
        monitor.add_position("pos-123", "AAPL", Decimal("150.00"), 100)
        
        signal = WarriorExitSignal(
            position_id="pos-123",
            symbol="AAPL",
            reason=WarriorExitReason.PARTIAL_EXIT,
            exit_price=Decimal("150.50"),
            shares_to_exit=50,
            pnl_estimate=Decimal("25.00"),
        )
        
        _run(monitor._handle_exit(signal))
        
        # Should NOT call fail recorder for profit-taking
        fail_recorder.assert_not_called()
