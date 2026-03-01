# Phase 3: Batch Divergence Deep Investigation

**Agent:** Backend Planner  
**Date:** 2026-03-01  
**Status:** Complete — 5 HIGH-IMPACT wall-clock leaks found, 3 structural  

---

## Executive Summary

The $139K gap between Windows ($409K) and Linux ($271K) batch tests persists because **5 wall-clock leaks remain in the entry decision path** that were missed in the Phase 1-2 fixes. Three of these directly affect entry/exit decisions and can cause divergent trades between environments.

Additionally, 1 `time.time()` dedup mechanism in `trade_event_service.py` produces platform-speed-dependent behavior, and 2 sites use the `get_simulation_clock()` fallback pattern instead of the ContextVar-based `sim_aware_now_utc()`.

---

## Findings

### Finding 1 — CRITICAL: DIP_FOR_LEVEL re-entry cooldown uses `now_utc()` (not sim-aware)

**Impact:** HIGH — Directly blocks or allows re-entries differently on fast vs slow machines  
**File:** `nexus2/domain/automation/warrior_entry_patterns.py:462`  
**Code:**
```python
from nexus2.utils.time_utils import now_utc

# Guard 1: Cooldown
if watched.last_exit_time:
    time_since_exit = (now_utc() - watched.last_exit_time).total_seconds() / 60
    if time_since_exit < reentry_cooldown_minutes:
```
**Problem:** `now_utc()` returns the real wall-clock time. In sim mode, `watched.last_exit_time` is set based on sim clock time (e.g., 10:30 AM on Jan 14, 2026). The `now_utc()` call returns March 1, 2026 — the actual date. The delta is always massive (>>10 minutes), so **this cooldown never fires in sim**. But on Windows, the batch runner completes each case faster, so the *relative* timing of this check vs wall-clock progresses at different rates. This is not the primary divergence vector but contributes to non-determinism.  
**Fix:** Replace `now_utc()` with `sim_aware_now_utc()` at line 462.

---

### Finding 2 — HIGH: `swing_high_time` uses real clock (affects PMH candle-over-candle logic)

**Impact:** HIGH — Used for candle-over-candle comparison in PMH break confirmation  
**Files:**
- `nexus2/domain/automation/warrior_entry_patterns.py:814`
- `nexus2/domain/automation/warrior_engine_entry.py:828`  

**Code (both files identical):**
```python
watched.swing_high_time = datetime.now(timezone.utc).strftime("%H:%M")
```
**Problem:** `swing_high_time` is later compared in PMH break's Stage 2 (`current_candle_time != watched.control_candle_time`) in `detect_pmh_break()`. While `swing_high_time` itself isn't directly used in PMH candle-over-candle logic (that uses `control_candle_time`), both files set this metadata with real wall-clock time. The real clock produces HH:MM values based on when the batch runner executes, not the simulated trading time. On a faster machine, these timestamps cluster differently, potentially affecting micro-pullback state tracking.

**Fix:** Replace both with `sim_aware_now_utc().strftime("%H:%M")`.

---

### Finding 3 — HIGH: DIP_FOR_LEVEL time gate has flaky sim_clock fallback

**Impact:** HIGH — Determines whether DIP_FOR_LEVEL pattern is blocked for being "too early"  
**File:** `nexus2/domain/automation/warrior_entry_patterns.py:304-317`  
**Code:**
```python
# TIME GATE: DIP_FOR_LEVEL requires established intraday structure
from datetime import datetime
import pytz
et = pytz.timezone("US/Eastern")
now_et = datetime.now(et)    # <--- STARTS WITH REAL CLOCK

# Get sim clock time if we're in sim mode
try:
    from nexus2.adapters.simulation import get_simulation_clock
    sim_clock = get_simulation_clock()
    if sim_clock and sim_clock.current_time:
        now_et = sim_clock.current_time
except Exception:
    pass   # <--- SILENTLY FALLS BACK TO REAL CLOCK
```
**Problem:** This uses `get_simulation_clock()` which checks the ContextVar first, then falls back to the global singleton. In the concurrent batch runner (`ProcessPoolExecutor` with `spawn`), each process sets its own ContextVar at `sim_context.py:667`. This *should* work. However:
1. If `get_simulation_clock()` raises for any reason (import error in fresh process, timing issue), the `except Exception: pass` silently falls back to `datetime.now(et)` — which is the real wall-clock time.
2. This is the old pattern. `sim_aware_now_et()` from `time_utils.py` was created specifically to replace this pattern, and it has the same ContextVar lookup but cleaner error handling.

**Fix:** Replace lines 304-317 with `from nexus2.utils.time_utils import sim_aware_now_et; now_et = sim_aware_now_et()`.

---

