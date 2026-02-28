# Backend Status: EoD Exit Bug Fix

**Date**: 2026-02-27
**Agent**: Backend Specialist
**Tests**: 844 passed, 0 failed

---

## Root Causes Identified

### Bug 1: CD entered at 7:35 PM (past trading_window_end)
**Root Cause**: `trading_window_end` was ONLY checked in `is_trading_window()` (`warrior_engine.py:299`) which is used exclusively for status display (`warrior_engine.py:820`). There was **zero per-entry time check** in `check_entry_guards()`. The `_watch_loop` only checks `is_extended_hours_active()` which is true until 8 PM — so entries were allowed until 8 PM.

**File**: `warrior_entry_guards.py` — no time check existed in `check_entry_guards()`
**Verified with**: `Select-String "is_trading_window" warrior_engine_entry.py` → 0 matches

### Bug 2: CDIO held overnight (force_exit didn't fire)
**Root Cause**: `_monitor_loop` (`warrior_monitor.py:519-528`) skipped ALL position checks when `is_extended_hours_active()` returned False (at 8 PM). This meant `_check_after_hours_exit()` with `force_exit_time_et=19:30` could never fire if the force-exit didn't complete by 8 PM — the monitor loop itself stopped ticking.

**File**: `warrior_monitor.py:522` — `if not calendar.is_extended_hours_active(): continue`
**Verified with**: `view_file` showing the unconditional `continue` at line 528

---

## Changes Made

### 1. Entry Cutoff Guard — `warrior_entry_guards.py`
**Lines 67-83**: Added EoD entry cutoff as FIRST guard in `check_entry_guards()` (non-skippable, even in A/B test mode). Blocks ALL new entries after `eod_entry_cutoff_time` (default 7:00 PM ET).

### 2. Progressive Spread Gates — `warrior_entry_guards.py`
**Lines 357-385** (inside `_check_spread_filter`): After normal spread check passes, applies tighter spread limits based on time of day:
- Phase 1 (4-6 PM): max `eod_phase1_max_spread_pct` (default 2%)
- Phase 2 (6-7 PM): max `eod_phase2_max_spread_pct` (default 1%)

### 3. Monitor Loop Fix — `warrior_monitor.py`
**Lines 519-538**: Monitor loop now keeps ticking when `self._positions` is non-empty, even if `is_extended_hours_active()` returns False. Logs a warning and continues checking positions so `_check_after_hours_exit()` can fire.

### 4. New Settings — `warrior_types.py`
**Lines 94-98**: Three new fields on `WarriorMonitorSettings`:
- `eod_entry_cutoff_time: str = "19:00"` — Hard cutoff for new entries
- `eod_phase1_max_spread_pct: float = 2.0` — Post-market spread gate
- `eod_phase2_max_spread_pct: float = 1.0` — Late post-market spread gate

---

## Testable Claims

| # | Claim | File:Line | Grep Pattern |
|---|-------|-----------|-------------|
| 1 | Entry at 7:05 PM returns `(False, "EoD entry cutoff...")` | `warrior_entry_guards.py:78-81` | `EoD entry cutoff` |
| 2 | Progressive spread gate blocks 2.5% spread at 5 PM | `warrior_entry_guards.py:374-380` | `EoD spread gate` |
| 3 | Progressive spread gate blocks 1.5% spread at 6:30 PM | `warrior_entry_guards.py:374-380` | `eod_phase2_max_spread_pct` |
| 4 | Monitor loop continues when positions held outside extended hours | `warrior_monitor.py:525-531` | `continuing monitor for after-hours exit` |
| 5 | `_check_after_hours_exit` fires at 7:30 PM (existing logic unchanged) | `warrior_monitor_exit.py:226` | `force_exit_time_et` |
| 6 | All 844 existing tests pass | — | `pytest` full suite |
| 7 | `eod_entry_cutoff_time` setting exists with default "19:00" | `warrior_types.py:96` | `eod_entry_cutoff_time` |
