# Backend Status: Phase 3 Wall-Clock Leak Fixes

**Date:** 2026-03-01  
**Agent:** Backend Specialist  
**Handoff:** `handoff_phase3_wall_clock_fix.md`

---

## Summary

Fixed 6 wall-clock leaks in entry pattern detection that caused $139K batch divergence between Windows and Linux. All fixes replace `datetime.now()`, `now_utc()`, or `time.time()` with centralized `sim_aware_now_utc()` / `sim_aware_now_et()` from `nexus2/utils/time_utils.py`.

---

## Changes Made

### File 1: `warrior_entry_patterns.py` (4 fixes)

| Fix | Lines | Before | After |
|-----|-------|--------|-------|
| 1 | 304-317→304-306 | `datetime.now(et)` + 14-line `get_simulation_clock()` fallback | `sim_aware_now_et()` (2 lines) |
| 2 | 457-462 | `from nexus2.utils.time_utils import now_utc` → `now_utc()` | `sim_aware_now_utc()` |
| 3 | 586-601→585-588 | `get_simulation_clock()` / `_dt.now(pytz)` fallback (16 lines) | `sim_aware_now_et()` (3 lines) |
| 4 | 814 | `datetime.now(timezone.utc).strftime("%H:%M")` | `sim_aware_now_utc().strftime("%H:%M")` |

### File 2: `warrior_engine_entry.py` (1 fix)

| Fix | Line | Before | After |
|-----|------|--------|-------|
| 5 | 828 | `datetime.now(timezone.utc).strftime("%H:%M")` | `sim_aware_now_utc().strftime("%H:%M")` |

### File 3: `trade_event_service.py` (1 fix)

| Fix | Line | Before | After |
|-----|------|--------|-------|
| 6 | 1066 | `time.time()` | `sim_aware_now_utc().timestamp()` |

---

## Testable Claims

### Claim 1: All 844 tests pass with 0 failures
```
python -m pytest nexus2/tests/ -x --tb=short -q
```
**Result:** 844 passed, 4 skipped, 3 deselected in 133.18s

### Claim 2: No `datetime.now()` or `time.time()` remains in `warrior_entry_patterns.py`
```powershell
Select-String -Path "nexus2\domain\automation\warrior_entry_patterns.py" -Pattern "datetime\.now\(|time\.time\(\)"
```
**Expected:** 0 matches

### Claim 3: No `datetime.now()` or `time.time()` remains in `warrior_engine_entry.py`
```powershell
Select-String -Path "nexus2\domain\automation\warrior_engine_entry.py" -Pattern "datetime\.now\(|time\.time\(\)"
```
**Expected:** 0 matches

### Claim 4: No `time.time()` remains in `trade_event_service.py`
```powershell
Select-String -Path "nexus2\domain\automation\trade_event_service.py" -Pattern "time\.time\(\)"
```
**Expected:** 0 matches

### Claim 5: Fix 1 reduces DIP_FOR_LEVEL time gate from 14 lines to 2 lines
The entire `datetime.now(et)` + `get_simulation_clock()` fallback block (lines 304-317) was replaced with:
```python
from nexus2.utils.time_utils import sim_aware_now_et
now_et = sim_aware_now_et()
```

### Claim 6: Fix 3 reduces PMH premarket detection from 16 lines to 3 lines
The entire `get_simulation_clock()` / `_dt.now(pytz)` fallback block (lines 586-601) was replaced with:
```python
from nexus2.utils.time_utils import sim_aware_now_et
_now_et = sim_aware_now_et()
is_premarket = _now_et.hour < 9 or (_now_et.hour == 9 and _now_et.minute < 30)
```

### Claim 7: No negative impact on live trading
`sim_aware_now_utc()` and `sim_aware_now_et()` fall back to `now_utc()` / `now_et()` when no sim clock is set (i.e., in live mode the ContextVar is unset → real wall clock is used).

---

## Verification Results

- ✅ 844/844 tests pass
- ✅ 0 `datetime.now()` matches in `warrior_entry_patterns.py`
- ✅ 0 `datetime.now()` matches in `warrior_engine_entry.py`  
- ✅ 0 `time.time()` matches in `trade_event_service.py`
- ✅ Net code reduction: ~25 lines removed (manual sim_clock fallback blocks eliminated)
