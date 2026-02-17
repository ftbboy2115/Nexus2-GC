# Findings: Zero P&L Cases Investigation

> [!CAUTION]
> **CORRECTION (2026-02-16 21:07 ET):** This report's framing for HIND and PRFX (Cases 1 & 3) is misleading. It claims the bot "waits for pattern formation after the spike" — implying the bot can't trade premarket. **The bot trades premarket starting at 6:00 AM** (per `warrior.md`). The actual root cause for non-entry has NOT been verified by tracing the code bar-by-bar. The statement that "all require price action *after* a spike" was copied from `findings_nonentry_investigation.md` without independent verification. The CMCT (Case 2) and OPTX (Case 4) findings about missing data appear valid.

**Date:** 2026-02-16  
**Investigator:** Backend Planner  
**Total gap from non-entries: $75,634**

> [!IMPORTANT]
> The Warrior bot trades premarket (6 AM - 7:30 PM ET). All four cases have premarket
> price action within the bot's trading window. The failures are NOT due to trading hours.

---

## Summary

| # | Symbol | Date | Ross P&L | Root Cause | Fixability |
|---|--------|------|----------|------------|------------|
| 1 | HIND | 2026-01-27 | +$55,252 | PMH hit but candle-over-candle blocks; Ross enters below PMH | Pattern Gap |
| 2 | CMCT | 2025-12-22 | +$10,806 | No intraday data file + excluded from batch | Missing Data |
| 3 | PRFX | 2026-02-11 | +$5,971 | PMH single rejection wick; Ross enters below PMH | Pattern Gap |
| 4 | OPTX | 2026-01-06 | +$3,605 | No intraday data file + excluded from batch | Missing Data |

---

## Case 1: HIND ($55,252 gap) — PMH Rejected + Ross Enters Below PMH

### Bar Data Evidence (verified via `_tmp_bar_analysis.py`)

**PMH = $7.57** (from YAML `premarket_data.pmh`)

```
08:00: O=3.35  H=4.58  L=3.12  C=4.58  V=5,204      ← Ross enters ~$5.00
08:01: O=4.48  H=6.28  L=3.81  C=6.25  V=192,812     ← Ross adding at $5.50
08:02: O=6.35  H=7.43  L=4.38  C=5.50  V=1,359,955   ← Near PMH, massive wick
08:03-08:12: Consolidation $5-$7 range, heavy volume
08:13: O=6.96  H=7.57  L=6.70  C=7.55  V=1,755,203   ← PMH HIT EXACTLY
08:14: O=7.55  H=7.56  L=6.88  C=6.97  V=1,406,655   ← REVERSAL: H=$7.56 < $7.57
08:15: O=6.97  H=7.12  C=6.81                          ← Price fading
08:30+: Price crashes to $4.50, never recovers
```

### Blocking Mechanism 1: Candle-Over-Candle Confirmation

**File:** `nexus2/domain/automation/warrior_entry_patterns.py`:492-610 (`detect_pmh_break`)

At 08:13, price hits PMH $7.57 → sets **control candle** (high=$7.57).  
At 08:14, the NEXT bar high is $7.56 — **fails to break control high** ($7.56 < $7.57).

```python
# STAGE 2: Check if CURRENT candle is DIFFERENT from control candle and breaks control high
if current_candle_time and current_candle_time != watched.control_candle_time:
    if current_price > watched.control_candle_high:  # 7.56 > 7.57 → FALSE
        return EntryTriggerType.PMH_BREAK
```

**Verdict:** Candle-over-candle confirmation is **working correctly** — the PMH was wicked but immediately rejected. This is the exact scenario the confirmation pattern was designed to filter.

### Blocking Mechanism 2: Ross Enters Below PMH

The deeper issue: **Ross never trades the PMH breakout.** He enters at ~$5.00 at 08:00 — that's $2.57 below PMH. He's buying the initial momentum spike, adding every 50¢ ($5→$5.50→$6→$6.50→$7→$7.40), and selling into the PMH area.

