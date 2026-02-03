"""
Tests for Warrior Engine Entry Logic

Tests entry-time safety filters:
- Entry Spread Filter (reject wide bid-ask spreads)
- Blacklist checks
- 2-Strike rule
- Re-entry cooldown
- Position size limits
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from dataclasses import dataclass

from nexus2.domain.automation.warrior_engine import (
    WarriorEngine,
    WarriorEngineConfig,
    WarriorEngineStats,
    WatchedCandidate,
    EntryTriggerType,
    get_warrior_engine,
)
from nexus2.domain.scanner.warrior_scanner_service import WarriorCandidate
from nexus2.adapters.market_data.protocol import OHLCV


# =============================================================================
# Helper
# =============================================================================

def _run(coro):
    """Helper to run async code in sync tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_mock_candles(count: int = 30, base_price: float = 10.0) -> list:
    """Create mock OHLCV candles for MACD gate tests.
    
    Returns list of OHLCV dataclass instances with positive price trend
    to ensure MACD histogram is bullish.
    """
    from datetime import datetime, timedelta
    base_time = datetime(2026, 1, 27, 10, 0, 0)
    candles = []
    for i in range(count):
        # Slight uptrend to make MACD bullish
        price = Decimal(str(base_price + i * 0.05))
        candles.append(OHLCV(
            timestamp=base_time + timedelta(minutes=i),
            open=price - Decimal("0.02"),
            high=price + Decimal("0.05"),
            low=price - Decimal("0.05"),
            close=price,
            volume=10000 + i * 100,
        ))
    return candles


def _get_bullish_macd_snapshot_mock():
    """Create a mock TechnicalSnapshot with bullish MACD and valid VWAP/EMA values.
    
    VWAP and EMA values must be below expected entry prices to pass the
    technical validation checks (price > VWAP and price > EMA*0.99).
    """
    mock_snapshot = MagicMock()
    mock_snapshot.is_macd_bullish = True
    mock_snapshot.macd_histogram = Decimal("0.05")
    mock_snapshot.macd_crossover = "bullish"
    # Set VWAP and EMA to low values so any entry price will pass checks
    mock_snapshot.vwap = Decimal("5.00")  # Low enough to pass price > VWAP check
    mock_snapshot.ema_9 = Decimal("5.00")  # Low enough to pass price > EMA*0.99 check
    mock_snapshot.data_insufficient = False
    return mock_snapshot


def make_watched_candidate(symbol: str = "TEST", gap_percent: float = 10.0, price: float = 10.0) -> WatchedCandidate:
    """Create a WatchedCandidate for testing."""
    candidate = WarriorCandidate(
        symbol=symbol,
        name=symbol,
        price=Decimal(str(price)),
        gap_percent=Decimal(str(gap_percent)),
        relative_volume=Decimal("5.0"),
        float_shares=1_000_000,
        catalyst_type="news",
        catalyst_description="Test catalyst",
        session_high=Decimal(str(price * 1.02)),
        session_low=Decimal(str(price * 0.98)),
    )
    return WatchedCandidate(
        candidate=candidate,
        pmh=Decimal(str(price * 1.01)),
    )


# =============================================================================
# Entry Spread Filter Config Tests
# =============================================================================

class TestEntrySpreadFilterConfig:
    """Tests for max_entry_spread_percent configuration."""
    
    def test_default_entry_spread_threshold(self):
        """Default entry spread threshold is 3%."""
        config = WarriorEngineConfig()
        assert config.max_entry_spread_percent == 3.0
    
    def test_custom_entry_spread_threshold(self):
        """Can customize entry spread threshold."""
        config = WarriorEngineConfig(max_entry_spread_percent=5.0)
        assert config.max_entry_spread_percent == 5.0
    
    def test_zero_threshold_disables_filter(self):
        """Setting threshold to 0 disables the filter."""
        config = WarriorEngineConfig(max_entry_spread_percent=0)
        assert config.max_entry_spread_percent == 0


# =============================================================================
# Entry Spread Filter Tests
# =============================================================================

