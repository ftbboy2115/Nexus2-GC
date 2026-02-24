# Backend Status: Premarket Entry Fix

**Date**: 2026-02-23  
**Agent**: Backend Specialist (via Coordinator)  
**Priority**: P1 (~$312K estimated P&L gap)

---

## Changes Made

### [warrior_entry_patterns.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py)

Three time-aware changes for premarket entries (before 9:30 AM ET):

1. **`detect_pmh_break()` — Relaxed `check_active_market` thresholds**  
   Before 9:30 AM: `min_bars=3, min_volume_per_bar=500, max_time_gap_minutes=30`  
   After 9:30 AM: unchanged (original `min_bars=5/18, min_vol=1000/200, max_gap=15/5`)

2. **`detect_pmh_break()` — Skip candle-over-candle confirmation**  
   Before 9:30 AM: immediate entry on PMH break (sparse bars make 2nd-candle confirmation impractical)  
   After 9:30 AM: unchanged (still requires candle-over-candle)

3. **`detect_dip_for_level()` — Same relaxed thresholds**  
   Before 9:30 AM: same relaxed params as PMH break  
   After 9:30 AM: unchanged

### Investigation Step 0 Result
Changing `entry_bar_timeframe` from `"1min"` to `"10s"` would **NOT** work — `HistoricalBarLoader.get_bars_up_to()` doesn't handle `"10s"` timeframe (falls through to 1-min bars), and the 10s thresholds (`max_time_gap=5min`) on 1-min bars would be MORE restrictive.

---

## Batch Test Results

| Metric | Benchmark (Feb 21) | Post-Fix | Change |
|--------|-------------------:|----------:|--------:|
| Total P&L | $135,020.44 | $136,103.21 | +$1,083 |
| Delta | -$297,979.18 | -$296,896.41 | +$1,083 |
| Cases run | 35 | 35 | — |
| Cases profitable | 24 | 24 | — |
| Runtime | ~65s | 343s | regression |

**Impact: Negligible (~$1K, within run-to-run noise)**

---

## Why the Fix Had No Measurable Impact

### Problem 1: LATE_ENTRY Cases Not in Test Suite
The spec listed 11 LATE_ENTRY cases, but most use OLD format IDs (`bnai_2026_01_23`, `bimi_2026_01_23`, etc.) that **don't exist** in the current test suite. Only `ross_gri_20260128` matched. The test suite has 35 cases, most from late Jan–Feb 2026 with `ross_*` naming.

### Problem 2: Trades Array Empty in Concurrent Runner (Pre-existing)
The concurrent batch runner's `warrior_db` extraction returns empty `trades: []` for all cases despite non-zero P&L (MockBroker calculates P&L independently). This means **entry times and triggers cannot be verified** from batch results. This is pre-existing and not caused by this fix.

### Problem 3: Other Gates May Block
Even with the active market gate relaxed, other gates still apply in premarket:
- **MACD gate** — with sparse premarket bars, MACD histogram may always be negative
- **EMA/VWAP gates** — insufficient data for meaningful calculation
- **Score threshold** — `compute_time_score()` penalizes premarket

---

## Recommendations

1. **Add the actual LATE_ENTRY test cases** — The 11 cases from the spec need to be added to `warrior_setups.yaml` with proper `ross_*` IDs and bar data
2. **Fix trades array extraction** in concurrent runner — investigate why `get_all_warrior_trades()` returns empty in per-process in-memory DB
3. **Run single-case debug** on one LATE_ENTRY case (e.g., GRI) with verbose logging to trace the exact gate that blocks premarket entry
4. **Consider MACD gate bypass** in premarket — with <10 bars, MACD is unreliable; may need to skip MACD gate before 9:30 AM

---

## Files Modified
- `nexus2/domain/automation/warrior_entry_patterns.py` — 3 changes (time-aware active market gate + skip candle confirmation in premarket)

## Verification Status
- [x] Syntax check passed
- [x] Server starts cleanly  
- [x] Full batch test runs without errors
- [ ] **INCONCLUSIVE** — Cannot verify premarket entry improvement due to missing test cases and empty trades array
