# Handoff: Testing Specialist — L2 Phase 2 Validation

## Task
Independently validate the Backend Specialist's L2 Phase 2 implementation (subscription manager + engine integration). Verify all 11 claims and write unit tests.

## Context
- Backend status: `nexus2/reports/2026-02-27/backend_status_l2_phase2.md`
- Phase 1 tests (still must pass): `nexus2/tests/unit/market_data/test_l2_types.py`, `test_l2_recorder.py`
- New code: `l2_subscription_manager.py`, modified `warrior_engine.py`

## Important: Search Path
Use `C:\Dev\Nexus` for `Select-String` and search tools.

---

## Claims to Verify (11 total)

### Import / Init Tests (Claims 1-2)

| # | Claim | Command |
|---|-------|---------|
| 1 | `L2SubscriptionManager` imports cleanly | `.venv\Scripts\python -c "from nexus2.domain.market_data.l2_subscription_manager import L2SubscriptionManager; print('PASS')"` |
| 2 | Engine init has `_l2_streamer=None`, `_l2_recorder=None`, `_l2_sub_manager=None` | `.venv\Scripts\python -c "from nexus2.domain.automation.warrior_engine import WarriorEngine; e=WarriorEngine(); print(e._l2_streamer, e._l2_recorder, e._l2_sub_manager)"` → `None None None` |

### Method Existence (Claims 3-4)

| # | Claim | Command |
|---|-------|---------|
| 3 | `_start_l2` is async method | `Select-String "async def _start_l2" C:\Dev\Nexus\nexus2\domain\automation\warrior_engine.py` |
| 4 | `_stop_l2` is async method | `Select-String "async def _stop_l2" C:\Dev\Nexus\nexus2\domain\automation\warrior_engine.py` |

### Status Integration (Claims 5-6)

| # | Claim | Command |
|---|-------|---------|
| 5 | `_get_l2_status()` returns `None` when disabled | `.venv\Scripts\python -c "from nexus2.domain.automation.warrior_engine import WarriorEngine; e=WarriorEngine(); print(e._get_l2_status())"` → `None` |
| 6 | `get_status()` includes `"l2"` key | `.venv\Scripts\python -c "from nexus2.domain.automation.warrior_engine import WarriorEngine; e=WarriorEngine(); s=e.get_status(); print('l2' in s, s['l2'])"` → `True None` |

### Feature Flag (Claims 7-8)

| # | Claim | Command |
|---|-------|---------|
| 7 | L2 start guarded behind `L2_ENABLED` | `Select-String "L2_ENABLED" C:\Dev\Nexus\nexus2\domain\automation\warrior_engine.py` |
| 8 | L2 sub update happens in `_run_scan()` | `Select-String "l2_sub_manager" C:\Dev\Nexus\nexus2\domain\automation\warrior_engine.py` |

### Regression (Claim 9)

| # | Claim | Command |
|---|-------|---------|
| 9 | All existing tests pass | `.venv\Scripts\python -m pytest nexus2/tests/ -v --timeout=30 -x -q` → 798+ passed |

### Subscription Manager Logic (Claims 10-11)

| # | Claim | Command |
|---|-------|---------|
| 10 | Manager respects `max_symbols` | Review `L2SubscriptionManager.__init__` — `max_symbols` param exists and is passed to streamer |
| 11 | Manager ranks by `quality_score` descending | Review `update_watchlist()` sorts `reverse=True` |

---

## Unit Tests to Write

### `nexus2/tests/unit/market_data/test_l2_subscription_manager.py`
- Manager initializes with max_symbols
- `update_watchlist` with 3 symbols → all 3 subscribed
- `update_watchlist` with 6 symbols (max=5) → only top 5 by quality_score subscribed
- `update_watchlist` with new higher-priority symbol → lowest evicted
- `get_active_subscriptions()` returns correct list
- `get_status()` returns expected dict shape
- Empty watchlist → empty subscriptions

Note: You'll need to mock `SchwabL2Streamer` since it requires Schwab auth for real connections. Use `unittest.mock.AsyncMock` for the async methods.

---

## Validation Report Format

Use the same format as Phase 1 validation:
```markdown
## Validation Report: L2 Phase 2

### Claims Verified
| # | Claim | Result | Evidence |
|---|-------|--------|----------|

### Unit Tests
| Test File | Tests Run | Passed | Failed |

### Overall Rating
HIGH / MEDIUM / LOW
```
