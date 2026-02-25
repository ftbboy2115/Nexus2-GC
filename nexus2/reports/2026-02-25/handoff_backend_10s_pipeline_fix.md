# Handoff: Fix 10s Bar Pipeline + Pattern Timeframe Support

**Agent:** Backend Specialist
**Priority:** P1 — patterns can't detect setups due to broken data pipeline
**Date:** 2026-02-25
**Reference:** `nexus2/reports/2026-02-25/spec_10s_data_fidelity.md`

---

## Problem

The sim pipeline has a broken link preventing 10s bar data from reaching pattern detection:
1. `sim_get_intraday_bars` passes `"10s"` to `get_bars_up_to()`, which only handles `"1min"`/`"5min"` and silently falls through to 1min
2. All 5 alternative entry patterns hardcode `"1min"` instead of using `engine.config.entry_bar_timeframe`

## Verified Facts (from Backend Planner spec)

**1. Broken `get_bars_up_to()`:**
- File: `nexus2/adapters/simulation/historical_bar_loader.py:420-442`
- Code: `if timeframe == "5min": ... else: return data.get_bars_up_to(...)` ← always returns 1min
- 10s data exists in `IntradayData.bars_10s` but is never accessed by this method

**2. `sim_get_intraday_bars` passes timeframe through blindly:**
- File: `nexus2/adapters/simulation/sim_context.py:384-407`
- Code: `bars = _loader.get_bars_up_to(symbol, time_str, timeframe, ...)`

**3. Five patterns hardcode `"1min"`:**
- `check_micro_pullback_entry` at `warrior_entry_patterns.py:733`
- `detect_pullback_pattern` at `warrior_entry_patterns.py:849+`
- `detect_vwap_break_pattern` at `warrior_entry_patterns.py:1089`
- `detect_abcd_pattern` at `warrior_entry_patterns.py:75`
- `detect_whole_half_anticipatory` at `warrior_entry_patterns.py:196`

## Tasks

### Task 1: Fix `get_bars_up_to()` to handle `"10s"` timeframe
- Add a `"10s"` branch in `historical_bar_loader.py:get_bars_up_to()` 
- Should call the `IntradayData`'s 10s bar retrieval method
- When 10s data unavailable, fall back to 1min (don't break existing cases)

### Task 2: Fix `sim_get_intraday_bars` callback
- In `sim_context.py:384-407`, add explicit 10s handling
- Check `_loader.has_10s_bars(symbol)` before requesting 10s data
- Apply `limit` to 10s bar results

### Task 3: Update 3 HIGH/MEDIUM impact patterns to use `entry_bar_timeframe`
- **micro_pullback** (HIGH impact) — `warrior_entry_patterns.py:733`
- **pullback** (MEDIUM) — `warrior_entry_patterns.py:849+`
- **vwap_break** (MEDIUM) — `warrior_entry_patterns.py:1089`

For each pattern:
- Replace hardcoded `"1min"` with `engine.config.entry_bar_timeframe`
- Adjust limit/threshold scaling if needed (10s needs ~6x more bars for same time window)
- Add fallback: if 10s bars unavailable, use 1min

> [!WARNING]
> Do NOT update `detect_abcd_pattern` or `detect_whole_half_anticipatory` — these require 15-40 bars of structural pattern data and need separate threshold redesign.

> [!WARNING]
> Do NOT change `entry_bar_timeframe` default from `"1min"` to `"10s"` — only 3/35 cases have 10s data. That change comes after backfill.

## Output

- Write status to: `nexus2/reports/2026-02-25/backend_status_10s_pipeline_fix.md`
- Include testable claims
- Run pytest after changes
