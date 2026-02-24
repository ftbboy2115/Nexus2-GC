# LATE_ENTRY Root Cause Spec

**Date:** 2026-02-23
**Priority:** P1 (~$312K P&L gap across 11 cases)
**Investigator:** Backend Planner

---

## Executive Summary

The bot enters 1-2 hours after Ross because **two pattern gates block entries during premarket**:

1. **`check_active_market()` gate** — rejects entries when bars are sparse, low volume, or have large time gaps (premarket conditions)
2. **Candle-over-candle confirmation** — requires 2+ separate candles, adding minutes-to-hours of delay in sparse premarket

These gates exist in `detect_pmh_break()` and `detect_dip_for_level()` — the two primary entry patterns. The sim start time, time scoring, and entry guards are **NOT** the bottleneck.

---

## Root Cause #1: `check_active_market()` Gate

### Finding

`check_active_market()` is called in both `detect_pmh_break()` and `detect_dip_for_level()`. It blocks entries when:
- Fewer than 5 bars available (`min_bars=5`)
- Average volume per bar < 1,000 (`min_volume_per_bar=1000`)
- Time gaps between bars > 15 minutes (`max_time_gap_minutes=15`)

**File:** [warrior_entry_patterns.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py)
**Location:** Lines 569-610 (PMH), Lines 388-435 (DIP_FOR_LEVEL)

#### PMH Break (L569-610):
```python
if engine._get_intraday_bars:
    try:
        tf = engine.config.entry_bar_timeframe
        if tf == "10s":
            activity_candles = await engine._get_intraday_bars(symbol, "10s", limit=60)
        else:
            activity_candles = await engine._get_intraday_bars(symbol, "1min", limit=10)
        ...
        if activity_candles:
            if tf == "10s":
                market_active, inactive_reason = check_active_market(
                    activity_candles,
                    min_bars=18, min_volume_per_bar=200, max_time_gap_minutes=5,
                )
            else:
                market_active, inactive_reason = check_active_market(
                    activity_candles,
                    min_bars=5, min_volume_per_bar=1000, max_time_gap_minutes=15,
                )
    ...
    if not market_active:
        logger.info(f"[Warrior Entry] {symbol}: PMH break BLOCKED - market not active ...")
        return None   # ← ENTRY KILLED
```

### Why It Blocks Premarket

In early premarket (4-8 AM), bars are naturally sparse:
- GRI first bar at 04:02 has only 250 volume — fails `min_volume_per_bar=1000`
- FLYE first bar at 04:59 has only 156 volume
- BCTX has bars at 04:00 (243 vol) with hour+ gaps between them — fails `max_time_gap_minutes=15`

Even when the stock starts heating up (7-8 AM), the **average** volume per bar remains low because the early sparse bars drag down the mean.

**File:** [warrior_entry_helpers.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_helpers.py)
**Location:** Lines 148-208 (`check_active_market` implementation)

```python
# Check average volume per bar
total_vol = sum(c.volume for c in candles if hasattr(c, 'volume'))
avg_vol = total_vol / len(candles)

if avg_vol < min_volume_per_bar:
    return False, f"Low volume ({int(avg_vol)} avg vs {min_volume_per_bar} min)"
```

---

## Root Cause #2: Candle-Over-Candle Confirmation Delay

### Finding

`detect_pmh_break()` requires a "control candle" to be set on the first bar that exceeds PMH, then waits for a SECOND candle to break the control candle's high. In sparse premarket, this adds significant delay.

