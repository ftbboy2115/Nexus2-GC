"""
Unit Tests for Simulation Module

Tests for mock trading environment:
- SimulationClock: Time control and market hours
- MockBroker: Order execution and position tracking
- MockMarketData: Historical data replay
"""

import pytest
import os
from datetime import datetime, timedelta

# Set test mode
os.environ["TESTING"] = "true"

from uuid import uuid4


class TestSimulationClock:
    """Tests for SimulationClock."""
    
    def test_default_initialization(self):
        """Clock initializes with current time."""
        from nexus2.adapters.simulation import SimulationClock
        
        clock = SimulationClock()
        assert clock.current_time is not None
        assert clock.speed == 1.0
    
    def test_set_time(self):
        """Can set specific time."""
        from nexus2.adapters.simulation import SimulationClock
        import pytz
        
        ET = pytz.timezone("US/Eastern")
        target = ET.localize(datetime(2025, 6, 15, 10, 30))
        
        clock = SimulationClock()
        clock.set_time(target)
        
        assert clock.current_time == target
    
    def test_advance_minutes(self):
        """Advance by minutes works."""
        from nexus2.adapters.simulation import SimulationClock
        import pytz
        
        ET = pytz.timezone("US/Eastern")
        start = ET.localize(datetime(2025, 6, 15, 10, 0))
        
        clock = SimulationClock(start_time=start)
        clock.advance(minutes=30)
        
        assert clock.current_time.hour == 10
        assert clock.current_time.minute == 30
    
    def test_advance_days(self):
        """Advance by days works."""
        from nexus2.adapters.simulation import SimulationClock
        import pytz
        
        ET = pytz.timezone("US/Eastern")
        start = ET.localize(datetime(2025, 6, 15, 10, 0))
        
        clock = SimulationClock(start_time=start)
        clock.advance(days=5)
        
        assert clock.current_time.day == 20
    
    def test_is_market_hours_weekday_open(self):
        """Market hours detected on weekday."""
        from nexus2.adapters.simulation import SimulationClock
        import pytz
        
        ET = pytz.timezone("US/Eastern")
        # Wednesday at 11 AM
        clock = SimulationClock(start_time=ET.localize(datetime(2025, 6, 18, 11, 0)))
        
        assert clock.is_market_hours() is True
    
    def test_is_market_hours_weekend(self):
        """Market closed on weekend."""
        from nexus2.adapters.simulation import SimulationClock
        import pytz
        
        ET = pytz.timezone("US/Eastern")
        # Saturday at 11 AM
        clock = SimulationClock(start_time=ET.localize(datetime(2025, 6, 21, 11, 0)))
        
        assert clock.is_market_hours() is False
    
    def test_is_eod_window(self):
        """EOD window detected correctly."""
        from nexus2.adapters.simulation import SimulationClock
        import pytz
        
        ET = pytz.timezone("US/Eastern")
        # 3:50 PM on weekday
        clock = SimulationClock(start_time=ET.localize(datetime(2025, 6, 18, 15, 50)))
        
        assert clock.is_eod_window() is True
    
    def test_get_trading_day(self):
        """Trading day formatted correctly."""
        from nexus2.adapters.simulation import SimulationClock
        import pytz
        
        ET = pytz.timezone("US/Eastern")
        clock = SimulationClock(start_time=ET.localize(datetime(2025, 6, 18, 10, 0)))
        
        assert clock.get_trading_day() == "2025-06-18"


