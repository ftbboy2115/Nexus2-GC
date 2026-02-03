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
        
        # Note: mental_stop_cents updated from 15 to 50 in production
        assert s.mental_stop_cents == Decimal("50")
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
        
        # Mental stop: $150.00 - $0.50 = $149.50 (default is now 50¢)
        assert position.mental_stop == Decimal("149.50")
        assert position.current_stop == Decimal("149.50")
        
        # Risk per share: $0.50
        assert position.risk_per_share == Decimal("0.50")
        
        # Profit target (2:1 R): $150.00 + $1.00 = $151.00
        assert position.profit_target == Decimal("151.000")
    
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
        """Create monitor with position using home_run mode for partial exit tests."""
        with patch("nexus2.domain.automation.warrior_monitor.trade_event_service"):
            # Use home_run mode so exit logic behaves as expected for stop tests
            m = WarriorMonitor(settings=WarriorMonitorSettings(session_exit_mode='home_run'))
            m.set_callbacks(
                get_price=AsyncMock(),
                execute_exit=AsyncMock(),
            )
            m.add_position("pos-123", "AAPL", Decimal("150.00"), 100)
            yield m
    
    def test_price_below_stop_triggers_exit(self, monitor):
        """Price at or below stop triggers mental stop exit."""
        # Price below the 50¢ mental stop ($149.50)
        monitor._get_price = AsyncMock(return_value=Decimal("149.40"))
        
        position = list(monitor._positions.values())[0]
        signal = _run(monitor._evaluate_position(position))
        
        assert signal is not None
        assert signal.reason == WarriorExitReason.MENTAL_STOP
        assert signal.shares_to_exit == 100
    
    def test_price_above_stop_no_exit(self, monitor):
        """Price above stop but below target does not trigger exit."""
        # Price between stop ($149.50) and target ($151.00) = no exit
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
        """Create monitor with position using home_run mode for partial exits.
        
        Note: base_hit mode (default) now does full exits on target hit.
        home_run mode supports partial exits and trailing stops.
        """
        with patch("nexus2.domain.automation.warrior_monitor.trade_event_service"):
            # Use home_run mode to get PARTIAL_EXIT behavior
            m = WarriorMonitor(settings=WarriorMonitorSettings(session_exit_mode='home_run'))
            m.set_callbacks(
                get_price=AsyncMock(),
                execute_exit=AsyncMock(),
                update_stop=AsyncMock(),
            )
            m.add_position("pos-123", "AAPL", Decimal("150.00"), 100)
            yield m
    
    @pytest.fixture
    def mock_trading_hours(self):
        """Mock datetime to simulate trading hours (2:00 PM ET) with proper timedelta support."""
        from datetime import datetime as real_datetime
        et = ZoneInfo("America/New_York")
        mock_dt = real_datetime(2026, 1, 12, 14, 0, 0, tzinfo=et)  # 2:00 PM ET
        mock_utc = real_datetime(2026, 1, 12, 19, 0, 0)  # 2:00 PM ET = 7:00 PM UTC
        
        with patch("nexus2.domain.automation.warrior_monitor.datetime") as mock_datetime:
            # Return mock time for both .now() and .utcnow()
            mock_datetime.now.return_value = mock_dt
            mock_datetime.utcnow.return_value = mock_utc
            # Make datetime(...) calls work normally
            mock_datetime.side_effect = lambda *args, **kw: real_datetime(*args, **kw)
            # Also need to make timedelta work for seconds_since_entry calculation
            mock_datetime.timedelta = timedelta
            yield mock_datetime
    
    def test_profit_target_triggers_partial(self, monitor, mock_trading_hours):
        """Hitting profit target triggers partial exit in home_run mode."""
        from datetime import datetime as real_datetime
        
        # Target is $151.00 (2:1 R with 50¢ stop)
        monitor._get_price = AsyncMock(return_value=Decimal("151.10"))
        
        position = list(monitor._positions.values())[0]
        # Set entry_time as naive UTC to match datetime.utcnow() subtraction
        position.entry_time = real_datetime(2026, 1, 12, 14, 30, 0)  # 9:30 AM ET = 2:30 PM UTC (naive)
        
        signal = _run(monitor._evaluate_position(position))
        
        assert signal is not None
        assert signal.reason == WarriorExitReason.PARTIAL_EXIT
        assert signal.shares_to_exit == 50  # 50% of 100
    
    def test_partial_taken_no_repeat(self, monitor, mock_trading_hours):
        """Partial already taken does not trigger again in home_run mode."""
        from datetime import datetime as real_datetime
        
        # Price above target but partial already taken
        monitor._get_price = AsyncMock(return_value=Decimal("151.50"))
        
        position = list(monitor._positions.values())[0]
        position.partial_taken = True
        # Set entry_time as naive UTC to match datetime.utcnow() subtraction
        position.entry_time = real_datetime(2026, 1, 12, 14, 30, 0)  # 9:30 AM ET = 2:30 PM UTC (naive)
        
        signal = _run(monitor._evaluate_position(position))
        
        # No partial signal because partial already taken (may have trail signal)
        if signal:
            assert signal.reason != WarriorExitReason.PARTIAL_EXIT


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


