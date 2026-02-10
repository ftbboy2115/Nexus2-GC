# Wave 1 Test Report: Phases 1-2

**Tester:** Testing Specialist (Claude)
**Date:** 2026-02-10
**Test File:** [test_concurrent_isolation.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/tests/test_concurrent_isolation.py)
**Audit Report:** [wave1_audit_report.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/wave1_audit_report.md) — All 8 claims PASS

---

## New Tests

| # | Test | Result | What It Validates |
|---|------|:------:|-------------------|
| T1 | ContextVar clock isolation | **PASS** ✅ | Two `asyncio.gather` tasks get independent clocks via `set_simulation_clock_ctx` |
| T2 | ContextVar fallback to global | **PASS** ✅ | Without ContextVar set, `get_simulation_clock()` returns global singleton |
| T3 | MockBroker clock injection | **PASS** ✅ | `sell_position()` uses injected clock's time for `sim_time` field |
| T4 | MockBroker backward compat | **PASS** ✅ | `MockBroker()` without `clock` param still works, falls back to global |
| T5 | `is_sim_mode()` ContextVar | **PASS** ✅ | `set_sim_mode_ctx(True)` makes `is_sim_mode()` return `True` |
| T6 | `is_sim_mode()` concurrent isolation | **PASS** ✅ | Two `asyncio.gather` tasks have independent `is_sim_mode()` state |

---

## Regression Tests

- **Total:** 670 tests
- **Passed:** 601
- **Failed:** 65 (all pre-existing, see below)
- **Skipped:** 4

### Pre-Existing Failures (NOT related to Wave 1)

| Category | Count | Root Cause |
|----------|:-----:|------------|
| `asyncio.get_event_loop()` deprecated | 57 | Tests use `asyncio.get_event_loop()` which raises `RuntimeError` in Python 3.12+. Affects `test_ma_check`, `test_position_monitor`, `test_warrior_engine`, `test_warrior_monitor`, `test_monitor_partials`. |
| `min_dollar_volume` AttributeError | 2 | `test_warrior_routes.py` references `WarriorScanSettings.min_dollar_volume` which no longer exists (schema drift). |
| `warrior_scan_results.price` column | 3 | Model has `price` column but SQLite table doesn't — migration not applied in test DB. |
| `test_timezone_compliance` | 1 | Pre-existing `datetime.now()` violations in `catalyst_search_service.py` and `warrior_scanner_service.py`. |
| Unrelated `conftest` warnings | 2 | Unawaited coroutine warnings from mock objects. |

> [!IMPORTANT]
> **Zero failures are related to Phase 1-2 changes.** All 65 failures reproduce without the Wave 1 code — they are pre-existing technical debt.

---

## Verdict

### ✅ ALL NEW TESTS PASS — Wave 1 Complete, Ready for Wave 2

Phase 1-2 concurrent isolation is verified:
- ContextVar clock isolation works correctly under `asyncio.gather`
- MockBroker clock injection works with backward compatibility preserved
- `is_sim_mode()` ContextVar provides per-task isolation with legacy fallback

### Recommended Cleanup (non-blocking, future pass)
1. Fix 57 tests using deprecated `asyncio.get_event_loop()` → use `asyncio.run()`
2. Fix `WarriorScanSettings.min_dollar_volume` schema drift (2 tests)
3. Add `price` column migration for `warrior_scan_results` (3 tests)
4. Fix `datetime.now()` violations in scanner/catalyst code (1 test)
