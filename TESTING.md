# Nexus 2 Testing Guide

## Simulation Tests Overview

The simulation test suite validates the mock trading environment without using real money.

### Test Files Comparison

| Test File | Purpose | Run Command |
|-----------|---------|-------------|
| `test_simulation_e2e.py` | Scanner → Signals (no execution) | `python -m nexus2.tests.test_simulation_e2e` |
| `test_full_simulation.py` | Full loop: Scanner → Engine → MockBroker → Positions → P&L | `python -m nexus2.tests.test_full_simulation` |
| `test_nac_simulation_integration.py` | API-based test via HTTP requests | `python nexus2/tests/test_nac_simulation_integration.py` |

---

## Test Details

### 1. `test_simulation_e2e.py`
**Focus:** Mock market data and scanner validation

**Steps:**
1. Reset simulation clock to Sept 15, 2025
2. Load real FMP data (NVDA, AMD, SMCI)
3. Find a date with 5%+ gainers
4. Test `get_gainers()` and `get_actives()`
5. Run EP scanner with MockMarketData
6. Verify signals generated

**Does NOT:** Execute trades or manage positions

---

### 2. `test_full_simulation.py`
**Focus:** Complete trading loop with MockBroker

**Steps:**
1. Reset simulation environment
2. Load historical data from FMP
3. Find a day with big gainers
4. Create AutomationEngine with MockBroker callbacks
5. Run scanner cycle
6. **Submit orders to MockBroker**
7. **Check positions**
8. **Advance time and check stops**
9. Report P&L

**Key difference:** Uses `AutomationEngine` with real callbacks, tests full trade lifecycle.

---

### 3. `test_nac_simulation_integration.py`
**Focus:** API endpoint integration testing

**Steps:**
1. Reset simulation via `/automation/simulation/reset`
2. Load historical data via `/automation/simulation/load_historical`
3. Enable `sim_mode` and `auto_execute` via `/automation/scheduler/settings`
4. Check broker state via `/automation/simulation/broker`
5. Advance time via `/automation/simulation/advance`
6. Verify P&L changes

**Key difference:** Uses HTTP API endpoints, tests the server integration.

---

## Mock Infrastructure

| Component | File | Description |
|-----------|------|-------------|
| `MockBroker` | `adapters/simulation/mock_broker.py` | Simulated order execution, position tracking |
| `MockMarketData` | `adapters/simulation/mock_market_data.py` | Historical data provider with sim clock |
| `SimulationClock` | `adapters/simulation/sim_clock.py` | Time control for backtesting |
| Simulation API | `api/routes/automation_simulation.py` | REST endpoints for simulation control |

---

## When to Use Each Test

| Scenario | Recommended Test |
|----------|-----------------|
| Verify scanner logic | `test_simulation_e2e` |
| Test full trading flow (entry/exit) | `test_full_simulation` |
| Test API integration | `test_nac_simulation_integration` |
| Debug specific component | Direct Python import |

---

## Quick Start

```powershell
# Run scanner-only test
python -m nexus2.tests.test_simulation_e2e

# Run full trading loop test
python -m nexus2.tests.test_full_simulation

# Run API integration test (requires server running)
python nexus2/tests/test_nac_simulation_integration.py
```