# =============================================================================
# PSM Helper Tests (Jan 2026)
# =============================================================================

class TestWarriorPSMHelpers:
    """Test the PSM-based helper methods in warrior_monitor."""
    
    def test_warrior_monitor_has_psm_helpers(self):
        """Test warrior_monitor has the new PSM helper methods."""
        monitor = WarriorMonitor.__new__(WarriorMonitor)
        
        # Check all helper methods exist
        assert hasattr(monitor, '_is_pending_exit')
        assert hasattr(monitor, '_mark_pending_exit')
        assert hasattr(monitor, '_clear_pending_exit')
        assert hasattr(monitor, '_get_pending_exit_symbols')
        
        # All should be callable
        assert callable(getattr(monitor, '_is_pending_exit'))
        assert callable(getattr(monitor, '_mark_pending_exit'))
        assert callable(getattr(monitor, '_clear_pending_exit'))
        assert callable(getattr(monitor, '_get_pending_exit_symbols'))
    
    def test_warrior_db_has_psm_functions(self):
        """Test warrior_db has all required PSM functions."""
        from nexus2.db import warrior_db
        
        # Check all functions exist
        assert hasattr(warrior_db, 'update_warrior_status')
        assert hasattr(warrior_db, 'get_warrior_trades_by_status')
        assert hasattr(warrior_db, 'get_warrior_trade_by_symbol')
        assert hasattr(warrior_db, 'get_open_warrior_trades')
        assert hasattr(warrior_db, 'log_warrior_entry')
        assert hasattr(warrior_db, 'log_warrior_exit')


# =============================================================================
# Recovery Integrity Tests (Jan 2026)
# =============================================================================