**File:** [warrior_entry_patterns.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py#L612-L636)
**Location:** Lines 612-636

```python
# STAGE 1: Set control candle if not already set
if watched.control_candle_high is None:
    watched.control_candle_high = current_candle_high ...
    return None  # ← WAIT FOR NEXT CANDLE

# STAGE 2: Check if CURRENT candle is DIFFERENT from control candle
if current_candle_time and current_candle_time != watched.control_candle_time:
    if current_price > watched.control_candle_high:
        return EntryTriggerType.PMH_BREAK  # ← FINALLY ENTERS
```

If bars are 15-60 minutes apart (common in premarket), this adds 15-60 minutes of delay on top of the `check_active_market` gate.

---

## Confirmed Non-Issues

### ✅ Sim Start Time (NOT the Problem)

**File:** [sim_context.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L199-L209)
**Location:** Lines 199-209

The sim clock starts from the **first bar's time**, not a hardcoded 9:30:

```python
if data.bars:
    first_bar_time = data.bars[0].time  # e.g. "07:56"
    hour, minute = map(int, first_bar_time.split(":"))
    start_time = ET.localize(trade_date.replace(hour=hour, minute=minute, second=0))
else:
    start_time = ET.localize(trade_date.replace(hour=9, minute=30, second=0))
```

The 9:30 default only triggers if there are NO bars — which never happens for our test cases.

### ✅ Time Score (NOT the Problem)

**File:** [warrior_entry_scoring.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_scoring.py#L146-L171)

Time score is only **5% weight** in the composite score:
```python
score = (
    pattern_confidence * 0.50 +
    vol_normalized * 0.20 +
    catalyst_strength * 0.15 +
    spread_score * 0.05 +
    level_proximity * 0.05 +
    time_score * 0.05          # ← Only 5% weight
)
```

Premarket time score = 0.4 (vs 1.0 for ORB window). Delta = 0.03 points — negligible vs the 0.40 threshold.

### ✅ Engine State (NOT the Problem)

The engine is set to `RUNNING` (L487 of `sim_context.py`), and `step_clock_ctx` triggers entry checks when state is `"running"` or `"premarket"` (L137).

### ✅ Entry Guards (NOT the Problem)

`check_entry_guards()` in [warrior_entry_guards.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py) has no time-based gates. It checks: top_x picks, min score, blacklist, fail limit, MACD, position limits, pending entries, cooldown, and spread — none are time-dependent.

### ✅ `check_entry_triggers()` (NOT the Problem)

The main entry trigger loop in [warrior_engine_entry.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py#L334-L645) has NO explicit time gates. It evaluates all patterns on every cycle.

---

## Bar Data Evidence

All 11 LATE_ENTRY cases have premarket bars. The data is there — the patterns just reject it.

| Case | Symbol | Ross Entry | First Bar | PM Bars | First Vol | Issues |
|------|--------|-----------|-----------|---------|-----------|--------|
| ross_lcfy_20260116 | LCFY | 08:01 | 08:00 | 90 | 143,179 | High vol BUT starts late |
| ross_rolr_20260114 | ROLR | 08:18 | 04:29 | 95 | 1,700 | Sparse early, active ~8AM |
| ross_gri_20260128 | GRI | 08:45 | 04:02 | 76 | 250 | Very sparse until news |
| ross_hind_20260127 | HIND | 08:00 | 08:00 | 90 | 5,204 | Starts at 8AM, high vol |
| ross_bctx_20260127 | BCTX | 07:30 | 04:00 | 130 | 243 | Ultra sparse 4-7AM |
| ross_npt_20260203 | NPT | 07:50 | 07:08 | 137 | 10,500 | High vol from 7AM |
| ross_bnai_20260205 | BNAI | 07:07 | 04:00 | 231 | 4,459 | Good vol, lots of bars |
| ross_flye_20260206 | FLYE | ~08:50 | 04:59 | 46 | 156 | Sparse, low vol early |
| ross_rdib_20260206 | RDIB | ? | 04:48 | 165 | 358 | Low vol early |
| ross_mnts_20260209 | MNTS | 08:00 | 04:04 | 102 | 375 | Sparse until 8AM |
| ross_bnrg_20260211 | BNRG | 07:00 | 04:25 | 305 | 15,621 | High vol, many bars |

> [!IMPORTANT]
> Key observation: LCFY (Ross entry 08:01, first bar 08:00, 143K volume) and HIND (Ross entry 08:00, first bar 08:00, 5K volume) should have IMMEDIATE entries but `check_active_market` blocks them because they don't have 5+ bars at 08:00 — they're the FIRST bar. The bot must wait for 5+ bars (5+ minutes) before the gate passes.

---

## Change Surface

### A. Primary Fix: Relax `check_active_market` for Premarket

| # | File | Change | Location |
|---|------|--------|----------|
| 1 | `warrior_entry_patterns.py` | Adjust `check_active_market` params for premarket hours | L569-610 (PMH), L388-435 (DFL) |
| 2 | `warrior_entry_helpers.py` | Add time-aware thresholds in `check_active_market()` | L148-208 |

**Approach Options:**

**Option A: Time-aware thresholds (Recommended)**
- Before 9:30 AM, use relaxed parameters: `min_bars=3`, `min_volume_per_bar=500`, `max_time_gap_minutes=30`
- After 9:30 AM, keep current (stricter) parameters
- Rationale: Ross trades premarket when he sees ACTIVITY — even 3 bars with 500+ vol/bar is enough for a human to see "something is happening"

**Option B: Skip active market check entirely for premarket**
- Remove the `check_active_market` gate before 9:30 AM
- Rely on volume expansion check instead (already exists independently)
- Risk: may enter dead premarket

**Option C: Use `ross_entry_time` from YAML to set check-from time**
- Only for sim: start checking patterns N minutes before Ross's documented entry time
- Too naive for live trading, but would fix sim benchmarks

### B. Secondary Fix: Relaxed Candle Confirmation for Premarket

| # | File | Change | Location |
|---|------|--------|----------|
| 3 | `warrior_entry_patterns.py` | Allow instant PMH break entry during premarket | L612-636 |

**Approach:** Before 9:30 AM, skip the candle-over-candle requirement — if price > PMH + buffer AND volume confirms, enter immediately. The two-candle requirement is designed for rapid market hours where wicks are common. In premarket, bars ARE the price action.

### C. DIP_FOR_LEVEL Time Gate

| # | File | Change | Location |
|---|------|--------|----------|
| 4 | `warrior_entry_patterns.py` | Review `hour < 6` gate on DIP_FOR_LEVEL | L319-324 |

Currently blocks before 6 AM — this is reasonable. No change needed, but verify it doesn't interact with the active market gate to create a double-block.

---

## Wiring Checklist (for Backend Specialist)

- [ ] Modify `check_active_market` call in `detect_pmh_break()` to use relaxed thresholds when sim clock < 9:30 AM
- [ ] Modify `check_active_market` call in `detect_dip_for_level()` similarly
- [ ] Add premarket path in `detect_pmh_break()` to skip/relax candle-over-candle confirmation before 9:30
- [ ] Verify `detect_hod_consolidation_break()` doesn't have the same issue (it's called below PMH)
- [ ] Run batch test: compare new results vs current benchmark for the 11 LATE_ENTRY cases
- [ ] Verify non-LATE_ENTRY cases don't regress (market-hours behavior unchanged)

---

## Impact Assessment

### Cases Expected to Improve

| Case | Ross P&L | Current Bot | Gap | Expected Fix |
|------|----------|-------------|-----|-------------|
| ROLR | $85,000 | ~$0 | $85K | Premarket active market gate |
| HIND | $55,252 | ~$0 | $55K | First-bar active market gate |
| NPT | $81,000 | ~$0 | $81K | Premarket active market gate |
| MLEC (Feb 13) | $43,000 | ~$0 | $43K | 8:11 AM entry blocked |
| GRI | $31,600 | ~$0 | $32K | Premarket + candle confirm |
| LCFY | $10,457 | ~$0 | $10K | First-bar active market gate |
| MNTS | $9,000 | ~$0 | $9K | Premarket active market gate |
| BNAI | -$7,900 | ~$0 | $8K | 7:07 AM entry blocked |
| FLYE | $4,800 | ~$0 | $5K | Active market gate |
| BCTX | $4,500 | ~$0 | $5K | 7:30 AM entry blocked |
| BNRG | $271 | ~$0 | $0.3K | 7 AM VWAP break blocked |

> [!WARNING]
> Not all cases will become profitable — some may enter premarket and still lose. But the bot will at least have the OPPORTUNITY to trade, which is the prerequisite for capturing this P&L.

---

## Risk Assessment

1. **False premarket entries** — Relaxing the active market gate could cause entries into truly dead premarket bars (e.g., 4 AM with 200 vol). Mitigation: keep minimum volume threshold, just reduce it.
2. **Stop calculation in sparse bars** — If bars are spread out, the 5-bar consolidation low stop method may produce very wide stops. This is noted in the code (L1102 of `warrior_engine_entry.py`). May need investigation separately.
3. **Regression risk** — Changes to `check_active_market` thresholds affect market hours too if not guarded by time check. Must use time-conditional logic.

---

## Recommendation

**Implement Option A (time-aware thresholds)** as the primary fix, plus **relax candle confirmation for premarket** as secondary:

1. Get sim clock time in pattern detection functions
2. Before 9:30 AM: `min_bars=3, min_volume_per_bar=500, max_time_gap_minutes=30`
3. Before 9:30 AM: Skip candle-over-candle, allow instant PMH break on first candle + volume
4. After 9:30 AM: Keep all current behavior unchanged
5. Run full batch benchmark to validate
