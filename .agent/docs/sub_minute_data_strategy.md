# Sub-Minute Data Strategy

## Implementation Status

| Phase | Status | Notes |
|-------|--------|-------|
| **Polygon Adapter** | ✅ Complete | `get_second_bars(symbol, seconds=10)` added |
| **10s Data Verified** | ✅ Complete | GRI 2026-01-28: 1,383 bars fetched |
| **Mock Market Integration** | ⬜ Pending | Update historical_bar_loader.py |
| **Live 10s Monitoring** | ⬜ Future | Low priority |

## Current Limitation

The Warrior bot uses **1-minute bars** for pattern detection and entry timing. Ross Cameron uses **10-second charts** for micro-timing entries during fast premarket moves.

### Impact

| Scenario | Ross (10s) | Bot (1m) | Result |
|----------|------------|----------|--------|
| GRI 01/28 | Entry at $5.97 during 08:31-08:35 surge | Entry at $4.15 on later pullback | -$1.81 delta, -$15 loss |
| Fast breakouts | Can enter within seconds of confirmation | Must wait for 1m candle close | Missed initial move |

## Polygon.io 10-Second Bars

Polygon.io added "second aggregates" in September 2023. **Implementation complete** in `polygon_adapter.py`:

```python
# Usage (now available)
from nexus2.adapters.market_data.polygon_adapter import get_polygon_adapter

polygon = get_polygon_adapter()
bars = polygon.get_second_bars("GRI", seconds=10, from_date="2026-01-28")
# Returns list of OHLCV with 10s granularity
```

## Implementation Path

### Phase 1: Historical 10s for Mock Market (Next)
- [ ] Fetch and cache 10s bars to JSON for test cases with `ross_chart_timeframe: "10s"`
- [ ] Update historical_bar_loader.py to support `timeframe="10s"`
- [ ] Enable high-fidelity replay matching Ross's timing

### Phase 2: Live 10s Monitoring (Future)
- Use Polygon WebSocket for real-time 10s aggregates
- More API overhead, only for premarket fast movers

## Test Cases with 10s Timing

| Symbol | Date | Ross Entry Time | Ross Chart | In YAML |
|--------|------|-----------------|------------|---------|
| GRI | 2026-01-28 | 08:45 | 10s | ✅ `ross_chart_timeframe: "10s"` |

## Recommendation

Start with **Phase 1** for Mock Market accuracy. This is a simulation-only change with no live trading risk.

