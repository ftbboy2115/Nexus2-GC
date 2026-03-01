# Handoff: Phase 3 Wall-Clock Leak Fixes

**Agent:** Backend Specialist  
**Priority:** P1  
**Date:** 2026-03-01  
**Context:** `nexus2/reports/2026-03-01/research_batch_divergence_phase3.md`

---

## Problem

5 wall-clock leaks remain in `warrior_entry_patterns.py` and `warrior_engine_entry.py` that cause the $139K batch divergence between Windows ($409K) and Linux ($271K). All fixes use the same `sim_aware_now_utc()` / `sim_aware_now_et()` pattern proven in Phase 1-2.

---

## Verified Facts

All 6 sites verified via `view_file` on 2026-03-01:

| # | File | Line(s) | Current Code | Verified |
|---|------|---------|-------------|----------|
| 1 | `warrior_entry_patterns.py` | 304-317 | `datetime.now(et)` with `get_simulation_clock()` fallback | ✅ |
| 2 | `warrior_entry_patterns.py` | 458, 462 | `from nexus2.utils.time_utils import now_utc` → `now_utc()` | ✅ |
| 3 | `warrior_entry_patterns.py` | 586-601 | `_dt.now(pytz.timezone("US/Eastern"))` fallback | ✅ |
| 4 | `warrior_entry_patterns.py` | 814 | `datetime.now(timezone.utc).strftime("%H:%M")` | ✅ |
| 5 | `warrior_engine_entry.py` | 828 | `datetime.now(timezone.utc).strftime("%H:%M")` | ✅ |
| 6 | `trade_event_service.py` | 1066 | `time.time()` dedup | ✅ |

The `sim_aware_now_utc()` and `sim_aware_now_et()` functions are at `nexus2/utils/time_utils.py:59-91`.

---

## Changes Required

### Fix 1: DIP_FOR_LEVEL time gate (CRITICAL)
**File:** `warrior_entry_patterns.py` lines 304-317  
**Replace** the entire `datetime.now(et)` + `get_simulation_clock()` fallback block with:
```python
    # TIME GATE: DIP_FOR_LEVEL requires established intraday structure
    from nexus2.utils.time_utils import sim_aware_now_et
    now_et = sim_aware_now_et()
```
This replaces 14 lines with 2 lines. The variable `now_et` is still used on line 319 and line 393.

### Fix 2: Re-entry cooldown (CRITICAL)
**File:** `warrior_entry_patterns.py` lines 457-458, 462  
**Replace:**
```python
        from datetime import timedelta
        from nexus2.utils.time_utils import now_utc
```
**With:**
```python
        from datetime import timedelta
        from nexus2.utils.time_utils import sim_aware_now_utc
```
**And on line 462, replace:**
```python
            time_since_exit = (now_utc() - watched.last_exit_time).total_seconds() / 60
```
**With:**
```python
            time_since_exit = (sim_aware_now_utc() - watched.last_exit_time).total_seconds() / 60
```

### Fix 3: PMH premarket detection (CRITICAL)
**File:** `warrior_entry_patterns.py` lines 586-601  
**Replace** the entire `get_simulation_clock()` / `_dt.now()` fallback block with:
```python
    # Get current time for premarket-aware thresholds
    from nexus2.utils.time_utils import sim_aware_now_et
    _now_et = sim_aware_now_et()
    is_premarket = _now_et.hour < 9 or (_now_et.hour == 9 and _now_et.minute < 30)
```

### Fix 4: swing_high_time in entry_patterns (HIGH)
**File:** `warrior_entry_patterns.py` line 814  
**Replace:**
```python
        watched.swing_high_time = datetime.now(timezone.utc).strftime("%H:%M")
```
**With:**
```python
        from nexus2.utils.time_utils import sim_aware_now_utc
        watched.swing_high_time = sim_aware_now_utc().strftime("%H:%M")
```

### Fix 5: swing_high_time in engine_entry (HIGH)
**File:** `warrior_engine_entry.py` line 828  
**Replace:**
```python
        watched.swing_high_time = datetime.now(timezone.utc).strftime("%H:%M")
```
**With:**
```python
        from nexus2.utils.time_utils import sim_aware_now_utc
        watched.swing_high_time = sim_aware_now_utc().strftime("%H:%M")
```

### Fix 6: Dedup timer in trade_event_service (MEDIUM)
**File:** `trade_event_service.py` line 1066  
**Replace:**
```python
        now = time.time()
```
**With:**
```python
        from nexus2.utils.time_utils import sim_aware_now_utc
        now = sim_aware_now_utc().timestamp()
```
Also replace on line 1070:
```python
        self._trigger_rejection_dedup[dedup_key] = now
```
This stays the same since `now` is now sim-aware.

---

## Open Questions (Investigate During Implementation)

1. After Fix 1 removes the 14-line block, verify `now_et` is used correctly on lines 319 and 393 (premarket checks downstream).
2. After Fix 3, the variable name changes from `is_premarket` — ensure it's still used at line 615 and 656. The new code should use `is_premarket` as the variable name.

---

## Verification

```powershell
# 1. Run full test suite
python -m pytest tests/ -x

# 2. Verify no remaining datetime.now() or time.time() in entry decision path
Select-String -Path "nexus2\domain\automation\warrior_entry_patterns.py" -Pattern "datetime\.now\(|time\.time\(\)"
Select-String -Path "nexus2\domain\automation\warrior_engine_entry.py" -Pattern "datetime\.now\(|time\.time\(\)"
Select-String -Path "nexus2\domain\automation\trade_event_service.py" -Pattern "time\.time\(\)"
```

---

## Deliverable

Backend status report at `nexus2/reports/2026-03-01/backend_status_phase3_wall_clock_fix.md` with testable claims.
