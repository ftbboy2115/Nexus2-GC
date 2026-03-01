# Fix Entry Logic Wall-Clock Leaks (Root Cause of $137K Divergence)

**Agent:** Backend Specialist  
**Priority:** P0  
**Date:** 2026-02-28  
**Research:** `nexus2/reports/2026-02-28/research_trace_divergence.md`

---

## Context

The $137K batch divergence between Windows ($391K) and Linux ($254K) is caused by 3 wall-clock leaks in **entry logic**. We already have `sim_aware_now_utc()` and `sim_aware_now_et()` in `nexus2/utils/time_utils.py` for exactly this pattern.

---

## Fix 1: `_get_eastern_time()` — Pattern Competition Scoring (P0)

**File:** `nexus2/domain/automation/warrior_engine.py` lines 291-294  
**Current (WRONG):**
```python
def _get_eastern_time(self) -> datetime:
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/New_York"))
```

**Fix:** Use `sim_aware_now_et()` from time_utils:
```python
def _get_eastern_time(self) -> datetime:
    from nexus2.utils.time_utils import sim_aware_now_et
    return sim_aware_now_et()
```

**Why:** `time_score = compute_time_score(et_now.hour, et_now.minute)` in `warrior_engine_entry.py:462-463` uses this to score every pattern candidate. At 10 PM (when VPS batch ran), time_score is totally different than at 9:42 AM (sim time), flipping entry decisions.

---

## Fix 2: `time.time()` Technical Update Throttle (P0)

**File:** `nexus2/domain/automation/warrior_engine_entry.py` lines 398-402  
**Current (WRONG):**
```python
import time as _time
_last = getattr(watched, '_last_tech_update_ts', 0)
if _time.time() - _last >= 60:
    await update_candidate_technicals(engine, watched, current_price)
    watched._last_tech_update_ts = _time.time()
```

**Fix:** Use sim-aware time for the throttle:
```python
from nexus2.utils.time_utils import sim_aware_now_utc
_last = getattr(watched, '_last_tech_update_ts', 0)
_now = sim_aware_now_utc().timestamp()
if _now - _last >= 60:
    await update_candidate_technicals(engine, watched, current_price)
    watched._last_tech_update_ts = _now
```

**Why:** In sim mode, sim time advances 1 min per step. `sim_aware_now_utc().timestamp()` returns the sim timestamp, so technicals update every 60 simulated seconds (deterministic). In live mode, falls back to real `now_utc()` (preserving the API throttle).

---

## Fix 3: `datetime.now()` in trend_updated_at (P2)

**File:** `nexus2/domain/automation/warrior_entry_helpers.py` line 356  
**Current:**
```python
watched.trend_updated_at = datetime.now(timezone.utc)
```

**Fix:**
```python
from nexus2.utils.time_utils import sim_aware_now_utc
watched.trend_updated_at = sim_aware_now_utc()
```

---

## DO NOT Modify

- `sim_aware_now_utc()` or `sim_aware_now_et()` in time_utils.py — already correct
- Any live-mode behavior — all fixes fall back to real clock when no sim context

---

## Verification

1. `python -m pytest nexus2/tests/ -x -q` — all 844 tests pass
2. Run ROLR single case locally, note PnL
3. Run full batch locally: `Invoke-RestMethod -Method POST -Uri "http://localhost:8000/warrior/sim/run_batch_concurrent" -ContentType "application/json" -Body '{}'`
4. Compare total PnL to baseline ($391,215) — should be similar but may differ since time_score will now use sim time instead of wall-clock

---

## Deliverable

- Modified 3 files with fixes
- Backend status report at `nexus2/reports/2026-02-28/backend_status_entry_clock_fix.md` with testable claims
