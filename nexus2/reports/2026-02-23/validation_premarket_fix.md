# Validation Report: Premarket Entry Fix

**Date**: 2026-02-23
**Validator**: Audit Validator (via Coordinator)
**Task**: Verify 6 claims from [backend_status_premarket_fix.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-02-23/backend_status_premarket_fix.md)

---

## Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | PMH Break — Relaxed `check_active_market` thresholds before 9:30 AM | **PASS** | See Claim 1 details |
| 2 | PMH Break — Skip candle-over-candle in premarket | **PASS** | See Claim 2 details |
| 3 | DFL — Same relaxed thresholds | **PASS** | See Claim 3 details |
| 4 | 10s timeframe default would NOT work | **PASS** | See Claim 4 details |
| 5 | No Regression — Market hours logic unchanged | **PASS** | See Claim 5 details |
| 6 | Batch Test — pytest passes | **PASS** | 757 passed, 4 skipped, 3 deselected |

---

## Claim 1: PMH Break — Relaxed `check_active_market` Thresholds

**Claim:** `is_premarket` flag computed from sim clock, with relaxed thresholds `min_bars=3, min_volume_per_bar=500, max_time_gap_minutes=30` before 9:30 AM; original thresholds unchanged after 9:30 AM.

**Verification:** Viewed [warrior_entry_patterns.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py) lines 586–638.

**Actual Code (L586–601) — `is_premarket` computation:**
```python
# Get current time for premarket-aware thresholds
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
        _now_et = _dt.now(pytz.timezone("US/Eastern"))
        is_premarket = _now_et.hour < 9 or (_now_et.hour == 9 and _now_et.minute < 30)
except Exception:
    pass
```

**Actual Code (L614–638) — threshold dispatch:**
```python
if is_premarket:
    # PREMARKET RELAXED THRESHOLDS:
    market_active, inactive_reason = check_active_market(
        activity_candles,
        min_bars=3,
        min_volume_per_bar=500,
        max_time_gap_minutes=30,
    )
elif tf == "10s":
    market_active, inactive_reason = check_active_market(
        activity_candles,
        min_bars=18,
        min_volume_per_bar=200,
        max_time_gap_minutes=5,
    )
else:
    market_active, inactive_reason = check_active_market(
        activity_candles,
        min_bars=5,
        min_volume_per_bar=1000,
        max_time_gap_minutes=15,
    )
```

**Result:** **PASS** — All values match the claim exactly. Premarket uses `3/500/30`, original 1min uses `5/1000/15`, 10s uses `18/200/5`.

---

## Claim 2: PMH Break — Skip Candle-Over-Candle in Premarket

**Claim:** Before 9:30 AM, `detect_pmh_break()` returns `PMH_BREAK` immediately without waiting for second candle. After 9:30 AM, candle-over-candle logic unchanged.

**Verification:** Viewed [warrior_entry_patterns.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py) lines 652–689.

**Actual Code (L652–662) — premarket instant entry:**
```python
# PREMARKET INSTANT ENTRY: Skip candle-over-candle in premarket
if is_premarket:
    logger.info(
        f"[Warrior Entry] {symbol}: PREMARKET PMH BREAK - "
        f"${current_price:.2f} > PMH ${watched.pmh:.2f} "
        f"(skipping candle-over-candle for premarket)"
    )
    return EntryTriggerType.PMH_BREAK
```

**Actual Code (L664–689) — original candle-over-candle (unchanged after `is_premarket` gate):**
```python
# STAGE 1: Set control candle if not already set
if watched.control_candle_high is None:
    watched.control_candle_high = ...
    return None

# STAGE 2: Check if CURRENT candle is DIFFERENT from control candle and breaks control high
if current_candle_time and current_candle_time != watched.control_candle_time:
    if current_price > watched.control_candle_high:
        return EntryTriggerType.PMH_BREAK
```

**Result:** **PASS** — Premarket returns early at L662 (skips candle-over-candle). After 9:30 AM, code falls through to original STAGE 1/STAGE 2 logic at L664+.

---

## Claim 3: DFL — Same Relaxed Thresholds

**Claim:** `detect_dip_for_level()` has `dfl_is_premarket` flag with same `hour < 9 or (hour == 9 and minute < 30)` check and same relaxed params `3/500/30`.

**Verification:** Viewed [warrior_entry_patterns.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py) lines 392–435.

**Actual Code (L392–393) — `dfl_is_premarket` computation:**
```python
# Determine if premarket (now_et already set above at L308-317)
dfl_is_premarket = now_et.hour < 9 or (now_et.hour == 9 and now_et.minute < 30)
```

