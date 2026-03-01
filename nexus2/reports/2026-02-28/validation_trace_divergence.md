# Validation Report: Trace Divergence Research

**Validator:** Audit Validator  
**Date:** 2026-02-28  
**Reference:** `research_trace_divergence.md`

---

## Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | `_get_eastern_time()` at `warrior_engine.py:291-294` uses `datetime.now()` | **PASS** | Code at line 291-294 matches exactly |
| 2 | `time.time()` throttle at `warrior_engine_entry.py:398-402` | **PASS** | Code at line 398-402 matches exactly |
| 3 | `datetime.now()` in `trend_updated_at` at `warrior_entry_helpers.py:356` | **PASS** | Code at line 356 matches exactly |

---

## Detailed Verification

### Claim 1: `_get_eastern_time()` uses wall clock

**Claim:** `warrior_engine.py` lines 291-294 contains `_get_eastern_time()` using `datetime.now()`  
**Verification:** `view_file` on `warrior_engine.py` lines 285-300  
**Actual Output:**
```python
# Lines 291-294
def _get_eastern_time(self) -> datetime:
    """Get current time in Eastern timezone."""
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/New_York"))
```
**Result:** ✅ PASS  
**Notes:** Exact match. Line numbers and code snippet are accurate. This function is called at `warrior_engine_entry.py:462` for `time_score` computation — also confirmed at line 462-463 of that file.

---

### Claim 2: `time.time()` throttle for technical updates

**Claim:** `warrior_engine_entry.py` lines 398-402 uses `time.time()` for 60-second throttle  
**Verification:** `view_file` on `warrior_engine_entry.py` lines 390-415  
**Actual Output:**
```python
# Lines 398-402
import time as _time
_last = getattr(watched, '_last_tech_update_ts', 0)
if _time.time() - _last >= 60:
    await update_candidate_technicals(engine, watched, current_price)
    watched._last_tech_update_ts = _time.time()
```
**Result:** ✅ PASS  
**Notes:** Exact match. Both the `time.time()` read (line 400) and the `time.time()` write (line 402) use wall clock. The report's analysis of sim-speed impact is consistent with the code.

---

### Claim 3: `datetime.now()` in `trend_updated_at`

**Claim:** `warrior_entry_helpers.py` line 356 sets `trend_updated_at` using `datetime.now(timezone.utc)`  
**Verification:** `view_file` on `warrior_entry_helpers.py` lines 345-370  
**Actual Output:**
```python
# Line 356
watched.trend_updated_at = datetime.now(timezone.utc)
```
**Result:** ✅ PASS  
**Notes:** Exact match. Located inside `update_candidate_technicals()`. Notably, the same function already uses `_sim_clock` for session phase filtering (lines 296-304), making the `datetime.now()` on line 356 inconsistent with the sim-aware pattern already in place.

---

## Overall Rating

**HIGH** — All 3 claims verified, line numbers and code snippets match exactly.