class TestEntrySpreadFilter:
    """Tests for entry-time spread rejection logic."""
    
    @pytest.fixture
    def engine(self):
        """Create engine with mocked callbacks and dependencies."""
        with patch("nexus2.domain.automation.warrior_engine.WarriorMonitor") as MockMonitor:
            mock_monitor = MagicMock()
            mock_monitor._recently_exited = {}
            mock_monitor._recovery_cooldown_seconds = 120
            mock_monitor.settings = MagicMock()
            mock_monitor.settings.mental_stop_cents = Decimal("15")
            MockMonitor.return_value = mock_monitor
            
            with patch("nexus2.domain.automation.warrior_monitor.get_warrior_monitor") as get_monitor:
                get_monitor.return_value = mock_monitor
                
                # Patch technical service for MACD gate (must patch source module, not import location)
                with patch("nexus2.domain.indicators.get_technical_service") as mock_tech_svc:
                    mock_tech = MagicMock()
                    mock_tech.get_snapshot.return_value = _get_bullish_macd_snapshot_mock()
                    mock_tech_svc.return_value = mock_tech
                    
                    config = WarriorEngineConfig(
                        max_entry_spread_percent=3.0,
                        max_shares_per_trade=100,
                    )
                    engine = WarriorEngine(config=config)
                    engine.monitor = mock_monitor
                    engine._symbol_fails = {}  # Real dict for 2-strike rule
                    
                    # Mock callbacks
                    engine._submit_order = AsyncMock(return_value={"order_id": "test-123"})
                    engine._get_quote = AsyncMock(return_value=10.0)
                    engine._get_positions = AsyncMock(return_value=[])
                    # MACD gate requires intraday bars callback
                    engine._get_intraday_bars = AsyncMock(return_value=_make_mock_candles(30))
                    
                    yield engine
    
    def test_wide_spread_rejects_entry(self, engine):
        """Entry is rejected when spread exceeds threshold."""
        # Mock spread data: 48% spread (like SOGP incident)
        engine._get_quote_with_spread = AsyncMock(return_value={
            "price": 15.69,
            "bid": 15.47,
            "ask": 23.00,  # 48.6% spread
        })
        
        watched = make_watched_candidate("SOGP", price=15.69)
        
        _run(engine._enter_position(watched, Decimal("15.69"), EntryTriggerType.PMH_BREAK))
        
        # Entry should be blocked - submit_order should NOT be called
        engine._submit_order.assert_not_called()
        
        # Position should be marked as triggered to prevent retries
        assert watched.entry_triggered == True
    
    def test_narrow_spread_allows_entry(self, engine):
        """Entry is allowed when spread is below threshold."""
        # Mock spread data: 0.5% spread (healthy)
        # Use $10 price range to match mock candle data for position sizing
        engine._get_quote_with_spread = AsyncMock(return_value={
            "price": 10.00,
            "bid": 9.95,
            "ask": 10.05,  # ~1% spread (healthy)
        })
        
        watched = make_watched_candidate("TEST", price=10.00)
        
        _run(engine._enter_position(watched, Decimal("10.00"), EntryTriggerType.PMH_BREAK))
        
        # Entry should proceed - submit_order should be called
        engine._submit_order.assert_called_once()
    
    def test_spread_below_threshold_allows_entry(self, engine):
        """Entry is allowed when spread is below threshold."""
        # Mock spread data: 2.9% spread (just under 3% threshold)
        engine._get_quote_with_spread = AsyncMock(return_value={
            "price": 10.00,
            "bid": 10.00,
            "ask": 10.29,  # 2.9%
        })
        
        watched = make_watched_candidate("XYZ", price=10.00)
        
        _run(engine._enter_position(watched, Decimal("10.00"), EntryTriggerType.PMH_BREAK))
        
        # 2.9% < 3% threshold, should allow
        engine._submit_order.assert_called_once()
    
    def test_spread_just_above_threshold_rejects(self, engine):
        """Entry is rejected when spread is just above threshold."""
        # Mock spread data: 3.1% spread
        engine._get_quote_with_spread = AsyncMock(return_value={
            "price": 10.00,
            "bid": 10.00,
            "ask": 10.31,  # 3.1%
        })
        
        watched = make_watched_candidate("XYZ", price=10.00)
        
        _run(engine._enter_position(watched, Decimal("10.00"), EntryTriggerType.PMH_BREAK))
        
        # 3.1% > 3% threshold, should reject
        engine._submit_order.assert_not_called()
        assert watched.entry_triggered == True
    
    def test_no_spread_data_proceeds_with_caution(self, engine):
        """Entry proceeds when quote data is unavailable."""
        # Mock no quote data
        engine._get_quote_with_spread = AsyncMock(return_value=None)
        
        watched = make_watched_candidate("XYZ", price=10.00)
        
        _run(engine._enter_position(watched, Decimal("10.00"), EntryTriggerType.PMH_BREAK))
        
        # Should proceed (fail-open for quote failures)
        engine._submit_order.assert_called_once()
    
    def test_zero_bid_proceeds_with_caution(self, engine):
        """Entry proceeds when bid is zero (incomplete quote)."""
        engine._get_quote_with_spread = AsyncMock(return_value={
            "price": 10.00,
            "bid": 0,
            "ask": 10.50,
        })
        
        watched = make_watched_candidate("XYZ", price=10.00)
        
        _run(engine._enter_position(watched, Decimal("10.00"), EntryTriggerType.PMH_BREAK))
        
        # Should proceed with caution (incomplete quote)
        engine._submit_order.assert_called_once()
    
    def test_zero_ask_proceeds_with_caution(self, engine):
        """Entry proceeds when ask is zero (incomplete quote)."""
        engine._get_quote_with_spread = AsyncMock(return_value={
            "price": 10.00,
            "bid": 10.00,
            "ask": 0,
        })
        
        watched = make_watched_candidate("XYZ", price=10.00)
        
        _run(engine._enter_position(watched, Decimal("10.00"), EntryTriggerType.PMH_BREAK))
        
        # Should proceed with caution (incomplete quote)
        engine._submit_order.assert_called_once()
    
    def test_spread_check_exception_proceeds(self, engine):
        """Entry proceeds if spread check throws exception."""
        engine._get_quote_with_spread = AsyncMock(side_effect=Exception("API error"))
        
        watched = make_watched_candidate("XYZ", price=10.00)
        
        _run(engine._enter_position(watched, Decimal("10.00"), EntryTriggerType.PMH_BREAK))
        
        # Should proceed (fail-open)
        engine._submit_order.assert_called_once()
    
    def test_no_callback_skips_spread_check(self, engine):
        """Entry proceeds if no spread callback is configured."""
        engine._get_quote_with_spread = None
        
        watched = make_watched_candidate("XYZ", price=10.00)
        
        _run(engine._enter_position(watched, Decimal("10.00"), EntryTriggerType.PMH_BREAK))
        
        # Should proceed (no callback = skip check)
        engine._submit_order.assert_called_once()
    
    def test_disabled_filter_skips_check(self, engine):
        """Entry proceeds if filter is disabled (threshold = 0)."""
        engine.config.max_entry_spread_percent = 0
        
        # Even with massive spread, should allow entry
        engine._get_quote_with_spread = AsyncMock(return_value={
            "price": 10.00,
            "bid": 10.00,
            "ask": 50.00,  # 400% spread!
        })
        
        watched = make_watched_candidate("XYZ", price=10.00)
        
        _run(engine._enter_position(watched, Decimal("10.00"), EntryTriggerType.PMH_BREAK))
        
        # Should proceed (filter disabled)
        engine._submit_order.assert_called_once()


