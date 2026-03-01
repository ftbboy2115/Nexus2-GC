# Fix Batch Test Divergence: wall-clock → sim-clock in Exit Logic

**Agent:** Backend Specialist  
**Priority:** P1  
**Date:** 2026-02-28  
**Prereqs:** Research verified by Audit Validator (all 10 claims PASS, HIGH rating)

---

## Context

Batch test results diverge between local (10-core, $391K PnL) and VPS (1-core, $254K PnL) because `warrior_monitor_exit.py` uses real wall clock (`datetime.now()`, `now_utc()`) in 3 exit logic paths. During sim replay, real clock is meaningless — sim clock should be used instead.

**Research report:** `nexus2/reports/2026-02-28/research_batch_divergence.md`  
**Validation report:** `nexus2/reports/2026-02-28/validation_batch_divergence.md`

---

## Fix 1: Candle-under-candle 5m bucket (LINE 516-517)

**File:** `nexus2/domain/automation/warrior_monitor_exit.py`  
**Current (WRONG):**
```python
et_now = datetime.now(ZoneInfo("America/New_York"))
bucket_start_minute = (et_now.minute // 5) * 5
```

**Fix:** Use the same sim-clock-aware pattern from `_check_after_hours_exit` (lines 189-197):
```python
# Use sim clock if available (for batch test fidelity)
if hasattr(monitor, '_sim_clock') and monitor._sim_clock:
    clock_time = monitor._sim_clock.current_time
    et_now = clock_time.astimezone(ZoneInfo("America/New_York"))
else:
    et_now = datetime.now(ZoneInfo("America/New_York"))
bucket_start_minute = (et_now.minute // 5) * 5
```

**Important:** `monitor` is the first argument to the enclosing function. Verify you can access it at this scope.

---

## Fix 2: Spread grace period (LINE 285)

**File:** `nexus2/domain/automation/warrior_monitor_exit.py`  
**Current (WRONG):**
```python
seconds_since_entry = (now_utc() - entry_time).total_seconds()
```

**Fix:** Use bar count instead of wall clock for sim fidelity. Check if there's a `candles_since_entry` attribute on the position, or compute from sim clock:
```python
# Use sim clock for elapsed time (bar count) if available
if hasattr(monitor, '_sim_clock') and monitor._sim_clock:
    seconds_since_entry = (monitor._sim_clock.current_time - entry_time).total_seconds()
else:
    seconds_since_entry = (now_utc() - entry_time).total_seconds()
```

---

## Fix 3: Candle-under-candle grace (LINE 461)

Same pattern as Fix 2 — replace `now_utc()` with sim-clock-aware check.

---

## Fix 4: Topping tail grace (LINE 612)

Same pattern as Fix 2 — replace `now_utc()` with sim-clock-aware check.

---

## Verification

After implementing:

1. **Run batch locally:** `Invoke-RestMethod -Method POST -Uri "http://localhost:8000/warrior/sim/run_batch_concurrent" -ContentType "application/json" -Body '{}'`
2. **Run batch again locally:** Compare results — should be identical (determinism check)
3. **Deploy to VPS and run:** Results should now be much closer to local
4. **Run existing tests:** `python -m pytest nexus2/tests/ -x -q` — no regressions

---

## Deliverable

- Modified `warrior_monitor_exit.py` with all 4 fixes
- Backend status report at `nexus2/reports/2026-02-28/backend_status_exit_clock_fix.md` with testable claims
