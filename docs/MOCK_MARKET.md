# Mock Market Simulation Environment

## Purpose

The Mock Market provides a simulated trading environment for testing the Nexus Automation Controller (NAC) when the real market is closed. Since the market is open only ~6.5 hours/day, this allows 24/7 development and testing.

**Key Design Goals:**
1. NAC code doesn't know it's a simulation (same interfaces)
2. Full trade lifecycle testing (scan → entry → stops → exit)
3. Historical data replay for backtesting

---

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                     AutomationEngine                          │
│  (Identical code for live and simulation)                     │
└───────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┴───────────────────┐
          ▼                                       ▼
┌─────────────────────────┐         ┌─────────────────────────┐
│     MockMarketData      │         │       MockBroker        │
│  ────────────────────   │         │  ───────────────────    │
│  • get_gainers()        │         │  • submit_order()       │
│  • get_quote()          │         │  • get_positions()      │
│  • get_daily_bars()     │         │  • check_stops()        │
│  • get_historical()     │         │  • calculate_pnl()      │
└─────────────────────────┘         └─────────────────────────┘
          ▲                                       ▲
          └───────────────────┬───────────────────┘
                              │
┌───────────────────────────────────────────────────────────────┐
│                     SimulationClock                           │
│  ─────────────────────────────────────────────────────────    │
│  • Controls "current time" for data replay                    │
│  • advance_day() moves to next bar                           │
│  • is_market_hours() returns True during sim                 │
└───────────────────────────────────────────────────────────────┘
```

---

## Components

### MockMarketData (`adapters/simulation/mock_market_data.py`)
Provides the same interface as `UnifiedMarketData.fmp`:
- `load_data(symbol, bars)` — Load historical OHLCV data
- `load_synthetic_data()` — Generate test data with configurable trend/volatility
- `get_current_price()` — Price at sim clock time
- `get_quote()` — Bid/ask/last
- `get_gainers()` — Top gainers for EP scanner
- `get_historical_prices()` — For HTF/Breakout scanners
- `advance_day()` — Step forward in time

### MockBroker (`adapters/simulation/mock_broker.py`)
Provides the same interface as `AlpacaBroker`:
- `submit_bracket_order()` — Place order with stop
- `get_positions()` — Current holdings
- `get_account()` — Cash, equity, P&L
- `set_price()` — Update market price for a symbol
- `_check_stop_orders()` — Trigger stops when price crosses

### SimulationClock (`adapters/simulation/sim_clock.py`)
Controls time for the simulation:
- `set_time()` — Jump to any date/time
- `advance()` — Move forward by days/hours
- `get_trading_day()` — Current sim date
- `is_market_hours()` — Always True in sim mode

---

## How To Use

### Enable Simulation Mode
```python
# Via API
PATCH /automation/scheduler/settings
{"sim_mode": true}

# Via Python
from nexus2.api.routes.automation_state import set_sim_broker
from nexus2.adapters.simulation.mock_broker import MockBroker
set_sim_broker(MockBroker(initial_cash=100_000))
```

### Load Historical Data
```python
# Via API
POST /automation/simulation/load_historical?symbol=NVDA&days=120

# Via Python
from nexus2.adapters.simulation import reset_mock_market_data
data = reset_mock_market_data()
data.load_data("NVDA", bar_dicts)  # From FMP or file
```

### Run a Simulation
```powershell
# Scanner-only test
python -m nexus2.tests.test_simulation_e2e

# Full trading loop test
python -m nexus2.tests.test_full_simulation

# API integration test (requires server)
python nexus2/tests/test_nac_simulation_integration.py
```

---

## Key Design Decisions

1. **Interface Compatibility:** Mock components implement identical interfaces to real counterparts. The engine code doesn't change.

2. **Clock-Based Replay:** Time is controlled, not real. Data is "current" relative to the SimulationClock position.

3. **Instant Fills:** MockBroker fills immediately at current price (no slippage model yet).

4. **Stop Order Simulation:** Stops trigger when `set_price()` crosses the stop level.

---

## Future Enhancements

- [ ] Slippage modeling
- [ ] Partial fills
- [ ] Latency simulation
- [ ] Multi-day strategy testing with overnight gaps
- [ ] Event-driven backtesting framework