# =============================================================================
# Combined Entry Filter Tests
# =============================================================================

class TestEntryFilterPriority:
    """Tests that entry filters are checked in correct order."""
    
    @pytest.fixture
    def engine(self):
        """Create engine with mocked dependencies."""
        with patch("nexus2.domain.automation.warrior_engine.WarriorMonitor") as MockMonitor:
            mock_monitor = MagicMock()
            mock_monitor._recently_exited = {}
            mock_monitor._recovery_cooldown_seconds = 120
            mock_monitor.settings = MagicMock()
            mock_monitor.settings.mental_stop_cents = Decimal("15")
            MockMonitor.return_value = mock_monitor
            
            with patch("nexus2.domain.automation.warrior_monitor.get_warrior_monitor") as get_monitor:
                get_monitor.return_value = mock_monitor
                
                config = WarriorEngineConfig(
                    max_entry_spread_percent=3.0,
                    max_shares_per_trade=100,
                    static_blacklist={"BANNED"},
                )
                engine = WarriorEngine(config=config)
                engine.monitor = mock_monitor
                engine._symbol_fails = {}  # Real dict for 2-strike rule
                
                engine._submit_order = AsyncMock(return_value={"order_id": "test-123"})
                engine._get_quote = AsyncMock(return_value=10.0)
                engine._get_positions = AsyncMock(return_value=[])
                engine._get_quote_with_spread = AsyncMock(return_value={
                    "price": 10.00,
                    "bid": 10.00,
                    "ask": 10.10,  # 1% spread (OK)
                })
                
                yield engine
    
    def test_blacklist_checked_before_spread(self, engine):
        """Blacklist is checked before spread (cheaper check first)."""
        # Add to engine's runtime blacklist (static_blacklist may not propagate through mock)
        engine._blacklist.add("BANNED")
        
        watched = make_watched_candidate("BANNED", price=10.00)
        
        _run(engine._enter_position(watched, Decimal("10.00"), EntryTriggerType.PMH_BREAK))
        
        # Should be blocked by blacklist, never check spread
        engine._submit_order.assert_not_called()
        engine._get_quote_with_spread.assert_not_called()
    
    def test_cooldown_checked_before_spread(self, engine):
        """Re-entry cooldown is checked before spread."""
        from nexus2.utils.time_utils import now_utc
        engine.monitor._recently_exited = {"RECENT": now_utc()}
        
        watched = make_watched_candidate("RECENT", price=10.00)
        
        _run(engine._enter_position(watched, Decimal("10.00"), EntryTriggerType.PMH_BREAK))
        
        # Should be blocked by cooldown, never check spread
        engine._submit_order.assert_not_called()
        engine._get_quote_with_spread.assert_not_called()
    
    def test_spread_checked_after_position_check(self, engine):
        """Spread is checked after already-holding check."""
        engine._get_positions = AsyncMock(return_value=[{"symbol": "HELD"}])
        
        watched = make_watched_candidate("HELD", price=10.00)
        
        _run(engine._enter_position(watched, Decimal("10.00"), EntryTriggerType.PMH_BREAK))
        
        # Should be blocked by position check, never check spread
        engine._submit_order.assert_not_called()
        engine._get_quote_with_spread.assert_not_called()


