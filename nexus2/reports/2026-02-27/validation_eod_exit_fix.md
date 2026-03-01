# Validation Report: EoD Exit Fix

**Date**: 2026-02-27  
**Validator**: Audit Validator  
**Reference**: `backend_status_eod_exit_fix.md`

---

## Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | Entry at 7:05 PM returns `(False, "EoD entry cutoff...")` | **PASS** | See Claim 1 below |
| 2 | Progressive spread gate blocks 2.5% spread at 5 PM | **PASS** | See Claim 2 below |
| 3 | Progressive spread gate blocks 1.5% spread at 6:30 PM | **PASS** | See Claim 3 below |
| 4 | Monitor loop continues when positions held outside extended hours | **PASS** | See Claim 4 below |
| 5 | `_check_after_hours_exit` fires at 7:30 PM (existing logic unchanged) | **PASS** | See Claim 5 below |
| 6 | All 844 existing tests pass | **PASS** | See Claim 6 below |
| 7 | `eod_entry_cutoff_time` setting exists with default "19:00" | **PASS** | See Claim 7 below |

---

## Detailed Evidence

### Claim 1: Entry cutoff guard blocks entries after 7 PM ET

**Claim:** Entry at 7:05 PM returns `(False, "EoD entry cutoff...")` at `warrior_entry_guards.py:78-81`  
**Verification Command:** `Select-String "EoD entry cutoff" C:\Dev\Nexus\nexus2\domain\automation\warrior_entry_guards.py`  
**Actual Output:**
```
warrior_entry_guards.py:79: reason = f"EoD entry cutoff: {current_time.strftime('%H:%M')} past {engine.monitor.settings.eod_entry_cutoff_time} ET"
```
**Code at lines 67-83** (verified via `view_file`):
```python
# EOD ENTRY CUTOFF — block ALL new entries past cutoff time (Feb 27 fix)
# This guard is NON-SKIPPABLE even in A/B test mode (safety critical)
current_time = et_now.time() if et_now else None
if current_time is not None:
    # Hard cutoff: no entries after eod_entry_cutoff_time (default 7 PM ET)
    try:
        h, m = map(int, engine.monitor.settings.eod_entry_cutoff_time.split(":"))
        from datetime import time as dt_time
        cutoff = dt_time(h, m)
        if current_time >= cutoff:
            reason = f"EoD entry cutoff: {current_time.strftime('%H:%M')} past {engine.monitor.settings.eod_entry_cutoff_time} ET"
            tml.log_warrior_guard_block(symbol, "eod_cutoff", reason, _trigger, _price, _btime)
            return False, reason
    except (ValueError, AttributeError) as e:
        logger.warning(f"[Warrior Guards] Failed to parse eod_entry_cutoff_time: {e}")
```
**Notes:** Guard is placed as FIRST guard at line 67, before the `skip_guards` A/B test bypass at line 85. This means the EoD cutoff is non-skippable even in A/B mode — confirmed. Logic correctly returns `(False, "EoD entry cutoff: ...")` when `current_time >= cutoff`.  
**Result:** PASS

---

### Claim 2: Progressive spread gate blocks 2.5% spread at 5 PM

**Claim:** Progressive spread gate blocks 2.5% spread at 5 PM at `warrior_entry_guards.py:374-380`  
**Verification Command:** `Select-String "EoD spread gate" C:\Dev\Nexus\nexus2\domain\automation\warrior_entry_guards.py`  
**Actual Output:**
```
warrior_entry_guards.py:384: f"EoD spread gate ({phase_label}): spread {spread_percent:.1f}% > "
```
**Code at lines 363-387** (verified via `view_file`):
```python
# Progressive EoD spread gates (Feb 27 fix)
try:
    from datetime import time as dt_time
    et_now = engine._get_eastern_time()
    current_time = et_now.time() if et_now else None
    if current_time is not None:
        phase2_start = dt_time(18, 0)  # 6 PM
        phase1_start = dt_time(16, 0)  # 4 PM
        
        eod_limit = None
        phase_label = ""
        if current_time >= phase2_start:
            eod_limit = engine.monitor.settings.eod_phase2_max_spread_pct
            phase_label = "phase2 (6-7 PM)"
        elif current_time >= phase1_start:
            eod_limit = engine.monitor.settings.eod_phase1_max_spread_pct
            phase_label = "phase1 (4-6 PM)"
        
        if eod_limit is not None and spread_percent > eod_limit:
            reason = (
                f"EoD spread gate ({phase_label}): spread {spread_percent:.1f}% > "
                f"max {eod_limit}% (bid=${bid:.2f}, ask=${ask:.2f})"
            )
            return False, reason, None
```
**Notes:** At 5 PM, `current_time >= phase1_start (16:00)` is true and `current_time >= phase2_start (18:00)` is false, so `eod_limit = eod_phase1_max_spread_pct` (default 2.0%). A 2.5% spread > 2.0% → blocked. Correct.  
**Result:** PASS

---

### Claim 3: Progressive spread gate blocks 1.5% spread at 6:30 PM