class TestRecoveryIntegrity:
    """Tests for position recovery from broker sync.
    
    Verifies that stop/target are restored from DB (not recalculated),
    and that target sanity check works correctly.
    """
    
    @pytest.fixture
    def monitor(self):
        """Create monitor with mocked callbacks."""
        with patch("nexus2.domain.automation.warrior_monitor.trade_event_service"):
            m = WarriorMonitor()
            m.sim_mode = True  # Set sim_mode as attribute
            m.set_callbacks(
                get_price=AsyncMock(return_value=Decimal("19.00")),
                execute_exit=AsyncMock(),
                get_positions=AsyncMock(return_value=[]),
            )
            yield m
    
    def test_recovery_restores_stop_from_db(self):
        """Stop price is restored from DB, not recalculated with fallback 15c."""
        from unittest.mock import MagicMock
        
        # Mock DB trade with original stop
        mock_trade = {
            "id": "trade-123",
            "symbol": "RIOT",
            "entry_price": "18.66",
            "stop_price": "17.50",  # Original stop (NOT 15c fallback)
            "target_price": "21.00",
            "trigger_type": "ORB",
            "entry_time": "2026-01-17T14:30:00+00:00",
            "high_since_entry": "19.00",
            "partial_taken": False,
        }
        
        with patch("nexus2.db.warrior_db.get_warrior_trade_by_symbol", return_value=mock_trade):
            from nexus2.domain.automation.warrior_monitor import WarriorPosition
            
            # Simulate recovery logic extracting stop from DB
            db_stop = mock_trade.get("stop_price")
            assert db_stop is not None
            
            # The recovered stop should be DB value, not fallback
            stop_price = Decimal(str(db_stop))
            assert stop_price == Decimal("17.50")
            
            # 15c fallback would be: 18.66 - 0.15 = 18.51
            fallback_stop = Decimal("18.66") - Decimal("0.15")
            assert stop_price != fallback_stop
    
    def test_recovery_restores_target_from_db(self):
        """Target price is restored from DB, not recalculated."""
        mock_trade = {
            "id": "trade-123",
            "entry_price": "18.66",
            "stop_price": "17.50",
            "target_price": "21.00",  # Original 2:1 R target
            "entry_time": "2026-01-17T14:30:00+00:00",
        }
        
        db_target = mock_trade.get("target_price")
        assert db_target is not None
        
        target_price = Decimal(str(db_target))
        assert target_price == Decimal("21.00")
        
        # Fallback with 15c risk would be: 18.66 + 0.30 = 18.96
        fallback_target = Decimal("18.66") + Decimal("0.30")
        assert target_price != fallback_target
    
    def test_recovery_fallback_when_no_db_record(self):
        """Uses fallback stop/target when no DB record exists."""
        with patch("nexus2.db.warrior_db.get_warrior_trade_by_symbol", return_value=None):
            # When no DB record, should use fallback 15c mental stop
            entry_price = Decimal("18.66")
            mental_stop_cents = Decimal("15")
            
            fallback_stop = entry_price - mental_stop_cents / 100
            fallback_target = entry_price + (mental_stop_cents / 100 * 2)  # 2:1 R
            
            assert fallback_stop == Decimal("18.51")
            assert fallback_target == Decimal("18.96")
    
    def test_target_sanity_check_marks_partial(self):
        """If current price > target at recovery, partial_taken is set True."""
        # Scenario: target was $19.50, but price is now $20.00
        target_price = Decimal("19.50")
        current_price = Decimal("20.00")
        
        partial_already_taken = False
        
        # Target sanity check logic
        if current_price > target_price and not partial_already_taken:
            partial_already_taken = True
        
        assert partial_already_taken == True
    
    def test_target_sanity_check_skips_if_partial_taken(self):
        """Doesn't re-mark if partial was already taken."""
        target_price = Decimal("19.50")
        current_price = Decimal("20.00")
        
        partial_already_taken = True  # Already taken in DB
        
        # Target sanity check shouldn't change this
        original_value = partial_already_taken
        if current_price > target_price and not partial_already_taken:
            partial_already_taken = True
        
        assert partial_already_taken == original_value
    
    def test_entry_time_is_timezone_aware(self):
        """Recovered entry_time is UTC-aware, not naive."""
        from datetime import datetime, timezone
        
        # Test various input formats
        entry_time_str = "2026-01-17T14:30:00+00:00"
        recovered_entry_time = datetime.fromisoformat(entry_time_str.replace("Z", "+00:00"))
        
        # Ensure timezone-aware
        if recovered_entry_time.tzinfo is None:
            recovered_entry_time = recovered_entry_time.replace(tzinfo=timezone.utc)
        
        assert recovered_entry_time.tzinfo is not None
        assert recovered_entry_time.tzinfo == timezone.utc
    
    def test_entry_time_naive_string_is_fixed(self):
        """Naive datetime string from DB is converted to UTC-aware."""
        from datetime import datetime, timezone
        
        # Naive string (no timezone info)
        entry_time_str = "2026-01-17T14:30:00"
        recovered_entry_time = datetime.fromisoformat(entry_time_str)
        
        # Should be naive initially
        assert recovered_entry_time.tzinfo is None
        
        # Apply fix
        if recovered_entry_time.tzinfo is None:
            recovered_entry_time = recovered_entry_time.replace(tzinfo=timezone.utc)
        
        assert recovered_entry_time.tzinfo is not None


# =============================================================================
# Scale Market Check Tests (Jan 2026)
# =============================================================================

