# Backend Status: NAC Weekend Guard

**Date:** 2026-03-01  
**Agent:** Backend Specialist  
**Reference:** [handoff_nac_weekend_guard.md](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-03-01/handoff_nac_weekend_guard.md)

---

## Changes Made

### 1. [scheduler.py](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/scheduler.py) — `_run_loop()` (L200-204)

Added fast weekday pre-check before `is_market_hours` (which hits Alpaca API):

```python
# FAST CHECK: Skip weekends immediately (no API call needed)
if not self.sim_mode and now.weekday() >= 5:
    logger.info(f"[Scheduler] Weekend ({now.strftime('%A')}) - skipping scan cycle")
    await self._smart_wait_for_market_open(now)
    continue
```

- Uses `logger.info` for VPS visibility
- Only applies to non-sim mode (sim testing unaffected)
- Delegates to existing `_smart_wait_for_market_open` for sleep logic

---

### 2. [scheduler_routes.py](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/scheduler_routes.py) — `force_scheduler_scan()` (L449-458)

Added weekend guard after settings are loaded, before scan runs:

```python
if not sim_mode:
    current_weekday = now_et().weekday()
    if current_weekday >= 5:
        logger.info(f"[ForceScan] Blocked on weekend ({now_et().strftime('%A')})")
        return {
            "status": "blocked",
            "reason": "Market closed (weekend) - force scan skipped to avoid FMP API waste. Use sim_mode for testing.",
        }
```

- Returns `{"status": "blocked"}` instead of running FMP API scan
- Sim mode `force_scan` remains unrestricted

---

### 3. [test_scheduler_routes.py](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/tests/api/test_scheduler_routes.py) — `TestForceScan` class (L181-219)

Added `test_force_scan_blocked_on_weekend`:
- Mocks `now_et()` → Sunday 2026-03-01 12:00
- Mocks `SchedulerSettingsRepository` with `sim_mode=false`
- Asserts response is `{"status": "blocked"}` with "weekend" in reason

---

## Testable Claims

| # | Claim | File:Line | Verification |
|---|-------|-----------|--------------|
| 1 | Weekend pre-check skips Alpaca API call | `scheduler.py:200-204` | `Select-String "Weekend.*skipping scan" scheduler.py` |
| 2 | Force scan returns blocked on weekend | `scheduler_routes.py:449-458` | `Select-String "Blocked on weekend" scheduler_routes.py` |
| 3 | Guard only fires in non-sim mode | Both files | `Select-String "not sim_mode\|not self.sim_mode" scheduler*.py` |
| 4 | Test mocks Sunday and asserts blocked | `test_scheduler_routes.py:181-219` | `pytest test_scheduler_routes.py -k weekend -v` |

## Test Results

```
17 passed, 2 deselected in 12.60s
```

All non-slow tests pass including the new `test_force_scan_blocked_on_weekend`.

## Open Questions (from handoff)

1. **Holiday check** — Not implemented. The Alpaca calendar already handles holidays in `is_market_hours`. The fast weekday check only covers Sat/Sun. Adding holiday checks would require an API call, defeating the purpose of the fast check.
2. **`force_scan` holiday guard** — Same reasoning. Weekend-only is sufficient for now; holidays are rare and the FMP cost is minimal for ~10 holidays/year.
