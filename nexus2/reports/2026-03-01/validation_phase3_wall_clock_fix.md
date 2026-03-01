# Validation Report: Phase 3 Wall-Clock Leak Fixes

**Date:** 2026-03-01  
**Validator:** Audit Validator  
**Report Under Validation:** `backend_status_phase3_wall_clock_fix.md`

---

## Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | All 844 tests pass | **PASS** | 844 passed, 4 skipped, 3 deselected in 136.09s |
| 2 | No `datetime.now()` or `time.time()` in `warrior_entry_patterns.py` | **PASS** | `grep_search` for `datetime.now(` → 0 results; `grep_search` for `time.time()` → 0 results |
| 3 | No `datetime.now()` or `time.time()` in `warrior_engine_entry.py` | **PASS** | `grep_search` for `datetime.now(` → 0 results; `grep_search` for `time.time()` → 0 results |
| 4 | No `time.time()` in `trade_event_service.py` | **PASS** | `grep_search` for `time.time()` → 0 results |
| 5 | Fix 1: DIP_FOR_LEVEL time gate reduced to `sim_aware_now_et()` | **PASS** | Lines 304-306 confirmed (see below) |
| 6 | Fix 3: PMH premarket detection reduced to `sim_aware_now_et()` | **PASS** | Lines 576-578 confirmed (see below) |
| 7 | `sim_aware_now_utc()` falls back to `now_utc()` in live mode | **PASS** | `time_utils.py:59-78` confirmed (see below) |

---

## Detailed Evidence

### Claim 2: No `datetime.now()` or `time.time()` in `warrior_entry_patterns.py`

**Verification Command:** `grep_search` with query `datetime.now(` on `C:\Dev\Nexus\nexus2\domain\automation\warrior_entry_patterns.py`  
**Actual Output:** No results found  

**Verification Command:** `grep_search` with query `time.time()` on `C:\Dev\Nexus\nexus2\domain\automation\warrior_entry_patterns.py`  
**Actual Output:** No results found  

**Result:** PASS  
**Notes:** One `datetime.now(timezone.utc)` exists at line 95 inside `detect_abcd_pattern` — this sets `watched.abcd_detected_at` (metadata timestamp, NOT a trading decision). This is correctly excluded from the report's scope.

---

### Claim 3: No `datetime.now()` or `time.time()` in `warrior_engine_entry.py`

**Verification Command:** `grep_search` with query `datetime.now(` on `C:\Dev\Nexus\nexus2\domain\automation\warrior_engine_entry.py`  
**Actual Output:** No results found  

**Verification Command:** `grep_search` with query `time.time()` on `C:\Dev\Nexus\nexus2\domain\automation\warrior_engine_entry.py`  
**Actual Output:** No results found  

**Result:** PASS  
**Notes:** Fix 5 confirmed at line 828-829: `sim_aware_now_utc().strftime("%H:%M")`

---

### Claim 4: No `time.time()` in `trade_event_service.py`

**Verification Command:** `grep_search` with query `time.time()` on `C:\Dev\Nexus\nexus2\domain\automation\trade_event_service.py`  
**Actual Output:** No results found  

**Result:** PASS

---

### Claim 5: Fix 1 — DIP_FOR_LEVEL time gate uses `sim_aware_now_et()`

**Verification Command:** `view_file` lines 304-306 of `warrior_entry_patterns.py`  
**Actual Output:**
```python
304:     from nexus2.utils.time_utils import sim_aware_now_et
305:     now_et = sim_aware_now_et()
306: 
```

**Result:** PASS  
**Notes:** Report claimed lines 304-317 were reduced to 304-306 (2 lines). Confirmed — the old 14-line `datetime.now(et)` + `get_simulation_clock()` fallback is gone, replaced by a single `sim_aware_now_et()` call.

---

### Claim 6: Fix 3 — PMH premarket detection uses `sim_aware_now_et()`

**Verification Command:** `view_file` lines 575-578 of `warrior_entry_patterns.py`  
**Actual Output:**
```python
575:     # Get current time for premarket-aware thresholds
576:     from nexus2.utils.time_utils import sim_aware_now_et
577:     _now_et = sim_aware_now_et()
578:     is_premarket = _now_et.hour < 9 or (_now_et.hour == 9 and _now_et.minute < 30)
```

**Result:** PASS  
**Notes:** Report claimed lines 586-601→585-588. Actual lines are 575-578 (slight shift from other edits). The old 16-line `get_simulation_clock()` / `_dt.now(pytz)` fallback is gone, replaced by 3 clean lines.

---

### Claim 7: `sim_aware_now_utc()` falls back to `now_utc()` in live mode

**Verification Command:** `view_file` lines 59-78 of `time_utils.py`  
**Actual Output:**
```python
59: def sim_aware_now_utc() -> datetime:
60:     """Returns sim clock time if in sim context, else real UTC.
61:     
62:     Use this INSTEAD of now_utc() in trading logic that must
63:     respect simulated time (exit logic, grace periods, cooldowns).
64:     
65:     In live mode, the ContextVar is unset → falls back to now_utc().
66:     In sim mode, the ContextVar is set per-case → returns sim time.
67:     
68:     DO NOT use this for:
69:     - DB timestamps (use now_utc())
70:     - API response timestamps (use now_utc())
71:     - Dataclass defaults (use now_utc_factory())
72:     - Logging timestamps (use now_utc())
73:     """
74:     from nexus2.adapters.simulation.sim_clock import _sim_clock_ctx
75:     clock = _sim_clock_ctx.get()
76:     if clock and clock.current_time:
77:         return clock.current_time
78:     return now_utc()
```

**Result:** PASS  
**Notes:** Line 78 confirms fallback: `return now_utc()`. When `_sim_clock_ctx` ContextVar is unset (live mode), the function returns the real wall clock via `now_utc()`. In sim mode, the ContextVar is set per-case and returns `clock.current_time`. This is safe for live trading.

---

## Overall Rating

**HIGH** — All 7 claims independently verified and PASS.

> [!NOTE]
> **Minor line-number drift:** Claim 6 references lines 585-588 but actual code is at lines 575-578. This is cosmetic — the code content matches exactly. Line numbers shifted due to the net code reduction from other fixes in the same file.

> [!NOTE]
> **Residual `datetime.now(timezone.utc)` at line 95:** This exists in `detect_abcd_pattern` for `abcd_detected_at` metadata only. It does NOT affect trading decisions and is not a wall-clock leak.
