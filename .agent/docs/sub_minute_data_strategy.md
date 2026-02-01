# Sub-Minute Data Strategy

## Current Limitation

The Warrior bot uses **1-minute bars** for pattern detection and entry timing. Ross Cameron uses **10-second charts** for micro-timing entries during fast premarket moves.

### Impact

| Scenario | Ross (10s) | Bot (1m) | Result |
|----------|------------|----------|--------|
| GRI 01/28 | Entry at $5.97 during 08:31-08:35 surge | Entry at $4.15 on later pullback | -$1.81 delta, -$15 loss |
| Fast breakouts | Can enter within seconds of confirmation | Must wait for 1m candle close | Missed initial move |

## Polygon.io 10-Second Bars

Polygon.io added "second aggregates" in September 2023. We can get 10s historical data:

```python
# Current 1-minute request
response = client.get_aggs(
    ticker=symbol,
    multiplier=1,
    timespan="minute",
    from_=start_date,
    to=end_date
)

# 10-second request (same API, different params)
response = client.get_aggs(
    ticker=symbol,
    multiplier=10,
    timespan="second",  # <-- Key change
    from_=start_date,
    to=end_date
)
```

## Implementation Path

### Phase 1: Historical 10s for Mock Market
- Fetch 10s bars for test cases where Ross used sub-minute timing
- Update historical_bar_loader.py to support `timeframe="10s"`
- Enable high-fidelity replay matching Ross's timing

### Phase 2: Live 10s Monitoring (Optional)
- Use Polygon WebSocket for real-time 10s aggregates
- More API overhead, but enables micro-timing like Ross
- Only needed for premarket fast movers

## Test Cases with 10s Timing

| Symbol | Date | Ross Entry Time | Ross Chart |
|--------|------|-----------------|------------|
| GRI | 2026-01-28 | 08:45 | 10s |

## Recommendation

Start with **Phase 1** for Mock Market accuracy. This is a simulation-only change with no live trading risk. It will reveal whether 10s granularity actually improves entry timing fidelity.
