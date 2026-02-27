# Handoff: Backend Specialist — L2 Dashboard API Endpoint

## Task
Add a REST API endpoint that exposes real-time L2 order book data and signals for the Warrior dashboard.

## Important: Search Path
Use `C:\Dev\Nexus` for search tools.

## Dependencies
- `nexus2/adapters/market_data/schwab_l2_streamer.py` — `get_snapshot(symbol)`, `get_status()`
- `nexus2/domain/market_data/l2_signals.py` — `get_book_summary()`, `L2Summary`
- `nexus2/domain/market_data/l2_subscription_manager.py` — `get_active_subscriptions()`
- Engine has `self._l2_streamer`, `self._l2_sub_manager` (may be None)

---

## [MODIFY] `nexus2/api/routes/warrior_routes.py`

Add two endpoints:

### `GET /warrior/l2/status`
Returns L2 subsystem status:
```json
{
    "enabled": true,
    "connected": true,
    "subscriptions": ["ALBT", "BATL", "CD"],
    "snapshot_count": 3
}
```

### `GET /warrior/l2/{symbol}`
Returns current L2 book snapshot + signals for a specific symbol:
```json
{
    "symbol": "AAPL",
    "timestamp": "2026-02-27T17:31:45Z",
    "best_bid": 263.76,
    "best_ask": 263.80,
    "spread": 0.04,
    "bids": [
        {"price": 263.76, "volume": 50, "num_entries": 1},
        {"price": 263.71, "volume": 100, "num_entries": 2}
    ],
    "asks": [
        {"price": 263.80, "volume": 200, "num_entries": 1},
        {"price": 263.85, "volume": 75, "num_entries": 1}
    ],
    "signals": {
        "bid_wall": null,
        "ask_wall": {"price": 264.00, "volume": 15000, "side": "ask"},
        "thin_ask": null,
        "spread_quality": {
            "spread_bps": 1.5,
            "quality": "tight",
            "bid_depth": 5000,
            "ask_depth": 8000,
            "imbalance": -0.23
        }
    }
}
```
If symbol not subscribed or L2 disabled, return 404/503 with appropriate message.

---

## Implementation Notes

- Access the engine singleton the same way other warrior routes do (grep for how `engine` is accessed in the existing routes)
- Convert `Decimal` values to `float` for JSON serialization
- Convert `datetime` to ISO string
- Limit bids/asks to top 10 levels each (don't send the full book)
- Guard behind L2_ENABLED check

## Testable Claims
1. `/warrior/l2/status` returns 200 with enabled/connected/subscriptions fields
2. `/warrior/l2/{symbol}` returns 404 when L2 disabled
3. Existing tests pass (no regressions)
4. JSON is serializable (no Decimal/datetime errors)

> [!NOTE]
> **Testing Specialist will validate separately.** Do NOT write tests.
