"""
Simulation Module

Provides mock trading environment for backtesting and simulation:
- SimulationClock: Time control with acceleration
- MockBroker: Simulated order execution
- MockMarketData: Historical data replay
"""

from nexus2.adapters.simulation.sim_clock import (
    SimulationClock, 
    get_simulation_clock, 
    reset_simulation_clock
)
from nexus2.adapters.simulation.mock_broker import MockBroker, MockBracketOrderResult
from nexus2.adapters.simulation.mock_market_data import (
    MockMarketData,
    get_mock_market_data,
    reset_mock_market_data,
    OHLCV
)

__all__ = [
    "SimulationClock",
    "get_simulation_clock",
    "reset_simulation_clock",
    "MockBroker",
    "MockBracketOrderResult",
    "MockMarketData",
    "get_mock_market_data",
    "reset_mock_market_data",
    "OHLCV",
]