class TestMockBroker:
    """Tests for MockBroker."""
    
    def test_initial_cash(self):
        """Broker starts with correct cash."""
        from nexus2.adapters.simulation import MockBroker
        
        broker = MockBroker(initial_cash=50_000)
        account = broker.get_account()
        
        assert account["cash"] == 50_000
    
    def test_set_price(self):
        """Can set symbol price."""
        from nexus2.adapters.simulation import MockBroker
        
        broker = MockBroker()
        broker.set_price("AAPL", 150.0)
        
        assert broker.get_price("AAPL") == 150.0
    
    def test_submit_bracket_order_fills(self):
        """Bracket order fills at current price."""
        from nexus2.adapters.simulation import MockBroker
        
        broker = MockBroker(initial_cash=50_000)
        broker.set_price("NVDA", 500.0)
        
        result = broker.submit_bracket_order(
            client_order_id=uuid4(),
            symbol="NVDA",
            quantity=10,
            stop_loss_price=480.0,
        )
        
        assert result.status.value == "filled"
        assert float(result.avg_fill_price) == 500.0
        assert result.filled_quantity == 10
    
    def test_position_created(self):
        """Position created after fill."""
        from nexus2.adapters.simulation import MockBroker
        
        broker = MockBroker(initial_cash=50_000)
        broker.set_price("NVDA", 500.0)
        broker.submit_bracket_order(uuid4(), "NVDA", 10, 480.0)
        
        positions = broker.get_positions()
        assert len(positions) == 1
        assert positions[0]["symbol"] == "NVDA"
        assert positions[0]["qty"] == 10
    
    def test_cash_reduced_after_buy(self):
        """Cash decreases after buy."""
        from nexus2.adapters.simulation import MockBroker
        
        broker = MockBroker(initial_cash=50_000)
        broker.set_price("AAPL", 150.0)
        broker.submit_bracket_order(uuid4(), "AAPL", 10, 145.0)  # $1500
        
        account = broker.get_account()
        assert account["cash"] == 50_000 - 1500
    
    def test_stop_triggers(self):
        """Stop order triggers when price falls."""
        from nexus2.adapters.simulation import MockBroker
        
        broker = MockBroker(initial_cash=50_000)
        broker.set_price("AAPL", 150.0)
        broker.submit_bracket_order(uuid4(), "AAPL", 10, 145.0)
        
        # Price drops below stop
        broker.set_price("AAPL", 140.0)
        
        # Position should be gone
        positions = broker.get_positions()
        assert len(positions) == 0
    
    def test_insufficient_buying_power(self):
        """Order rejected if insufficient funds."""
        from nexus2.adapters.simulation import MockBroker
        
        broker = MockBroker(initial_cash=1_000)
        broker.set_price("TSLA", 200.0)
        
        result = broker.submit_bracket_order(uuid4(), "TSLA", 100, 190.0)  # $20,000
        
        assert result.status.value == "rejected"


class TestMockMarketData:
    """Tests for MockMarketData."""
    
    def test_load_synthetic_data(self):
        """Synthetic data generation works."""
        from nexus2.adapters.simulation import MockMarketData
        
        data = MockMarketData()
        count = data.load_synthetic_data("TEST", start_price=100, days=30)
        
        assert count > 0
        assert "TEST" in data.get_symbols()
    
    def test_get_current_price(self):
        """Current price available after load."""
        from nexus2.adapters.simulation import MockMarketData
        
        data = MockMarketData()
        data.load_synthetic_data("TEST", start_price=100, days=30)
        
        price = data.get_current_price("TEST")
        assert price is not None
        assert price > 0
    
    def test_get_daily_bars(self):
        """Daily bars returned correctly."""
        from nexus2.adapters.simulation import MockMarketData
        
        data = MockMarketData()
        data.load_synthetic_data("TEST", start_price=100, days=60)
        
        bars = data.get_daily_bars("TEST", days=10)
        assert len(bars) <= 10
    
    def test_load_data_from_dict(self):
        """Can load data from dict format."""
        from nexus2.adapters.simulation import MockMarketData
        
        bars = [
            {"date": "2025-01-01", "open": 100, "high": 105, "low": 99, "close": 103, "volume": 1000000},
            {"date": "2025-01-02", "open": 103, "high": 108, "low": 102, "close": 107, "volume": 1200000},
        ]
        
        data = MockMarketData()
        count = data.load_data("TEST", bars)
        
        assert count == 2
        assert data.get_current_price("TEST") == 107.0


class TestSimulationIntegration:
    """Integration tests for simulation components."""
    
    def test_full_trade_cycle(self):
        """Full trade from entry to stop-out."""
        from nexus2.adapters.simulation import SimulationClock, MockBroker, MockMarketData
        import pytz
        
        ET = pytz.timezone("US/Eastern")
        
        # Setup
        clock = SimulationClock(start_time=ET.localize(datetime(2025, 6, 18, 9, 30)))
        broker = MockBroker(initial_cash=10_000)
        data = MockMarketData()
        data.set_clock(clock)
        data.load_synthetic_data("NVDA", start_price=500, days=60)
        
        # Entry
        broker.set_price("NVDA", 500.0)
        result = broker.submit_bracket_order(uuid4(), "NVDA", 10, 490.0)
        
        assert result.status.value == "filled"
        assert len(broker.get_positions()) == 1
        
        # Price drops to stop
        broker.set_price("NVDA", 485.0)
        
        # Position closed
        assert len(broker.get_positions()) == 0
        
        # Check P&L
        account = broker.get_account()
        assert account["realized_pnl"] < 0  # Lost money
    
    def test_profitable_trade(self):
        """Trade with profit before stop."""
        from nexus2.adapters.simulation import MockBroker
        
        broker = MockBroker(initial_cash=10_000)
        broker.set_price("AAPL", 150.0)
        broker.submit_bracket_order(uuid4(), "AAPL", 10, 145.0)
        
        # Price goes up
        broker.set_price("AAPL", 160.0)
        
        # Sell manually
        broker.sell_position("AAPL")
        
        account = broker.get_account()
        assert account["realized_pnl"] == 100.0  # $10 x 10 shares


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
