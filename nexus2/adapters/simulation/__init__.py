"""
Simulation Module

Provides mock trading environment for backtesting and simulation:
- SimulationClock: Time control with acceleration
- MockBroker: Simulated order execution
- MockMarketData: Historical data replay
- HistoricalBarLoader: Load intraday bars from JSON test cases
- SimContext: Isolated simulation environment for concurrent batch runs
"""

from nexus2.adapters.simulation.sim_clock import (
    SimulationClock, 
    get_simulation_clock, 
    reset_simulation_clock,
    set_simulation_clock_ctx,
)
from nexus2.adapters.simulation.mock_broker import MockBroker, MockBracketOrderResult
from nexus2.adapters.simulation.mock_market_data import (
    MockMarketData,
    get_mock_market_data,
    reset_mock_market_data,
    OHLCV
)
from nexus2.adapters.simulation.historical_bar_loader import (
    HistoricalBarLoader,
    IntradayBar,
    IntradayData,
    get_historical_bar_loader,
    reset_historical_bar_loader,
)
from nexus2.adapters.simulation.sim_context import SimContext, step_clock_ctx

__all__ = [
    "SimulationClock",
    "get_simulation_clock",
    "reset_simulation_clock",
    "set_simulation_clock_ctx",
    "MockBroker",
    "MockBracketOrderResult",
    "MockMarketData",
    "get_mock_market_data",
    "reset_mock_market_data",
    "OHLCV",
    "HistoricalBarLoader",
    "IntradayBar",
    "IntradayData",
    "get_historical_bar_loader",
    "reset_historical_bar_loader",
    "SimContext",
    "step_clock_ctx",
]