The bot's below-PMH patterns (DIP_FOR_LEVEL, WHOLE_HALF_ANTICIPATORY, HOD_CONSOLIDATION_BREAK) don't match this price action because:
- **DIP_FOR_LEVEL**: Requires a dip from a prior high — price is going straight up
- **WHOLE_HALF_ANTICIPATORY**: Has `entry_triggered` guard that blocks after first attempt
- **HOD_CONSOLIDATION_BREAK**: Requires tight consolidation — this is a vertical spike

### Active Market Gate

Active market gate **PASSES** at 08:13: 14 bars available, avg volume 982,711.

### Fixability: Pattern Gap

This requires a new pattern: "**Premarket Momentum Spike**" — detect rapid price rise with volume explosion (e.g. >100% move in <5 minutes) and enter on first micro-pullback during the rise. High complexity, significant risk of false entries.

---

## Case 2: CMCT ($10,806 gap) — No Intraday Data

### Root Cause A: Excluded by batch filter

**File:** `nexus2/api/routes/warrior_sim_routes.py`:1360
```python
cases = [c for c in all_cases if c.get("status") == "POLYGON_DATA"]
```

CMCT has `status: USABLE` → **never included in batch runs**.

### Root Cause B: No intraday JSON file

**Verified:** `find_by_name *cmct*` in `tests/test_cases/intraday/` → 0 results

**File:** `nexus2/adapters/simulation/historical_bar_loader.py`:305-309
```python
json_path = self._test_cases_dir / "intraday" / f"{case_id}.json"
if not json_path.exists():
    return None
```

No `cmct_2025_12_22.json` exists → `load_test_case()` returns None → 0 bars → $0.

### Root Cause C: No `intraday_file` field

CMCT's YAML entry has no `intraday_file` field and no `data_source: polygon`. Only FMP daily data.

### Fixability: Missing Data

Fetch Polygon 1-min intraday for 2025-12-22, create JSON, update YAML `status` to `POLYGON_DATA`. Ross entered at $4.65-$4.70 (which equals PMH $4.65), so PMH_BREAK **plausibly fires** if data existed.

---

## Case 3: PRFX ($5,971 gap) — Single Rejection Wick + Below-PMH Entry

### Bar Data Evidence

**PMH = $7.93**

```
07:41: V=315      H=2.95   ← Dead premarket
07:49: V=724      H=2.93
08:12: V=750      H=2.91   ← 23min gap from prior bar
08:19: V=1,010    H=2.95
08:27: V=115      H=2.95
08:30: V=387,415  H=5.70   ← Momentum ignition
08:31: V=694,287  H=7.93   ← PMH HIT (single bar: O=5.34, H=7.93, C=4.36)
08:32: V=346,929  H=5.08   ← Crash, never recovers to PMH
```

### Blocking Mechanism: Massive Rejection Wick

**File:** `nexus2/domain/automation/warrior_entry_patterns.py`:492-610 (`detect_pmh_break`)

PMH $7.93 is hit on **ONE bar** (08:31) that opens at $5.34, wicks to $7.93, and closes at $4.36. This is a textbook rejection wick — the candle-over-candle confirmation would set control candle at 08:31, but the next bar (08:32) high is only $5.08, far below $7.93.

### Active Market Gate

Active market gate **PASSES**: 7 bars at 08:31, avg volume 154,945. However, there are significant time gaps (23min gap from 07:49 to 08:12), which the gate should catch at `max_time_gap_minutes=15`:

**File:** `nexus2/domain/automation/warrior_entry_helpers.py` (`check_active_market`)
```python
# Check last 5 bars for gaps
if last_gap_minutes > max_time_gap_minutes:
    return False, f"Large gap ({last_gap_minutes}min between bars)"
```

The check only looks at the **last 5 bars** (`for i in range(1, min(5, len(candles)))`) — and the last 5 bars at 08:31 go 08:27→08:30→08:31 (3min, 1min gaps: PASSES). The 23min gap is between bars 2 and 3 (07:49→08:12), which is outside the last-5 lookback.

