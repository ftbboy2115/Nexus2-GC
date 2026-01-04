# Mock Market Simulation Page

> **Last Updated:** January 3, 2026

## Existing Backend Endpoints (Ready for GUI)

| Endpoint | Purpose |
|----------|---------|
| `GET /simulation/status` | Clock time, broker state, market data info |
| `GET /simulation/positions` | MockBroker positions + P&L |
| `POST /simulation/reset` | Reset clock, cash, load synthetic data |
| `POST /simulation/advance` | Advance by minutes/hours/days |
| `POST /simulation/load_historical` | Load real FMP data for symbol |
| `POST /simulation/load_htf_pattern` | Create synthetic HTF setup |
| `GET /simulation/broker` | Full broker state |
| `GET /simulation/test_cases` | List curated test scenarios |
| `POST /simulation/test_cases/{id}` | Load specific test case |

---

## What We Need to Build

### Backend (Minimal)
- [ ] `POST /simulation/run-scenario` — Auto-run N days
- [ ] `GET /simulation/progress` — SSE stream for real-time events
- [ ] `POST /simulation/pause` — Pause auto-run
- [ ] Speed multiplier support in sim_clock

### Frontend (New Page)
- [ ] `pages/simulation.tsx` — Full control panel
- [ ] Clock display + advance controls
- [ ] Scenario builder (load historical / synthetic)
- [ ] Auto-run controls with real-time event log
- [ ] Stats dashboard (cash, equity, P&L)

---

## Page Layout

```
┌─────────────────────────────────────────────────┐
│ MOCK MARKET CONTROL PANEL           [SIM MODE] │
├───────────────────┬─────────────────────────────┤
│ Clock Controls    │ Stats Dashboard             │
│ ─────────────     │ ─────────────────           │
│ Date: 2021-01-21  │ Cash: $95,000               │
│ [◀ Day] [Day ▶]   │ Equity: $100,477            │
│ [Play] [Pause]    │ Unrealized: +$477           │
│ Speed: [1x][5x]   │ Realized: $0                │
├───────────────────┴─────────────────────────────┤
│ Scenario Builder                                │
│ ─────────────────────────────────────           │
│ [Load Historical] Symbol: ___ Dates: ___ - ___ │
│ [Load Test Case] [▼ SMCI EP 2023           ]   │
│ [Create Synthetic] EP / HTF / Breakout          │
├─────────────────────────────────────────────────┤
│ Event Log (Real-time)                           │
│ ─────────────────────────────────────           │
│ 09:30 - Scan: Found 2 EP candidates            │
│ 09:31 - Entry: SMCI 150 shares @ $53.17        │
│ 09:45 - Stop checked: SMCI holding             │
│ ...                                            │
└─────────────────────────────────────────────────┘
```

---

## Verification

1. Load GME Jan 2021 data
2. Set clock to Jan 11, 2021
3. Auto-run 10 days
4. Verify NAC detects setups, enters, manages stops
