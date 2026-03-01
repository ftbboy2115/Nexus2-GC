# Backend Status: Entry Logic Wall-Clock Fix

**Date:** 2026-02-28  
**Task:** Fix 3 wall-clock leaks in entry logic (root cause of $137K batch divergence)  
**Reference:** `nexus2/reports/2026-02-28/handoff_entry_clock_fix.md`  
**Status:** ✅ COMPLETE

---

## Changes Made

### Fix 1: `_get_eastern_time()` — Pattern Competition Scoring (P0)

**File:** `nexus2/domain/automation/warrior_engine.py:291-294`

```diff
 def _get_eastern_time(self) -> datetime:
-    """Get current time in Eastern timezone."""
-    from zoneinfo import ZoneInfo
-    return datetime.now(ZoneInfo("America/New_York"))
+    """Get current time in Eastern timezone (sim-aware)."""
+    from nexus2.utils.time_utils import sim_aware_now_et
+    return sim_aware_now_et()
```

**Impact:** `compute_time_score()` in pattern competition now uses simulated time (e.g., 9:42 AM) instead of wall-clock (e.g., 10 PM when VPS batch runs). This was the #1 divergence cause.

---

### Fix 2: `time.time()` Technical Update Throttle (P0)

**File:** `nexus2/domain/automation/warrior_engine_entry.py:398-403`

```diff
-import time as _time
+from nexus2.utils.time_utils import sim_aware_now_utc
 _last = getattr(watched, '_last_tech_update_ts', 0)
-if _time.time() - _last >= 60:
+_now = sim_aware_now_utc().timestamp()
+if _now - _last >= 60:
     await update_candidate_technicals(engine, watched, current_price)
-    watched._last_tech_update_ts = _time.time()
+    watched._last_tech_update_ts = _now
```

**Impact:** Technical updates now throttle on simulated time, meaning they fire every 60 simulated seconds (deterministic) instead of every 60 wall-clock seconds (non-deterministic across environments).

---

### Fix 3: `datetime.now()` in `trend_updated_at` (P2)

**File:** `nexus2/domain/automation/warrior_entry_helpers.py:356-357`

```diff
-watched.trend_updated_at = datetime.now(timezone.utc)
+from nexus2.utils.time_utils import sim_aware_now_utc
+watched.trend_updated_at = sim_aware_now_utc()
```

**Impact:** Lower priority — `trend_updated_at` is metadata, not decision logic. But ensures consistency.

---

## Testable Claims

| # | Claim | Verification |
|---|-------|-------------|
| 1 | `warrior_engine.py:291-294` no longer calls `datetime.now()` | `Select-String -Path nexus2\domain\automation\warrior_engine.py -Pattern "datetime\.now"` should return only `last_scan_at` (line 538), NOT `_get_eastern_time` |
| 2 | `warrior_engine.py:293` calls `sim_aware_now_et()` | `Select-String -Path nexus2\domain\automation\warrior_engine.py -Pattern "sim_aware_now_et"` should match line 293 |
| 3 | `warrior_engine_entry.py` no longer imports `time` module | `Select-String -Path nexus2\domain\automation\warrior_engine_entry.py -Pattern "import time"` should return 0 matches |
| 4 | `warrior_engine_entry.py` uses `sim_aware_now_utc().timestamp()` for throttle | `Select-String -Path nexus2\domain\automation\warrior_engine_entry.py -Pattern "sim_aware_now_utc"` should match lines ~398-403 |
| 5 | `warrior_entry_helpers.py:356-357` uses `sim_aware_now_utc()` for `trend_updated_at` | `Select-String -Path nexus2\domain\automation\warrior_entry_helpers.py -Pattern "sim_aware_now_utc"` should match lines 356-357 |
| 6 | All 804 tests pass (excluding pre-existing HIND scanner RVOL boundary bug) | `python -m pytest nexus2/tests/ -q --ignore=nexus2/tests/test_scanner_validation.py` → 804 passed |

---

## Pre-existing Issue (NOT introduced by this change)

`test_scanner_validation.py::test_known_winners_pass[ross_hind_20260127]` fails due to RVOL boundary condition: `2.0x < 2.0x` is false (should be `<=`). This is a scanner bug, not an entry clock issue.

---

## Live Mode Safety

All 3 fixes use `sim_aware_now_utc()` / `sim_aware_now_et()` which fall back to real `now_utc()` / `now_et()` when no sim context is active. **Zero impact on live trading.**
