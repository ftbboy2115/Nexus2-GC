# Backend Status: L2 Phase 2 — Subscription Manager + Engine Integration

## Summary

Created `l2_subscription_manager.py` and wired L2 streaming into the Warrior engine lifecycle. All behind `L2_ENABLED` feature flag. Zero regressions (798 tests pass).

## Files Changed

### [NEW] `nexus2/domain/market_data/l2_subscription_manager.py`
- `L2SubscriptionManager` class with `update_watchlist()`, `get_active_subscriptions()`, `get_status()`
- Ranks candidates by `quality_score` (descending), subscribes top N
- Delegates to `SchwabL2Streamer.update_subscriptions()` for efficient diff-based rotation
- Logs all subscription changes with `[L2 Sub Manager]` prefix

### [MODIFY] `nexus2/domain/automation/warrior_engine.py`
5 integration points + 3 helper methods:

1. **`__init__` (line 123-125)**: Added `_l2_streamer`, `_l2_recorder`, `_l2_sub_manager` instance vars (all `None`)
2. **`start()` (line 338-340)**: Conditionally calls `_start_l2()` when `L2_ENABLED=true`
3. **`stop()` (line 372-374)**: Calls `_stop_l2()` if streamer exists
4. **`_run_scan()` (line 513-515)**: Updates L2 subscriptions after each scan via `_l2_sub_manager.update_watchlist()`
5. **`get_status()` (line 840)**: Adds `"l2"` key via `_get_l2_status()`

Helper methods (lines 401-475):
- `_start_l2()`: Instantiates `SchwabL2Streamer`, `L2Recorder`, `L2SubscriptionManager`; wires recorder as update callback; starts both. Non-fatal on failure.
- `_stop_l2()`: Stops recorder then streamer; nullifies all refs in `finally` block.
- `_get_l2_status()`: Returns `None` when disabled, or `{enabled, connected, subscriptions, manager}` dict when enabled.

## Testable Claims

| # | Claim | Verification |
|---|-------|-------------|
| 1 | `L2SubscriptionManager` imports cleanly | `.venv\Scripts\python -c "from nexus2.domain.market_data.l2_subscription_manager import L2SubscriptionManager; print('OK')"` |
| 2 | Engine initializes with `_l2_streamer=None`, `_l2_recorder=None`, `_l2_sub_manager=None` | `.venv\Scripts\python -c "from nexus2.domain.automation.warrior_engine import WarriorEngine; e=WarriorEngine(); print(e._l2_streamer, e._l2_recorder, e._l2_sub_manager)"` → `None None None` |
| 3 | `_start_l2` method exists and is async | `Select-String "async def _start_l2" nexus2\domain\automation\warrior_engine.py` |
| 4 | `_stop_l2` method exists and is async | `Select-String "async def _stop_l2" nexus2\domain\automation\warrior_engine.py` |
| 5 | `_get_l2_status` returns `None` when `L2_ENABLED=false` | `.venv\Scripts\python -c "from nexus2.domain.automation.warrior_engine import WarriorEngine; e=WarriorEngine(); print(e._get_l2_status())"` → `None` |
| 6 | `get_status()` includes `"l2"` key | `.venv\Scripts\python -c "from nexus2.domain.automation.warrior_engine import WarriorEngine; e=WarriorEngine(); s=e.get_status(); print('l2' in s, s['l2'])"` → `True None` |
| 7 | L2 start is guarded behind `app_config.L2_ENABLED` in `start()` | `Select-String "L2_ENABLED" nexus2\domain\automation\warrior_engine.py` |
| 8 | L2 subscription update happens after scan log line | `Select-String "l2_sub_manager" nexus2\domain\automation\warrior_engine.py` |
| 9 | Existing tests pass (no regressions) | `pytest nexus2/tests/ -v --timeout=30 -x -q` → 798 passed |
| 10 | Subscription manager respects `max_symbols` (capped by `L2_MAX_SYMBOLS`) | Check `L2SubscriptionManager.__init__` takes `max_symbols` param, passes to streamer |
| 11 | Subscription manager ranks by `quality_score` descending | Check `update_watchlist()` sorts with `reverse=True` on `_get_quality_score` |