**Actual Code (L411–435) — threshold dispatch:**
```python
if dfl_is_premarket:
    # PREMARKET RELAXED THRESHOLDS (same as PMH break)
    market_active, inactive_reason = check_active_market(
        activity_candles,
        min_bars=3,
        min_volume_per_bar=500,
        max_time_gap_minutes=30,
    )
else:
    # Adjust thresholds for 10s bars vs 1min bars
    tf = engine.config.entry_bar_timeframe
    if tf == "10s":
        market_active, inactive_reason = check_active_market(
            activity_candles, min_bars=18, min_volume_per_bar=200, max_time_gap_minutes=5,
        )
    else:
        market_active, inactive_reason = check_active_market(
            activity_candles, min_bars=5, min_volume_per_bar=1000, max_time_gap_minutes=15,
        )
```

**Result:** **PASS** — Same flag pattern, same relaxed values `3/500/30`, same original values for non-premarket.

> [!NOTE]
> The `now_et` variable for DFL uses the sim clock obtained at L308-317 (top of `detect_dip_for_level`), which also has the wall-clock fallback. Consistent with PMH break's approach.

---

## Claim 4: 10s Timeframe Default Would NOT Work

**Claim:** `HistoricalBarLoader.get_bars_up_to()` doesn't handle `"10s"` timeframe — it falls through to 1-min bars.

**Verification:** Viewed [historical_bar_loader.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/historical_bar_loader.py) lines 420–442 and [sim_context.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py) line 389.

**Actual Code — `HistoricalBarLoader.get_bars_up_to()` (L420–442):**
```python
def get_bars_up_to(self, symbol: str, time_str: str, timeframe: str = "1min", include_continuity: bool = True):
    # ...
    if timeframe == "5min":
        return data.aggregate_to_5min(time_str)
    else:
        return data.get_bars_up_to(time_str, include_continuity=include_continuity)
```

**Actual Code — `sim_get_intraday_bars()` in sim_context.py (L389):**
```python
bars = _loader.get_bars_up_to(symbol, time_str, timeframe, include_continuity=True)
```

**Analysis:** The `sim_get_intraday_bars` callback passes `timeframe` through to `loader.get_bars_up_to()`. But `get_bars_up_to` only checks for `"5min"` — everything else (including `"10s"`) hits the `else` branch, which returns 1-min bars. So setting `entry_bar_timeframe="10s"` would result in 1-min bars being passed to `check_active_market()` with the 10s thresholds (`max_time_gap=5min`), which would be **MORE** restrictive on 1-min data.

**Result:** **PASS** — Claim is accurate. 10s timeframe default would not work as described.

---

## Claim 5: No Regression — Market Hours Logic Unchanged

**Claim:** All premarket-relaxed paths gated behind `is_premarket`/`dfl_is_premarket`. When false, code flows through exact original paths.

**Verification:** Reviewed all three change sites in `warrior_entry_patterns.py`:

| Location | Gate Variable | Premarket Path | Market Hours Path |
|----------|---------------|----------------|-------------------|
| PMH `check_active_market` (L614) | `is_premarket` | L615-624 (relaxed thresholds) | L625-638 (original 10s/1min branches) |
| PMH candle-over-candle (L656) | `is_premarket` | L657-662 (instant entry) | L664-689 (original STAGE 1/2) |
| DFL `check_active_market` (L411) | `dfl_is_premarket` | L412-418 (relaxed thresholds) | L419-435 (original 10s/1min branches) |

**Analysis:** All three changes are structured as `if is_premarket: ... else: [original code]`. The `else` branches contain the exact same thresholds as before the fix. No new parameters or thresholds affect market-hours behavior.

**Result:** **PASS** — No regression risk. Market hours paths are untouched.

---

## Claim 6: Batch Test — pytest Passes

**Claim:** Test suite passes.

**Verification:** Ran `pytest nexus2/tests/ -x -q` (command executed, user provided output).

**Actual Output:**
```
757 passed, 4 skipped, 3 deselected in 152.02s (0:02:32)
```

**Result:** **PASS** — 757 tests pass, 0 failures.

---

## Overall Rating

**HIGH** — All 6 claims verified. Code matches claims exactly. No discrepancies found.

> [!IMPORTANT]
> The backend status report correctly notes the fix had **negligible batch impact** (~$1K) due to missing LATE_ENTRY test cases and empty trades array in concurrent runner. The code changes themselves are correct and well-structured.
