# Validation Report: Exit Clock Fix

**Validator:** Audit Validator  
**Date:** 2026-02-28  
**Source:** `backend_status_exit_clock_fix.md`  
**File Under Test:** `nexus2/domain/automation/warrior_monitor_exit.py`

---

## Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | `now_utc()` no longer called anywhere | **FAIL** | 3 matches remain (lines 48, 1505, 1534) |
| 2 | `datetime.now(` no longer called anywhere | **FAIL** | 3 matches remain (lines 222, 233, 537) |
| 3 | `_get_sim_aware_now_utc` exists with 4 matches (1 def + 3 calls) | **PASS** | 4 matches: def at L34, calls at L302, L478, L633 |
| 4 | 5m bucket uses `monitor._sim_clock` pattern | **PASS** | 4 matches at L43, L208, L534, L1509 |
| 5 | `_check_after_hours_exit` unchanged, log string present | **PASS** | `"Using monitor._sim_clock"` at L212 |
| 6 | All 844 tests pass | **PASS** | `844 passed, 4 skipped, 3 deselected` in 127.98s |

---

## Detailed Evidence

### Claim 1 — FAIL: `now_utc()` still present

**Verification Command:**
```powershell
Select-String -Path "nexus2\domain\automation\warrior_monitor_exit.py" -Pattern "now_utc\(\)"
```

**Actual Output:**
```
warrior_monitor_exit.py:48:    return now_utc()
warrior_monitor_exit.py:1505:  monitor._recently_exited[signal.symbol] = now_utc()
warrior_monitor_exit.py:1534:  exit_time=now_utc(),
```

**Notes:** Line 48 is the intentional fallback inside the new `_get_sim_aware_now_utc` helper (expected). Lines 1505 and 1534 are in `_execute_exit_signal` for exit timestamp tracking — these were NOT among the 4 targeted leakage sites (spread grace, candle grace, 5m bucket, topping tail grace) but the claim said "anywhere." The claim is overly broad.

> [!WARNING]
> Lines 1505 and 1534 may themselves be clock leakage in batch sim — `_recently_exited` timestamps and `exit_time` callbacks will use wall clock instead of sim clock during replay. This could affect re-entry cooldown logic.

---

### Claim 2 — FAIL: `datetime.now(` still present

**Verification Command:**
```powershell
Select-String -Path "nexus2\domain\automation\warrior_monitor_exit.py" -Pattern "datetime\.now\("
```

**Actual Output:**
```
warrior_monitor_exit.py:222:  real_now = datetime.now(ET)
warrior_monitor_exit.py:233:  et_now = datetime.now(ET)
warrior_monitor_exit.py:537:  et_now = datetime.now(ZoneInfo("America/New_York"))
```

**Notes:** Lines 222 and 233 are in `_check_after_hours_exit` which was deliberately left unchanged per claim 5 — these are fallback paths when no sim clock is available. Line 537 is the else-branch fallback in the 5m candle bucket (live trading path). All three are intentional fallbacks guarded by `_sim_clock` checks. The claim is overly broad — it should have said "no unguarded `datetime.now()` calls" rather than "no longer called anywhere."

---

### Claim 3 — PASS: `_get_sim_aware_now_utc` exists with 4 matches

**Verification Command:**
```powershell
Select-String -Path "nexus2\domain\automation\warrior_monitor_exit.py" -Pattern "_get_sim_aware_now_utc"
```

**Actual Output:**
```
warrior_monitor_exit.py:34:def _get_sim_aware_now_utc(monitor: "WarriorMonitor") -> datetime:
warrior_monitor_exit.py:302:    seconds_since_entry = (_get_sim_aware_now_utc(monitor) - entry_time).total_seconds()
warrior_monitor_exit.py:478:    seconds_since_entry = (_get_sim_aware_now_utc(monitor) - entry_time).total_seconds()
warrior_monitor_exit.py:633:    seconds_since_entry = (_get_sim_aware_now_utc(monitor) - entry_time).total_seconds()
```

**Notes:** Exactly 4 matches: 1 definition + 3 call sites (spread grace, candle-under-candle grace, topping tail grace). Matches claim exactly.

---

### Claim 4 — PASS: 5m bucket uses `_sim_clock` pattern

**Verification Command:**
```powershell
Select-String -Path "nexus2\domain\automation\warrior_monitor_exit.py" -Pattern "_sim_clock.*current_time"
```

**Actual Output:**
```
warrior_monitor_exit.py:43:   clock_time = monitor._sim_clock.current_time
warrior_monitor_exit.py:208:  clock_time = monitor._sim_clock.current_time
warrior_monitor_exit.py:534:  clock_time = monitor._sim_clock.current_time
warrior_monitor_exit.py:1509: sim_time = monitor._sim_clock.current_time
```

**Notes:** 4 matches — helper (L43), after-hours (L208), 5m bucket (L534), exit tracking (L1509). Report claimed "matches at helper + 5m bucket + after-hours" — all three present plus an additional match at L1509.

---

### Claim 5 — PASS: `_check_after_hours_exit` unchanged

**Verification Command:**
```powershell
view_file warrior_monitor_exit.py lines 206-214
```

**Actual Output (line 212):**
```python
logger.debug(f"[Warrior] Using monitor._sim_clock time {et_now.strftime('%H:%M')} for after-hours check")
```

**Notes:** The `"Using monitor._sim_clock"` log string is present at line 212, confirming `_check_after_hours_exit` retains its existing sim-clock logic.

---

### Claim 6 — PASS: All 844 tests pass

**Verification Command:**
```powershell
python -m pytest nexus2/tests/ -x -q
```

**Actual Output:**
```
844 passed, 4 skipped, 3 deselected in 127.98s (0:02:07)
```

**Notes:** Exact match with claimed test count. Zero failures.

---

## Quality Rating

**MEDIUM** — The core implementation is correct (claims 3-6 all pass), but claims 1-2 are overly broad assertions that fail on literal verification. The fixes do address the 4 targeted wall-clock leakage sites (spread grace, candle grace, 5m bucket, topping tail grace), but:

1. Two `now_utc()` calls in `_execute_exit_signal` (L1505, L1534) may be additional clock leakage affecting re-entry cooldown during batch replay
2. The `datetime.now()` fallbacks (L222, L233, L537) are intentional but should have been noted as "guarded fallbacks" rather than claiming complete removal

> [!IMPORTANT]
> **Potential remaining leakage at lines 1505 and 1534** — `_recently_exited` timestamps and `exit_time` callbacks use `now_utc()` during batch sim. If any downstream logic compares these against bar timestamps, cooldown/re-entry behavior could diverge between local and VPS runs.

---

## Recommendation

Report back to **Backend Specialist** to:
1. Correct claims 1-2 wording to reflect intentional fallbacks
2. Evaluate whether L1505/L1534 `now_utc()` calls need sim-clock treatment for batch replay fidelity
