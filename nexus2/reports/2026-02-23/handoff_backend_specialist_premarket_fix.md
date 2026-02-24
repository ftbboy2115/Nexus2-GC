# Backend Specialist Handoff: Premarket Entry Fix

## Context

Read the full root cause spec first: [spec_late_entry_root_cause.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-02-23/spec_late_entry_root_cause.md)

**TL;DR:** Bot enters 1-2h after Ross due to `check_active_market()` gate blocking premarket entries. 11 cases, ~$312K P&L gap.

## Critical Finding: 10s Bar Path Already Exists

The code already has TWO paths in `detect_pmh_break()` (warrior_entry_patterns.py L569-610):

| Timeframe | min_bars | min_vol/bar | max_gap | Time to pass |
|-----------|----------|-------------|---------|-------------|
| `1min` (DEFAULT) | 5 | 1,000 | 15 min | 5+ minutes |
| `10s` | 18 | 200 | 5 min | 3+ minutes |

The 10s path is MORE lenient (200 vol/bar vs 1000) but `entry_bar_timeframe` defaults to `"1min"` in `warrior_engine_types.py:144`.

**Investigation Step 0:** Before implementing Option A, check if simply changing the default to `"10s"` resolves premarket entries for the 11 LATE_ENTRY cases. If 10s bars exist in premarket Polygon data AND the 200 vol/bar threshold passes, this could be a one-line fix.

## Implementation Plan (if 10s alone doesn't solve it)

### Step 1: Time-Aware Thresholds in `check_active_market` Calls

**File:** `nexus2/domain/automation/warrior_entry_patterns.py`

In both `detect_pmh_break()` (L569-610) and `detect_dip_for_level()` (L388-435):
- Get the current sim/market time from the engine
- Before 9:30 AM ET, use relaxed params: `min_bars=3, min_volume_per_bar=500, max_time_gap_minutes=30`
- After 9:30 AM ET, keep current behavior unchanged

### Step 2: Relax Candle-Over-Candle for Premarket

**File:** `nexus2/domain/automation/warrior_entry_patterns.py` (L612-636)

Before 9:30 AM ET:
- Skip the control candle wait — if `current_price > PMH` AND volume confirms, enter immediately
- In premarket, sparse bars ARE the price action; waiting for a 2nd candle adds 15-60min delay

### Step 3: Verify Stop Width in Premarket

**File:** `nexus2/domain/automation/warrior_engine_entry.py` (near L1102)

The 5-bar consolidation low stop may produce absurdly wide stops with sparse premarket bars. Add a safety check:
- If stop distance > ATR * 2.5 (or some reasonable bound), use a tighter fallback (e.g., PMH - small buffer)
- Log a warning when premarket stop is widened

### Step 4: Batch Test Validation

Run the full batch test and compare:
1. All 11 LATE_ENTRY cases should show earlier entry times
2. Non-LATE_ENTRY cases should NOT regress (market hours unchanged)
3. Write results to `nexus2/reports/2026-02-23/batch_benchmark_premarket_fix.md`

## Output

- Modified files with changes
- Batch test comparison report
- Status report: `nexus2/reports/2026-02-23/backend_status_premarket_fix.md`