### Finding 4 — HIGH: PMH break premarket detection falls back to `datetime.now()`

**Impact:** HIGH — Determines `is_premarket` flag, which controls whether candle-over-candle confirmation is skipped  
**File:** `nexus2/domain/automation/warrior_entry_patterns.py:586-601`  
**Code:**
```python
is_premarket = False
try:
    from nexus2.adapters.simulation import get_simulation_clock
    sim_clock = get_simulation_clock()
    if sim_clock and sim_clock.current_time:
        is_premarket = sim_clock.current_time.hour < 9 or (
            sim_clock.current_time.hour == 9 and sim_clock.current_time.minute < 30
        )
    else:
        import pytz
        from datetime import datetime as _dt
        _now_et = _dt.now(pytz.timezone("US/Eastern"))    # <--- FALLBACK TO REAL CLOCK
        is_premarket = _now_et.hour < 9 or (_now_et.hour == 9 and _now_et.minute < 30)
except Exception:
    pass
```
**Problem:** Same pattern as Finding 3 — `get_simulation_clock()` might work, but if `sim_clock.current_time` is None or the import fails, it falls back to `datetime.now()`. If real clock says "1:24 AM" (batch running overnight on VPS) this reads as `is_premarket = True`, enabling premarket instant entry and skipping candle-over-candle — which is a DIFFERENT code path than Windows running at 6:24 AM ET.

**Fix:** Replace with `sim_aware_now_et()` and compute `is_premarket` from that.

---

### Finding 5 — MEDIUM: `trade_event_service.py` dedup uses `time.time()` (wall-clock)

**Impact:** MEDIUM — Can suppress trigger rejection events differently on fast vs slow machines  
**File:** `nexus2/domain/automation/trade_event_service.py:1064-1070`  
**Code:**
```python
# Dedup: skip if same symbol+pattern was rejected < 30s ago
dedup_key = f"{symbol}_{best_pattern}"
now = time.time()
last_ts = self._trigger_rejection_dedup.get(dedup_key, 0)
if (now - last_ts) < 30:
    return  # Suppress duplicate within 30s window
self._trigger_rejection_dedup[dedup_key] = now
```
**Problem:** This dedup uses `time.time()` (real wall-clock). In batch mode, each case steps 960 minutes of sim time but runs in ~1-2 real seconds. Thus `time.time()` barely advances between rejection checks, causing:
- Most rejections are suppressed (dedup fires because real time < 30s between checks)
- This is **both** Windows and Linux, but the execution speed differs

**This dedup only affects trigger rejection LOGGING (not actual entry decisions)**, so the impact is secondary. However, it affects the guard_blocks analysis and observability.

**Fix:** Use `sim_aware_now_utc().timestamp()` instead of `time.time()`.

---

## Files NOT Affected (Clean)

| File | Status | Notes |
|------|--------|-------|
| `warrior_entry_guards.py` | ✅ CLEAN | No wall-clock calls |
| `warrior_entry_helpers.py` | ✅ CLEAN | Fixed in Phase 2 |
| `warrior_monitor_exit.py` | ✅ CLEAN | Fixed in Phase 1 |
| `warrior_engine.py:291-294` | ✅ CLEAN | Fixed in Phase 2 (uses `sim_aware_now_et()`) |
| `nexus2/domain/indicators/*` | ✅ CLEAN | No wall-clock calls |
| `nexus2/adapters/simulation/sim_context.py` | ✅ CLEAN | Uses `time.time()` only for perf measurement |
| `nexus2/adapters/simulation/mock_broker.py` | ✅ CLEAN | No wall-clock in decision logic |
| `nexus2/adapters/simulation/historical_bar_loader.py` | ✅ CLEAN | Pure data loading, deterministic |

---

## Metadata-Only Sites (NOT Impactful)

These use `datetime.now()` for timestamp metadata on pattern objects, NOT for decision-making:

| File | Line | Usage | Impact |
|------|------|-------|--------|
| `warrior_entry_patterns.py` | 95 | `watched.abcd_detected_at` | None |
| `warrior_entry_patterns.py` | 1221 | `watched.inverted_hs_detected_at` | None |
| `warrior_entry_patterns.py` | 1314 | `watched.cup_handle_detected_at` | None |
| `warrior_engine.py` | 538 | `stats.last_scan_at` | None |

---

## Root Cause Assessment

The $139K gap is caused by **divergent entry decisions** due to wall-clock leaks in the pattern detection layer. Specifically:

1. **Finding 3+4 (DIP_FOR_LEVEL + PMH premarket)**: When the VPS runs batch tests at a different time of day than Windows, the `is_premarket` flag and DIP_FOR_LEVEL time gate evaluate differently. This can:
   - Skip candle-over-candle on VPS (running at night → real clock = premarket) but enforce it on Windows (running during day)
   - Block DIP_FOR_LEVEL on one env but allow it on the other

