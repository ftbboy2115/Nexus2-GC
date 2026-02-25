# Validation Report: 10s Bar Pipeline Fix

**Validator:** Testing Specialist
**Date:** 2026-02-25
**Reference:** `nexus2/reports/2026-02-25/backend_status_10s_pipeline_fix.md`

---

## Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | `get_bars_up_to` handles `"10s"` timeframe | **PASS** | `Select-String -Path "nexus2\adapters\simulation\historical_bar_loader.py" -Pattern 'elif timeframe == "10s"' -SimpleMatch` → `historical_bar_loader.py:441: elif timeframe == "10s":` |
| 2 | `get_bars_up_to` falls back to 1min when no 10s data | **PASS** | `Select-String -Path "nexus2\adapters\simulation\historical_bar_loader.py" -Pattern "falling back to 1min"` → `historical_bar_loader.py:446: ...No 10s bars for {symbol}, falling back to 1min` |
| 3 | `sim_get_intraday_bars` checks `has_10s_bars` | **PASS** | `Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "has_10s_bars"` → 4 matches including `sim_context.py:396: if _loader.has_10s_bars(symbol):` |
| 4 | `sim_get_intraday_bars` applies limit to 10s results | **PASS** | `Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "bars\[-limit:\]"` → `sim_context.py:401: bars = bars[-limit:]` |
| 5 | `check_micro_pullback_entry` uses `entry_bar_timeframe` | **PASS** | `Select-String` shows match at line 733. Verified via `view_file` L728-740: `tf = engine.config.entry_bar_timeframe` inside `check_micro_pullback_entry`, with `bar_limit = 180 if tf == "10s" else 30` and `min_candles = 120 if tf == "10s" else 20` |
| 6 | `detect_pullback_pattern` uses `entry_bar_timeframe` | **PASS** | `Select-String` shows match at line 898. Verified via `view_file` L893-905: `tf = engine.config.entry_bar_timeframe` inside `detect_pullback_pattern`, with `bar_limit = 180 if tf == "10s" else 30` |
| 7 | `detect_vwap_break_pattern` uses `entry_bar_timeframe` | **PASS** | `Select-String` shows match at line 1094. Verified via `view_file` L1085-1100: `tf = engine.config.entry_bar_timeframe` inside `detect_vwap_break_pattern`, with `bar_limit = min(bar_limit * 6, 6000)` for 10s |
| 8 | Pytest passes (757 passed, 4 skipped, 3 deselected) | **PASS** | `python -m pytest nexus2/tests/ -x -q --tb=line` → `757 passed, 4 skipped, 3 deselected in 118.82s` — exact match |

---

## Additional Observations

- **6 total `entry_bar_timeframe` references** found in `warrior_entry_patterns.py` (lines 398, 421, 605, 733, 898, 1094). The status report claimed "6+ matches (was 3)" — confirmed exactly 6.
- Lines 398/421 are in `detect_dip_for_level_pattern`, line 605 is in `detect_pmh_break` — these appear to be pre-existing or additional 10s-aware updates beyond the 3 claimed patterns.
- All 10s scaling factors look reasonable: `bar_limit * 6` (6 bars/min × minutes), `min_candles` scaled 6x, capped at 6000 for VWAP break.

---

## Overall Rating: **HIGH**

All 8 claims verified. Pytest count is an exact match. Code changes are present at the claimed locations with correct function contexts.