**Claim:** Progressive spread gate blocks 1.5% spread at 6:30 PM at `warrior_entry_guards.py:374-380`  
**Verification Command:** `Select-String "eod_phase2_max_spread_pct" C:\Dev\Nexus\nexus2\domain\automation\warrior_entry_guards.py`  
**Actual Output:**
```
warrior_entry_guards.py:376: eod_limit = engine.monitor.settings.eod_phase2_max_spread_pct
```
**Notes:** At 6:30 PM, `current_time >= phase2_start (18:00)` is true, so `eod_limit = eod_phase2_max_spread_pct` (default 1.0%). A 1.5% spread > 1.0% → blocked. Correct.  
**Result:** PASS

---

### Claim 4: Monitor loop continues when positions held outside extended hours

**Claim:** Monitor loop continues when `self._positions` is non-empty at `warrior_monitor.py:525-531`  
**Verification Command:** `Select-String "continuing monitor for after-hours exit" C:\Dev\Nexus\nexus2\domain\automation\warrior_monitor.py`  
**Actual Output:**
```
warrior_monitor.py:530: f"continuing monitor for after-hours exit checks"
```
**Code at lines 519-538** (verified via `view_file`):
```python
# CRITICAL FIX (Feb 27): If we HAVE positions, keep ticking even outside
# extended hours — the after-hours exit logic NEEDS the monitor to be running
# to force-exit before overnight. Stopping the monitor too early = overnight holds.
if not self.sim_mode:
    from nexus2.adapters.market_data.market_calendar import get_market_calendar
    calendar = get_market_calendar(paper=True)
    if not calendar.is_extended_hours_active():
        if self._positions:
            # KEEP TICKING — we have positions that need after-hours exit checks
            logger.info(
                f"[Warrior Monitor] Market closed but {len(self._positions)} position(s) held — "
                f"continuing monitor for after-hours exit checks"
            )
        else:
            # ...sleep and continue (skip position checks)
            await asyncio.sleep(60)
            continue
```
**Notes:** When `is_extended_hours_active()` returns False AND `self._positions` is non-empty, the loop logs a warning and falls through to `_check_all_positions()` at line 540 instead of `continue`-ing. This ensures `_check_after_hours_exit()` can fire. Only the empty-positions branch sleeps and continues.  
**Result:** PASS

---

### Claim 5: `_check_after_hours_exit` fires at 7:30 PM (existing logic unchanged)

**Claim:** `_check_after_hours_exit` uses `force_exit_time_et` at `warrior_monitor_exit.py:226`  
**Verification Command:** `Select-String "force_exit_time_et" C:\Dev\Nexus\nexus2\domain\automation\warrior_monitor_exit.py`  
**Actual Output:**
```
warrior_monitor_exit.py:226: if current_time_str >= s.force_exit_time_et:
warrior_monitor_exit.py:230: force_hour, force_min = map(int, s.force_exit_time_et.split(":"))
warrior_monitor_exit.py:240: f"(offset={exit_offset*100:.0f}%, {minutes_since_force:.1f}min since {s.force_exit_time_et} ET)"
warrior_monitor_exit.py:251: trigger_description=f"Force exit at {s.force_exit_time_et} ET (offset={exit_offset*100:.0f}%)",
```
**Code at line 226** (verified via `view_file`):
```python
if current_time_str >= s.force_exit_time_et:
```
**Notes:** Default `force_exit_time_et` is `"19:30"` (confirmed at `warrior_types.py:92`). Logic is unchanged — compares `HH:MM` string against setting and generates `AFTER_HOURS_EXIT` signal with escalating offset.  
**Result:** PASS

---

### Claim 6: All 844 existing tests pass

**Claim:** `pytest` full suite passes with 844 tests  
**Verification Command:** `cd nexus2; python -m pytest tests/ -q --tb=short`  
**Actual Output:** (provided by user after command timeout)
```
844 passed, 4 skipped, 3 deselected in 135.02s (0:02:15)
```
**Notes:** 844 passed matches claim exactly. 4 skipped and 3 deselected are pre-existing, not new failures. 0 failures.  
**Result:** PASS

---

### Claim 7: `eod_entry_cutoff_time` setting exists with default "19:00"

**Claim:** `eod_entry_cutoff_time` setting at `warrior_types.py:96` with default `"19:00"`  
**Verification Command:** `Select-String "eod_entry_cutoff_time" C:\Dev\Nexus\nexus2\domain\automation\warrior_types.py`  
**Actual Output:**
```
warrior_types.py:96: eod_entry_cutoff_time: str = "19:00"  # Block ALL new entries after 7 PM ET
```
**Code at lines 94-98** (verified via `view_file`):
```python
# EoD Entry Cutoff & Progressive Spread Gates (Feb 27 fix)
# Prevents new entries in late post-market; tightens spread requirements after hours
eod_entry_cutoff_time: str = "19:00"  # Block ALL new entries after 7 PM ET
eod_phase1_max_spread_pct: float = 2.0  # Post-market (4-6 PM): max 2% spread
eod_phase2_max_spread_pct: float = 1.0  # Late post-market (6-7 PM): max 1% spread
```
**Notes:** All three new settings confirmed at lines 96-98 with correct defaults: `"19:00"`, `2.0`, `1.0`. These are on `WarriorMonitorSettings` dataclass.  
**Result:** PASS

---

## Overall Rating

**HIGH** — All 7 claims verified, clean work. Code is at the claimed line numbers, logic matches described behavior, settings have correct defaults, and all 844 tests pass with 0 failures.