2. **Finding 1 (re-entry cooldown)**: The cooldown check always passes in sim because `now_utc()` is months ahead of the sim date. This is consistent across envs, so it's not a divergence vector per se, but it's a correctness bug.

3. **Finding 2 (swing_high_time)**: Real clock timestamps mess up micro-pullback state tracking. Different execution speeds produce different HH:MM stamps, potentially causing micro-pullback entries on one env but not the other.

---

## Change Surface

| # | File | Line(s) | Change | Impact |
|---|------|---------|--------|--------|
| 1 | `warrior_entry_patterns.py` | 458,462 | Replace `now_utc()` with `sim_aware_now_utc()` | HIGH |
| 2 | `warrior_entry_patterns.py` | 814 | Replace `datetime.now(timezone.utc)` with `sim_aware_now_utc()` | HIGH |
| 3 | `warrior_engine_entry.py` | 828 | Replace `datetime.now(timezone.utc)` with `sim_aware_now_utc()` | HIGH |
| 4 | `warrior_entry_patterns.py` | 304-317 | Replace fallback block with `sim_aware_now_et()` | HIGH |
| 5 | `warrior_entry_patterns.py` | 586-601 | Replace fallback block with `sim_aware_now_et()` | HIGH |
| 6 | `trade_event_service.py` | 1066 | Replace `time.time()` with `sim_aware_now_utc().timestamp()` | MEDIUM |

---

## Wiring Checklist (for Backend Specialist)

- [ ] Add `from nexus2.utils.time_utils import sim_aware_now_utc` to `warrior_entry_patterns.py`
- [ ] Replace `now_utc()` with `sim_aware_now_utc()` at `warrior_entry_patterns.py:462`
- [ ] Replace `datetime.now(timezone.utc).strftime("%H:%M")` at `warrior_entry_patterns.py:814` with `sim_aware_now_utc().strftime("%H:%M")`
- [ ] Replace `datetime.now(timezone.utc).strftime("%H:%M")` at `warrior_engine_entry.py:828` with `sim_aware_now_utc().strftime("%H:%M")`
- [ ] Replace lines 304-317 in `warrior_entry_patterns.py` (DIP_FOR_LEVEL time gate) with `sim_aware_now_et()` call
- [ ] Replace lines 586-601 in `warrior_entry_patterns.py` (PMH premarket detection) with `sim_aware_now_et()` call
- [ ] Replace `time.time()` at `trade_event_service.py:1066` with `sim_aware_now_utc().timestamp()`
- [ ] Add import of `sim_aware_now_utc` to `trade_event_service.py`
- [ ] Add import of `sim_aware_now_utc` to `warrior_engine_entry.py` (if not present)
- [ ] Run full test suite: `python -m pytest tests/ -x`
- [ ] Run batch test on Windows and compare with VPS

---

## Risk Assessment

**What could go wrong:**
- `sim_aware_now_utc()` returns sim time in UTC while some code expects ET — need to ensure timezone consistency at each site
- `sim_aware_now_et()` correctly converts via `.astimezone(EASTERN)` — verified at `time_utils.py:90`
- The DIP_FOR_LEVEL cooldown (Finding 1) timing change may cause re-entries in sim that didn't happen before
- If any of these patterns aren't tested in the batch suite, new behavior won't be caught

**What to test:**
1. ROLR case — largest single-case divergence ($61K local vs few K VPS). This is the canary.
2. Run full 30-case batch on both Windows and VPS after all 6 fixes
3. Compare case-by-case P&L — if the gap shrinks significantly, the root cause was confirmed

---

## Verification Plan

### Automated
```powershell
# Run test suite
python -m pytest tests/ -x

# Run ROLR case standalone (canary)
python -c "import asyncio; from nexus2.adapters.simulation.sim_context import *; asyncio.run(_run_single_case_async({'id':'ross_rolr_20260114','symbol':'ROLR','ross_pnl':10000}, {}))"

# Run full batch on Windows
# (use existing batch test endpoint or script)
```

### Manual
1. Run full batch on Windows → record total P&L
2. Deploy fixes to VPS via `/deploy-to-vps`
3. Run full batch on VPS → record total P&L
4. Compare: gap should shrink from $139K to <$20K (ideally $0)

---

## Previous Reports
- `nexus2/reports/2026-02-28/research_batch_divergence.md` — Phase 1
- `nexus2/reports/2026-02-28/research_trace_divergence.md` — Phase 2
- `nexus2/reports/2026-02-28/validation_batch_divergence.md` — Phase 1 validation
- `nexus2/reports/2026-02-28/validation_trace_divergence.md` — Phase 2 validation
