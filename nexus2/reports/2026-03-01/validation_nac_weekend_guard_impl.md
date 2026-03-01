# Validation Report: NAC Weekend Guard Implementation

**Date:** 2026-03-01
**Validator:** Testing Specialist
**Reference:** [backend_status_nac_weekend_guard.md](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-03-01/backend_status_nac_weekend_guard.md)

---

## Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | Weekend pre-check skips Alpaca API call in `_run_loop()` | **PASS** | `scheduler.py:200-204` — `if not self.sim_mode and now.weekday() >= 5:` with `logger.info` and `_smart_wait_for_market_open` |
| 2 | Force scan returns `{"status": "blocked"}` on weekend (non-sim) | **PASS** | `scheduler_routes.py:449-457` — guard checks `not sim_mode` + `current_weekday >= 5`, returns `{"status": "blocked", "reason": "..."}` |
| 3 | Guard only fires in non-sim mode | **PASS** | Both files gate on `not self.sim_mode` (scheduler.py:201) and `not sim_mode` (scheduler_routes.py:450) |
| 4 | Test `test_force_scan_blocked_on_weekend` exists and passes | **PASS** | `test_scheduler_routes.py:181-219` — mocks `now_et()` → Sunday, mocks settings with `sim_mode="false"`, asserts `status == "blocked"` and `"weekend" in reason` |

---

## Test Run

```
Command: python -m pytest nexus2/tests/api/test_scheduler_routes.py -v -m "not slow"
Result:  17 passed, 2 deselected in 12.70s
```

The 2 deselected tests are `test_force_scan` (marked `@pytest.mark.slow` — makes real FMP calls) and `test_discord_endpoint_exists` (marked `@pytest.mark.slow` — sends real Discord message). Both correctly excluded.

---

## Code Evidence

### Claim 1: `scheduler.py:200-204`

```python
# FAST CHECK: Skip weekends immediately (no API call needed)
if not self.sim_mode and now.weekday() >= 5:
    logger.info(f"[Scheduler] Weekend ({now.strftime('%A')}) - skipping scan cycle")
    await self._smart_wait_for_market_open(now)
    continue
```

**Verified with:** `view_file scheduler.py:195-215`
**Conclusion:** Guard is correctly placed before `self.is_market_hours` (L207), preventing the Alpaca API call on weekends. Uses `logger.info` for VPS visibility. Only applies to non-sim mode.

### Claim 2: `scheduler_routes.py:449-457`

```python
# Guard: Block force_scan on non-market days in non-sim mode (saves FMP API calls)
if not sim_mode:
    current_weekday = now_et().weekday()
    if current_weekday >= 5:
        logger.info(f"[ForceScan] Blocked on weekend ({now_et().strftime('%A')})")
        return {
            "status": "blocked",
            "reason": "Market closed (weekend) - force scan skipped to avoid FMP API waste. Use sim_mode for testing.",
        }
```

**Verified with:** `view_file scheduler_routes.py:440-470`
**Conclusion:** Guard is placed after settings load but before any FMP API calls. Returns clear `blocked` status with actionable reason. Sim mode scans remain unrestricted.

### Claim 4: `test_scheduler_routes.py:181-219`

```python
def test_force_scan_blocked_on_weekend(self, client):
    sunday = datetime(2026, 3, 1, 12, 0, 0, tzinfo=pytz.timezone("America/New_York"))
    assert sunday.weekday() == 6, "Test date must be a Sunday"
    
    with patch("nexus2.api.routes.scheduler_routes.now_et", return_value=sunday):
        # ... mocks SchedulerSettingsRepository with sim_mode="false" ...
        response = client.post("/automation/scheduler/force_scan")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "blocked"
    assert "weekend" in data["reason"].lower()
```

**Verified with:** `view_file test_scheduler_routes.py:175-225`
**Conclusion:** Test correctly mocks current time to Sunday, ensures sim_mode is false, and asserts both the `blocked` status and that "weekend" appears in the reason string.

---

## Overall Rating

**HIGH** — All 4 claims verified. Code is clean, guards are correctly placed, test coverage exists.