### Ross's Entry: Below PMH

Ross enters at ~$4.15 during the 08:30-08:31 spike — $3.78 below PMH $7.93. Same pattern as HIND: buying during the momentum ignition, not the PMH breakout.

### Fixability: Pattern Gap

Same as HIND — needs "Premarket Momentum Spike" pattern.

---

## Case 4: OPTX ($3,605 gap) — No Intraday Data

### Root Causes

Identical structure to CMCT:

1. **Status filter**: `status: USABLE` (not `POLYGON_DATA`) → excluded from batch runs
   - **File:** `nexus2/tests/test_cases/warrior_setups.yaml`:62
2. **No intraday JSON**: `find_by_name *optx*` in `tests/test_cases/intraday/` → 0 results
3. **No `intraday_file` field** in YAML

### Fixability: Missing Data (Most Promising)

OPTX has `setup_type: orb` with entry at $3.50 near PMH $3.40. If data existed:
- ORB setup would establish opening range at 09:30 (`check_orb_setup()` at `warrior_engine_entry.py:623`)
- ORB breakout above $3.40 would likely fire at 09:31
- This is the **most plausibly fixable** of all 4 cases

---

## Root Cause Categories

### Category 1: Missing Data (CMCT + OPTX) — $14,411 gap

| Case | Fix Required | Likelihood of Entry |
|------|-------------|-------------------|
| CMCT | Fetch Polygon data, update YAML | Medium — PMH at $4.65, Ross entered at same level |
| OPTX | Fetch Polygon data, update YAML | **High** — ORB setup, price crosses PMH immediately |

### Category 2: Pattern Gap (HIND + PRFX) — $61,223 gap

Both cases share the same structure:
1. Ross enters during initial premarket momentum spike, **far below PMH**
2. Price reaches PMH briefly then crashes 40-50%
3. PMH_BREAK candle-over-candle **correctly blocks** (rejection wick)
4. No below-PMH pattern matches the vertical spike + aggressive adds

This is Ross's highest-conviction, most discretionary style: full buying power, adds every 50¢, enters on breaking news before pattern formation.

---

## Recommendations

1. **Quick Win: Fetch CMCT + OPTX data** (~30min)
   - Polygon intraday for both dates
   - OPTX likely produces profitable entry via ORB

2. **Analysis: Study below-PMH patterns for HIND/PRFX** (~2hr)
   - During the 08:00-08:13 rise, price crosses $5.00, $5.50, $6.00, $6.50, $7.00
   - Could WHOLE_HALF_ANTICIPATORY fire at these levels if guards were adjusted?
   - What specifically blocks it? (`entry_triggered` guard, MACD check, etc.)

3. **New Pattern: Premarket Momentum Spike** (~4-8hr, high risk)
   - Detect: volume explosion + rapid price rise in premarket
   - Entry: first micro-pullback during the rise
   - Risk: many premarket spikes are pump-and-dumps

---

## Files Examined

| File | Purpose |
|------|---------|
| [warrior_setups.yaml](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/tests/test_cases/warrior_setups.yaml) | CMCT L26, OPTX L57, HIND L623 |
| [historical_bar_loader.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/historical_bar_loader.py) | `load_test_case()` L292 — returns None if no JSON |
| [warrior_sim_routes.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py) | Batch filter L1360: only `POLYGON_DATA` |
| [warrior_entry_patterns.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py) | `detect_pmh_break` L492 — candle-over-candle logic |
| [warrior_engine_entry.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py) | `check_entry_triggers` L334 — pattern routing |
| [ross_hind_20260127.json](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/tests/test_cases/intraday/ross_hind_20260127.json) | 612 bars, PMH hit at 08:13 |
| [ross_prfx_20260211.json](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/tests/test_cases/intraday/ross_prfx_20260211.json) | 465 bars, PMH rejection wick at 08:31 |