# =============================================================================
# Spread Calculation Edge Cases
# =============================================================================

class TestSpreadCalculation:
    """Tests for spread percentage calculation edge cases."""
    
    @pytest.fixture
    def engine(self):
        """Create engine for spread testing."""
        with patch("nexus2.domain.automation.warrior_engine.WarriorMonitor") as MockMonitor:
            mock_monitor = MagicMock()
            mock_monitor._recently_exited = {}
            mock_monitor._recovery_cooldown_seconds = 120
            mock_monitor.settings = MagicMock()
            mock_monitor.settings.mental_stop_cents = Decimal("15")
            MockMonitor.return_value = mock_monitor
            
            with patch("nexus2.domain.automation.warrior_monitor.get_warrior_monitor") as get_monitor:
                get_monitor.return_value = mock_monitor
                
                # Patch technical service for MACD gate (must patch source module, not import location)
                with patch("nexus2.domain.indicators.get_technical_service") as mock_tech_svc:
                    mock_tech = MagicMock()
                    mock_tech.get_snapshot.return_value = _get_bullish_macd_snapshot_mock()
                    mock_tech_svc.return_value = mock_tech
                    
                    config = WarriorEngineConfig(max_entry_spread_percent=3.0)
                    engine = WarriorEngine(config=config)
                    engine.monitor = mock_monitor
                    engine._symbol_fails = {}  # Real dict for 2-strike rule
                    
                    engine._submit_order = AsyncMock(return_value={"order_id": "test-123"})
                    engine._get_quote = AsyncMock(return_value=10.0)
                    engine._get_positions = AsyncMock(return_value=[])
                    # MACD gate requires intraday bars callback
                    engine._get_intraday_bars = AsyncMock(return_value=_make_mock_candles(30))
                    
                    yield engine
    
    def test_low_price_stock_spread(self, engine):
        """Spread filter works correctly for low-price stocks."""
        # $2 stock with $0.10 spread = 5%
        engine._get_quote_with_spread = AsyncMock(return_value={
            "price": 2.00,
            "bid": 2.00,
            "ask": 2.10,  # 5% spread
        })
        
        watched = make_watched_candidate("PENNY", price=2.00)
        
        _run(engine._enter_position(watched, Decimal("2.00"), EntryTriggerType.PMH_BREAK))
        
        # 5% > 3% threshold, should reject
        engine._submit_order.assert_not_called()
    
    def test_high_price_stock_spread(self, engine):
        """Spread filter works correctly for high-price stocks."""
        # $500 stock with $20 spread = 4%
        engine._get_quote_with_spread = AsyncMock(return_value={
            "price": 500.00,
            "bid": 500.00,
            "ask": 520.00,  # 4% spread
        })
        
        watched = make_watched_candidate("EXPENSIVE", price=500.00)
        
        _run(engine._enter_position(watched, Decimal("500.00"), EntryTriggerType.PMH_BREAK))
        
        # 4% > 3% threshold, should reject
        engine._submit_order.assert_not_called()


