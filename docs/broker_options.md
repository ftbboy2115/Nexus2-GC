# Nexus 2 Brokerage Options

## Currently Implemented

### Alpaca ✅ (Primary)
- **Status:** Production-ready
- **File:** `nexus2/adapters/broker/alpaca_broker.py`
- **API Type:** REST + WebSocket
- **Features:**
  - Paper and live trading
  - Fractional shares
  - Extended hours trading
  - Real-time order status via WebSocket
- **Data:** Free Level 1 quotes, basic historical data
- **Cost:** Free commissions

### Paper Broker ✅ (Simulation)
- **Status:** Production-ready
- **File:** `nexus2/adapters/broker/paper_broker.py`
- **Purpose:** Mock trading for testing without API calls

---

## Potential Integrations

### Lightspeed 🔍 (Researched Jan 2026)
- **Status:** Not implemented
- **API:** Lightspeed Connect (WebSocket + JSON, launched Nov 2024)
- **Best for:** Fast execution on momentum stocks
- **Features:**
  - Direct market access
  - Multi-asset (stocks, options, futures)
  - Low-latency order routing
- **Data:** Requires third-party (Polygon.io, Databento)
  - No Level 2 bundle (~$91/mo for all exchanges separately)
  - Free Level 1 with $25K+ account
- **Cost:** 
  - Software: $130/mo (waived with $130+ commissions)
  - Per-share: $0.004 (tiered down to $0.001)
- **Certification:** Required before production access
- **Value Proposition:** Execution quality, not data pricing
- **Ross Cameron uses this broker**

### Schwab/TD Ameritrade 🔍 (Partial)
- **Status:** Data integration only
- **File:** `nexus2/adapters/market_data/schwab_adapter.py`
- **Notes:** NBBO quote validation, no order execution yet

### Interactive Brokers 🔍 (Not started)
- **Status:** Not implemented
- **Notes:** Popular for prop trading, TWS API available

---

## Broker Selection Criteria

| Criteria | Alpaca | Lightspeed |
|----------|--------|------------|
| Ease of integration | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| Commission cost | Free | Tiered |
| Execution speed | Good | Excellent |
| Minimum balance | None | $25K+ |
| Paper trading | ✅ | ✅ (certification) |
| Market data included | Basic | None |
