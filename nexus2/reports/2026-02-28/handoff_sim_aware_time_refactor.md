# Refactor: Centralize sim_aware_now_utc() in time_utils.py

**Agent:** Backend Specialist  
**Priority:** P1  
**Date:** 2026-02-28  
**Prereqs:** Exit clock fix already applied (4 sites in warrior_monitor_exit.py)

---

## Goal

Replace the scattered `_get_sim_aware_now_utc(monitor)` helper pattern with a centralized `sim_aware_now_utc()` function in `time_utils.py` that uses the **existing** `_sim_clock_ctx` ContextVar. This also fixes the 2 remaining `now_utc()` sites at L1505/L1534 that the previous fix missed.

---

## Step 1: Add `sim_aware_now_utc()` to time_utils.py

**File:** `nexus2/utils/time_utils.py`  
**Where:** After `now_utc()` (line ~57)

```python
def sim_aware_now_utc() -> datetime:
    """Returns sim clock time if in sim context, else real UTC.
    
    Use this INSTEAD of now_utc() in trading logic that must
    respect simulated time (exit logic, grace periods, cooldowns).
    
    In live mode, the ContextVar is unset → falls back to now_utc().
    In sim mode, the ContextVar is set per-case → returns sim time.
    
    DO NOT use this for:
    - DB timestamps (use now_utc())
    - API response timestamps (use now_utc())
    - Dataclass defaults (use now_utc_factory())
    - Logging timestamps (use now_utc())
    """
    from nexus2.adapters.simulation.sim_clock import _sim_clock_ctx
    clock = _sim_clock_ctx.get()
    if clock and clock.current_time:
        return clock.current_time
    return now_utc()


def sim_aware_now_et() -> datetime:
    """Returns sim clock time in ET if in sim context, else real ET.
    
    Same as sim_aware_now_utc() but returns Eastern Time.
    Use for cases where datetime.now(ET) was used directly.
    """
    from nexus2.adapters.simulation.sim_clock import _sim_clock_ctx
    clock = _sim_clock_ctx.get()
    if clock and clock.current_time:
        return clock.current_time.astimezone(EASTERN)
    return now_et()
```

---

## Step 2: Refactor warrior_monitor_exit.py

**File:** `nexus2/domain/automation/warrior_monitor_exit.py`

### 2a: Remove the `_get_sim_aware_now_utc()` helper
The Backend Specialist added a local helper function. Remove it entirely — `sim_aware_now_utc()` from time_utils replaces it.

### 2b: Replace all `_get_sim_aware_now_utc(monitor)` calls
Replace with `sim_aware_now_utc()` (no args needed — ContextVar handles scope).

### 2c: Replace the `datetime.now(ZoneInfo("America/New_York"))` sim-clock block
At the 5m bucket (around L516), the Backend Specialist added a multi-line if/else block. Replace with:
```python
et_now = sim_aware_now_et()
```

### 2d: Fix remaining `now_utc()` at L1505 and L1534
These are in `_execute_exit_signal` and were missed by the previous fix. Replace with `sim_aware_now_utc()`.

### 2e: Fix remaining `datetime.now()` at L222, L233, L537
Check each — if it's trading logic (not just a live-mode fallback), replace with `sim_aware_now_et()`. If it's an intentional live-mode fallback inside the existing if/else, it can stay.

---

## Step 3: Update imports

In `warrior_monitor_exit.py`, add:
```python
from nexus2.utils.time_utils import sim_aware_now_utc, sim_aware_now_et
```

Remove any now-unused imports of `_get_sim_aware_now_utc`.

---

## DO NOT Modify

- `now_utc()` itself — it must stay as real UTC for DB/API/logging
- `now_utc_factory()` — dataclass defaults stay real UTC
- Any `now_utc()` calls OUTSIDE of trading logic (DB writes, API timestamps, etc.)

---

## Verification

1. `python -m pytest nexus2/tests/ -x -q` — all 844 tests pass
2. `Select-String -Path nexus2\domain\automation\warrior_monitor_exit.py -Pattern "now_utc\(\)" | Measure-Object` — should be 0 (all replaced with sim_aware_now_utc)
3. `Select-String -Path nexus2\domain\automation\warrior_monitor_exit.py -Pattern "_get_sim_aware_now_utc"` — should be 0 (helper removed)
4. `Select-String -Path nexus2\domain\automation\warrior_monitor_exit.py -Pattern "datetime\.now\("` — should be 0 (all replaced with sim_aware_now_et)

---

## Deliverable

- Modified `time_utils.py` with new functions
- Modified `warrior_monitor_exit.py` with refactored calls
- Backend status report at `nexus2/reports/2026-02-28/backend_status_sim_aware_refactor.md`