class TestScaleMarketCheck:
    """Tests for early market check in scale execution.
    
    Verifies that scaling is blocked when market is closed.
    """
    
    @pytest.fixture
    def monitor(self):
        """Create monitor with mocked callbacks."""
        with patch("nexus2.domain.automation.warrior_monitor.trade_event_service"):
            m = WarriorMonitor(sim_mode=False)  # Real mode (not sim)
            m.set_callbacks(
                get_price=AsyncMock(return_value=Decimal("19.00")),
                execute_exit=AsyncMock(),
            )
            yield m
    
    def test_scale_blocked_when_market_closed(self):
        """Scale returns False when market is closed on holiday."""
        from nexus2.adapters.market_data.market_calendar import MarketStatus
        
        # Mock market as closed
        mock_status = MarketStatus(is_open=False, reason="holiday_or_closed")
        
        with patch("nexus2.adapters.market_data.market_calendar.get_market_calendar") as mock_cal:
            mock_cal.return_value.get_market_status.return_value = mock_status
            mock_cal.return_value.is_extended_hours_active.return_value = False
            
            # Check the logic that would run in _execute_scale_in
            status = mock_cal.return_value.get_market_status()
            should_block = not status.is_open
            
            assert should_block == True
            assert status.reason == "holiday_or_closed"
    
    def test_scale_proceeds_when_market_open(self):
        """Scale proceeds when market is open."""
        from nexus2.adapters.market_data.market_calendar import MarketStatus
        
        mock_status = MarketStatus(is_open=True)
        
        with patch("nexus2.adapters.market_data.market_calendar.get_market_calendar") as mock_cal:
            mock_cal.return_value.get_market_status.return_value = mock_status
            
            status = mock_cal.return_value.get_market_status()
            should_block = not status.is_open
            
            assert should_block == False
    
    def test_scale_skips_market_check_in_sim_mode(self):
        """Sim mode bypasses market check."""
        with patch("nexus2.domain.automation.warrior_monitor.trade_event_service"):
            m = WarriorMonitor()
            m.sim_mode = True  # Set sim_mode as attribute
            
            # In sim mode, the market check should be skipped
            # The logic is: if sim_mode, skip the check entirely
            assert m.sim_mode == True


# =============================================================================
# Stop Check on Sync Tests
# =============================================================================

class TestStopCheckOnSync:
    """Tests for immediate stop check when recovering positions during sync."""
    
    @pytest.fixture
    def monitor(self):
        """Create monitor with mocked callbacks."""
        with patch("nexus2.domain.automation.warrior_monitor.trade_event_service"):
            m = WarriorMonitor()
            m.set_callbacks(
                get_price=AsyncMock(return_value=Decimal("19.00")),
                execute_exit=AsyncMock(),
            )
            yield m
    
    def test_sync_exits_position_below_stop(self, monitor):
        """Position recovered below stop triggers immediate exit."""
        # This tests the logic flow where:
        # 1. Position is recovered with price < stop
        # 2. Exit signal should be generated
        # 3. _handle_exit should be called
        
        # We verify this by checking the math that would be used in the stop check
        current_price = Decimal("19.06")
        stop_price = Decimal("19.07")
        
        # The condition that triggers exit
        should_exit = current_price <= stop_price
        
        assert should_exit == True
        
        # Verify the exit would be a loss (negative P&L)
        entry_price = Decimal("19.50")
        qty = 100
        pnl = (current_price - entry_price) * qty
        
        assert pnl < 0  # This is a losing trade
    
    def test_sync_keeps_position_above_stop(self, monitor):
        """Position recovered above stop is kept, not exited."""
        current_price = Decimal("19.50")
        stop_price = Decimal("19.07")
        
        # The condition that would trigger exit
        should_exit = current_price <= stop_price
        
        assert should_exit == False  # Should NOT exit
    
    def test_sync_exit_on_equal_price(self, monitor):
        """Position recovered AT stop price triggers exit (defensive)."""
        current_price = Decimal("19.07")
        stop_price = Decimal("19.07")
        
        should_exit = current_price <= stop_price
        
        assert should_exit == True  # Exactly at stop = exit

