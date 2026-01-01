"""
Tests for PositionMonitor partial exits (KK-style day-based).
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from nexus2.domain.automation.monitor import (
    PositionMonitor,
    ExitSignal,
    ExitReason,
)


def run_async(coro):
    """Helper to run async functions in sync tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestKKStylePartialExits:
    """Tests for KK-style day-based partial exits."""
    
    def make_position(
        self,
        days_ago: int = 0,
        entry_price: float = 100.0,
        current_stop: float = 95.0,
        shares: int = 100,
        partial_taken: bool = False,
    ) -> dict:
        """Create a mock position dict."""
        opened_at = datetime.now() - timedelta(days=days_ago)
        return {
            "id": "pos_123",
            "symbol": "TEST",
            "entry_price": entry_price,
            "initial_stop": current_stop,
            "current_stop": current_stop,
            "remaining_shares": shares,
            "opened_at": opened_at,
            "partial_taken": partial_taken,
        }
    
    @pytest.fixture
    def monitor(self):
        """Create a PositionMonitor with KK-style settings."""
        return PositionMonitor(
            kk_style_partials=True,
            partial_exit_days=3,
            partial_exit_fraction=0.5,
        )
    
    def test_partial_triggers_day_3_in_profit(self, monitor):
        """Day 3 + in profit should trigger partial exit."""
        position = self.make_position(days_ago=3, entry_price=100.0)
        current_price = Decimal("110.0")  # In profit
        
        signal = run_async(monitor._check_partial_exit(
            position=position,
            current_price=current_price,
            entry_price=Decimal("100.0"),
            shares=100,
            r_multiple=2.0,
        ))
        
        assert signal is not None
        assert signal.reason == ExitReason.PARTIAL_EXIT
        assert signal.shares_to_exit == 50  # 50% of 100
        assert signal.exit_type == "partial"
        assert "Day 3" in signal.trigger_reason
        assert signal.days_held == 3
    
    def test_partial_skips_day_2(self, monitor):
        """Day 2 (even if in profit) should NOT trigger partial."""
        position = self.make_position(days_ago=2, entry_price=100.0)
        current_price = Decimal("115.0")  # Nice profit
        
        signal = run_async(monitor._check_partial_exit(
            position=position,
            current_price=current_price,
            entry_price=Decimal("100.0"),
            shares=100,
            r_multiple=3.0,
        ))
        
        assert signal is None  # Too early
    
    def test_partial_skips_not_in_profit(self, monitor):
        """Day 5 but not in profit should NOT trigger partial."""
        position = self.make_position(days_ago=5, entry_price=100.0)
        current_price = Decimal("98.0")  # Loss
        
        signal = run_async(monitor._check_partial_exit(
            position=position,
            current_price=current_price,
            entry_price=Decimal("100.0"),
            shares=100,
            r_multiple=-0.4,
        ))
        
        assert signal is None  # Not in profit
    
    def test_partial_prevents_repeat(self, monitor):
        """partial_taken=True should prevent second partial."""
        position = self.make_position(days_ago=4, entry_price=100.0, partial_taken=True)
        current_price = Decimal("120.0")  # Nice profit
        
        signal = run_async(monitor._check_partial_exit(
            position=position,
            current_price=current_price,
            entry_price=Decimal("100.0"),
            shares=50,  # Already did partial
            r_multiple=4.0,
        ))
        
        assert signal is None  # Already took partial
    
    def test_breakeven_stop_called_after_partial(self, monitor):
        """Stop should move to breakeven after partial exit."""
        # Create async mock that tracks calls
        update_stop_calls = []
        async def mock_update_stop(pos_id, price):
            update_stop_calls.append((pos_id, price))
        
        monitor._update_stop = mock_update_stop
        
        position = self.make_position(days_ago=4, entry_price=100.0)
        current_price = Decimal("112.0")
        
        signal = run_async(monitor._check_partial_exit(
            position=position,
            current_price=current_price,
            entry_price=Decimal("100.0"),
            shares=100,
            r_multiple=2.4,
        ))
        
        assert signal is not None
        # Check that update_stop was called with entry price (breakeven)
        assert len(update_stop_calls) == 1
        assert update_stop_calls[0] == ("pos_123", Decimal("100.0"))
    
    def test_partial_exit_fraction_respected(self, monitor):
        """Should sell the configured fraction (50%)."""
        position = self.make_position(days_ago=5, entry_price=50.0, shares=200)
        current_price = Decimal("60.0")
        
        signal = run_async(monitor._check_partial_exit(
            position=position,
            current_price=current_price,
            entry_price=Decimal("50.0"),
            shares=200,
            r_multiple=2.0,
        ))
        
        assert signal is not None
        assert signal.shares_to_exit == 100  # 50% of 200
    
    def test_analytics_fields_populated(self, monitor):
        """Analytics fields should be populated in ExitSignal."""
        position = self.make_position(days_ago=4, entry_price=100.0)
        current_price = Decimal("110.0")
        
        signal = run_async(monitor._check_partial_exit(
            position=position,
            current_price=current_price,
            entry_price=Decimal("100.0"),
            shares=100,
            r_multiple=2.0,
        ))
        
        assert signal is not None
        assert signal.days_held == 4
        assert signal.exit_type == "partial"
        assert signal.trigger_reason == "Day 4 + in profit"
        assert signal.r_multiple == 2.0


class TestLegacyRBasedPartials:
    """Tests for legacy R-based partial exits (non-KK style)."""
    
    @pytest.fixture
    def monitor(self):
        """Create a PositionMonitor with legacy R-based settings."""
        return PositionMonitor(
            kk_style_partials=False,
            partial_exit_threshold_r=2.0,
            partial_exit_percent=0.25,
        )
    
    def test_legacy_partial_at_2r(self, monitor):
        """Legacy mode should trigger partial at 2R."""
        position = {
            "id": "pos_456",
            "symbol": "LEGACY",
            "partial_taken": False,
        }
        
        signal = run_async(monitor._check_partial_exit(
            position=position,
            current_price=Decimal("120.0"),
            entry_price=Decimal("100.0"),
            shares=100,
            r_multiple=2.5,
        ))
        
        assert signal is not None
        assert signal.shares_to_exit == 25  # 25% of 100