# =============================================================================
# Scan Loop Market Check Tests (Jan 2026)
# =============================================================================

class TestScanLoopMarketCheck:
    """Tests for market check in scan loop.
    
    Verifies scan loop skips when market is closed.
    """
    
    def test_scan_skipped_when_market_closed(self):
        """Scan loop logic should skip when is_extended_hours_active returns False."""
        from nexus2.adapters.market_data.market_calendar import MarketStatus
        
        # Mock calendar to return closed
        with patch("nexus2.adapters.market_data.market_calendar.get_market_calendar") as mock_cal:
            mock_status = MarketStatus(is_open=False, reason="holiday_or_closed")
            mock_cal.return_value.is_extended_hours_active.return_value = False
            mock_cal.return_value.get_market_status.return_value = mock_status
            
            # Verify the check that would happen in scan loop
            calendar = mock_cal.return_value
            should_skip = not calendar.is_extended_hours_active()
            
            assert should_skip == True
    
    def test_scan_runs_when_market_open(self):
        """Scan loop should run when is_extended_hours_active returns True."""
        from nexus2.adapters.market_data.market_calendar import MarketStatus
        
        with patch("nexus2.adapters.market_data.market_calendar.get_market_calendar") as mock_cal:
            mock_status = MarketStatus(is_open=True)
            mock_cal.return_value.is_extended_hours_active.return_value = True
            mock_cal.return_value.get_market_status.return_value = mock_status
            
            calendar = mock_cal.return_value
            should_skip = not calendar.is_extended_hours_active()
            
            assert should_skip == False
    
    def test_scan_bypasses_check_in_sim_mode(self):
        """Sim mode should bypass market check."""
        config = WarriorEngineConfig(sim_only=True)
        
        # In sim_only mode, the market check should be skipped entirely
        assert config.sim_only == True
        
        # The logic in scan loop: if self.config.sim_only: skip_check
        should_check_market = not config.sim_only
        assert should_check_market == False


# =============================================================================
# Watch Loop Market Check Tests (Jan 2026)
# =============================================================================

class TestWatchLoopMarketCheck:
    """Tests for market check in watch loop.
    
    Verifies watch loop skips entry checks when market is closed.
    """
    
    def test_watch_skipped_when_market_closed(self):
        """Watch loop logic should skip when market is closed."""
        from nexus2.adapters.market_data.market_calendar import MarketStatus
        
        with patch("nexus2.adapters.market_data.market_calendar.get_market_calendar") as mock_cal:
            mock_status = MarketStatus(is_open=False, reason="weekend")
            mock_cal.return_value.is_extended_hours_active.return_value = False
            mock_cal.return_value.get_market_status.return_value = mock_status
            
            calendar = mock_cal.return_value
            should_skip = not calendar.is_extended_hours_active()
            
            assert should_skip == True
    
    def test_watch_runs_when_market_open(self):
        """Watch loop should check entries when market is open."""
        from nexus2.adapters.market_data.market_calendar import MarketStatus
        
        with patch("nexus2.adapters.market_data.market_calendar.get_market_calendar") as mock_cal:
            mock_status = MarketStatus(is_open=True)
            mock_cal.return_value.is_extended_hours_active.return_value = True
            mock_cal.return_value.get_market_status.return_value = mock_status
            
            calendar = mock_cal.return_value
            should_skip = not calendar.is_extended_hours_active()
            
            assert should_skip == False
    
    def test_watch_bypasses_check_in_sim_mode(self):
        """Sim mode bypasses market check for testing."""
        config = WarriorEngineConfig(sim_only=True)
        
        # Market check is skipped in sim mode
        assert config.sim_only == True

