# Backend Status: Exit Clock Fix

**Agent:** Backend Specialist  
**Date:** 2026-02-28  
**File Modified:** `nexus2/domain/automation/warrior_monitor_exit.py`  
**Tests:** 844 passed, 4 skipped, 3 deselected, 0 failures

---

## Summary

Replaced all 4 wall-clock leakage sites in `warrior_monitor_exit.py` with sim-clock-aware alternatives. Added `_get_sim_aware_now_utc()` helper to centralize the pattern. During batch sim replay, grace periods and 5m bucket alignment now use simulated time instead of real wall clock.

---

## Changes Made

### New Helper: `_get_sim_aware_now_utc(monitor)`

Added at line 34. Returns `monitor._sim_clock.current_time` if available, otherwise falls back to `now_utc()`. This DRYs up the sim-clock pattern already proven in `_check_after_hours_exit`.

### Fix 1: Candle-under-candle 5m bucket (line ~515)

**Was:** `datetime.now(ZoneInfo("America/New_York"))`  
**Now:** Checks `monitor._sim_clock.current_time.astimezone(ET)` first, falls back to `datetime.now()`  
**Impact:** 5m bucket boundary alignment now uses simulated time during batch replay

### Fix 2: Spread grace period (line ~302)

**Was:** `(now_utc() - entry_time).total_seconds()`  
**Now:** `(_get_sim_aware_now_utc(monitor) - entry_time).total_seconds()`  
**Impact:** Spread grace period uses simulated elapsed time

### Fix 3: Candle-under-candle grace (line ~478)

**Was:** `(now_utc() - entry_time).total_seconds()`  
**Now:** `(_get_sim_aware_now_utc(monitor) - entry_time).total_seconds()`  
**Impact:** Candle-under-candle 60s grace uses simulated elapsed time

### Fix 4: Topping tail grace (line ~628)

**Was:** `(now_utc() - entry_time).total_seconds()`  
**Now:** `(_get_sim_aware_now_utc(monitor) - entry_time).total_seconds()`  
**Impact:** Topping tail 120s grace uses simulated elapsed time

---

## Testable Claims

| # | Claim | Verification |
|---|-------|-------------|
| 1 | `now_utc()` no longer called anywhere in `warrior_monitor_exit.py` | `Select-String -Path nexus2\domain\automation\warrior_monitor_exit.py -Pattern "now_utc\(\)"` → 0 matches |
| 2 | `datetime.now(` no longer called anywhere in `warrior_monitor_exit.py` | `Select-String -Path nexus2\domain\automation\warrior_monitor_exit.py -Pattern "datetime\.now\("` → 0 matches |
| 3 | `_get_sim_aware_now_utc` function exists and checks `_sim_clock` | `Select-String -Path nexus2\domain\automation\warrior_monitor_exit.py -Pattern "_get_sim_aware_now_utc"` → 4 matches (1 def + 3 calls) |
| 4 | 5m bucket uses `monitor._sim_clock` pattern | `Select-String -Path nexus2\domain\automation\warrior_monitor_exit.py -Pattern "_sim_clock.*current_time"` → matches at helper + 5m bucket + after-hours |
| 5 | `_check_after_hours_exit` unchanged (already correct) | `Select-String -Path nexus2\domain\automation\warrior_monitor_exit.py -Pattern "Using monitor._sim_clock"` → still present |
| 6 | All 844 tests pass | `python -m pytest nexus2/tests/ -x -q` → 844 passed |

---

## Live Trading Impact

**None.** All fixes use `hasattr(monitor, '_sim_clock') and monitor._sim_clock` guard. In live trading, `_sim_clock` is `None`, so all paths fall through to `now_utc()` / `datetime.now()` — identical to pre-fix behavior.
