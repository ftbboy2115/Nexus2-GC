# Volume Gate Investigation for Re-Entries

**Date:** 2026-02-15  
**Task:** Investigate existing volume checks and their applicability to re-entry quality gating  
**Requested by:** Coordinator handoff (`handoff_volume_gate_investigation.md`)

---

## 1. Inventory of ALL Existing Volume Checks

### Entry Pipeline Architecture (Flow Order)

```
Scanner (RVOL pillar)
    ↓
Pattern Detection (check_entry_triggers)
    ↓
Entry Guards (check_entry_guards)
    ↓
Entry Scoring (score_pattern)
    ↓
enter_position (order execution)
```

### Volume Checks by Location

| # | File | Function | Line | What It Checks | Threshold | Applies to Re-Entries? |
|---|------|----------|------|----------------|-----------|----------------------|
| 1 | `warrior_scanner_service.py` | `_calculate_rvol_pillar` | 1230 | Daily RVOL (projected vol / 10-day avg) | ≥ 2.0x (min) | No — scanner runs once at stock discovery |
| 2 | `warrior_entry_patterns.py` | `detect_abcd_pattern` | 101-113 | Current bar vol ≥ 80% of 10-bar avg | 0.8x avg | Both (no distinction) |
| 3 | `warrior_entry_patterns.py` | `detect_whole_half_anticipatory` | 229-243 | `check_volume_expansion` if NOT a clear breakout | 1.5x expansion | Both (no distinction) |
| 4 | `warrior_entry_patterns.py` | `detect_dip_for_level` | 459-472 | `check_volume_expansion` with **re-entry-aware threshold** | 3.0x normal / **5.0x re-entry** | **YES — only pattern with re-entry logic** |
| 5 | `warrior_entry_patterns.py` | `check_micro_pullback_entry` | 707-716 | Current bar volume > prior bar volume | current > prior | Both (no distinction) |
| 6 | `warrior_entry_patterns.py` | `detect_vwap_break_pattern` | 1050-1058 | `check_volume_confirmed` — current ≥ avg OR current > prior | Weakest check | Both (no distinction) |
| 7 | `warrior_entry_patterns.py` | `detect_inverted_hs_pattern` | 1138-1151 | Current ≥ 10-bar avg OR current > prior bar | Same as #6 | Both (no distinction) |
| 8 | `warrior_entry_patterns.py` | `detect_cup_handle_pattern` | 1231-1241 | Current bar vol ≥ 80% of 10-bar avg | 0.8x avg | Both (no distinction) |
| 9 | `warrior_entry_patterns.py` | `detect_bull_flag_pattern` | 868-941 | **NONE** | N/A | N/A |
| 10 | `warrior_entry_patterns.py` | `detect_pullback_pattern` | 770-865 | **NONE** | N/A | N/A |
| 11 | `warrior_entry_patterns.py` | `detect_pmh_break` | 492-610 | **NONE** | N/A | N/A |
| 12 | `warrior_entry_guards.py` | `check_entry_guards` | 35-149 | **NONE — zero volume checks** | N/A | N/A |
| 13 | `warrior_entry_scoring.py` | `score_pattern` | 64-125 | `volume_ratio` at 20% weight, informational scoring | MIN_SCORE 0.40 | Both (scoring only, not blocking) |
| 14 | `warrior_monitor_exit.py` | candle-under-candle | 469-483 | Exit confirmation: current vol > 1.5x avg | 1.5x (exit, not entry) | N/A |
| 15 | `warrior_monitor_scale.py` | scale logic | 41 | RVOL for add-on: 2.0x | 2.0x (scale, not entry) | N/A |

### Volume Helper Functions (`warrior_entry_helpers.py`)

| Function | Lines | Logic | Used By |
|----------|-------|-------|---------|
| `check_volume_confirmed` | 29-59 | `current ≥ avg OR current > prior` | VWAP_BREAK, INVERTED_HS |
| `check_volume_expansion` | 62-96 | `current / avg ≥ min_expansion` (strict ratio) | DIP_FOR_LEVEL, WHOLE_HALF |
| `check_high_volume_red_candle` | 99-140 | Red candle + vol ≥ 1.5x avg (distribution signal) | VWAP_BREAK (blocks entry) |

---

## 2. Gap Analysis: Why Bad Re-Entries Aren't Caught

### The Core Problem

> **Entry guards (`check_entry_guards`) have ZERO volume checks.**

The entry guard pipeline checks:
- ✅ Top-X picks filter
- ✅ Min score threshold
- ✅ Blacklist
- ✅ Fail limit
- ✅ **MACD gate** (already confirmed as a no-op for re-entry discrimination)
- ✅ Position guards (max scales, profit check)
- ✅ Spread filter
- ✅ Technical validation (VWAP/EMA alignment)
- ❌ **No volume gate at any level**

### Why This Matters for Re-Entries

The research identified that bad re-entries have **0.06× late/early volume ratio** vs good re-entries at **0.65×**. This means bad re-entries happen when volume has completely dried up. But:

1. **Only DIP_FOR_LEVEL has re-entry-aware volume logic** (line 460: 5.0x for re-entries vs 3.0x normal). All other patterns use the same threshold for first entries and re-entries.

2. **Three patterns have NO volume check at all** (BULL_FLAG, PULLBACK, PMH_BREAK). A re-entry through these patterns faces zero volume scrutiny.

3. **Four patterns use very weak volume checks** (ABCD, CUP_HANDLE at 0.8x; VWAP_BREAK, INVERTED_HS at "current ≥ avg OR current > prior"). These are trivially easy to pass even on dying volume.

4. **Volume checks are per-bar, not session-relative.** The research discriminator was **late session volume / early session volume** — a session-level metric. Pattern-level checks only compare the *current bar* to *recent bars*, which is a micro view. If the whole session has dried up, all recent bars are low-volume, so the current bar easily exceeds the (low) average.

### Concrete Example

A stock has its first entry at 08:00 with heavy volume. It gets stopped out at 08:30. At 10:15 (dying volume), the watch list still has the stock. A BULL_FLAG pattern fires. There is:
- No volume check in the pattern (BULL_FLAG has none)
- No volume check in the entry guards
- The MACD gate may pass (MACD could still be positive from earlier momentum)

Result: **bad re-entry on dead volume — exactly the 0.06x scenario.**

---

## 3. Recommendation: Centralized Volume Gate in Entry Guards

### Option A: Add Volume Gate to `check_entry_guards` (RECOMMENDED)

**Where:** `warrior_entry_guards.py`, in `check_entry_guards()` function (lines 35-149)  
**What:** Add a volume ratio check that applies to ALL entries, with a stricter threshold for re-entries.

**Rationale:**
- Guards are the **single chokepoint** — every entry must pass through them
- Catches re-entries through ALL patterns, even those with no pattern-level volume check
- Consistent with the guard architecture (MACD gate, spread filter, etc.)
- Can be easily configured (config flag, threshold) and A/B tested

**Approach:**
1. Fetch recent candles (already available — most patterns have already fetched them)
2. Compute a session-relative volume metric (NOT just bar-vs-recent-avg)
3. For re-entries: require a **stricter threshold** (the discriminator was 0.65x vs 0.06x late/early ratio)
4. For first entries: apply a reasonable minimum (e.g., 1.0x — current bar at least matches recent average)

**Session Volume Ratio Concept:**
```
late_volume  = avg volume of last N bars
early_volume = avg volume of first N bars of the session
ratio = late_volume / early_volume

If ratio < threshold → block re-entry
```

This directly maps to the research finding that good re-entries have 0.65x and bad ones have 0.06x.

**Suggested threshold:** 0.30x (midpoint between 0.06 bad and 0.65 good, with margin for safety).

### Option B: Retrofit Volume Checks into Every Pattern (NOT RECOMMENDED)

- Requires touching 10+ pattern functions
- Easy to miss patterns or have inconsistent thresholds
- Doesn't solve the "session-relative" problem since patterns compare against recent bars only
- High regression risk

### Option C: Add Volume Check to `enter_position` (POSSIBLE BUT LESS CLEAN)

- Works architecturally but muddies the guard/entry separation
- Guards are the established "gating" layer; `enter_position` is execution

---

## 4. Implementation Spec (if Option A is approved)

### Change Surface

| # | File | Change | Location |
|---|------|--------|----------|
| 1 | `warrior_types.py` | Add config fields | `WarriorEngineConfig` class |
| 2 | `warrior_entry_guards.py` | Add `_check_volume_gate` function | After `_check_macd_gate` |
| 3 | `warrior_entry_guards.py` | Wire into `check_entry_guards` | After MACD gate call |

### Config Fields (warrior_types.py)

```python
# Volume gate for re-entry quality
volume_gate_enabled: bool = True
volume_gate_min_ratio: float = 1.0         # Minimum bar vol / recent avg for ALL entries
volume_gate_reentry_min_ratio: float = 0.30  # Minimum late/early session vol ratio for re-entries
volume_gate_lookback_bars: int = 10          # Bars to average for comparison
```

### Guard Function Signature

```python
async def _check_volume_gate(
    engine: "WarriorEngine",
    watched: WatchedCandidate,
    entry_price: Decimal,
) -> tuple[bool, str]:
    """
    Volume gate: Block entries on insufficient volume.
    
    For re-entries: Requires late-session volume maintains 
    a minimum ratio vs early-session volume (research shows 
    good re-entries have 0.65x, bad ones have 0.06x).
    
    For all entries: Requires current bar volume exceeds 
    a minimum ratio vs recent average.
    
    Returns:
        (True, "") if volume OK
        (False, reason) if blocked
    """
```

### Key Design Decision: Detecting Re-Entries

The `WatchedCandidate` already tracks:
- `entry_attempt_count` (int) — incremented on each entry
- `last_exit_time` (datetime) — set on profit exit
- `last_exit_price` (Decimal) — set on profit exit

A re-entry is: `entry_attempt_count > 0 AND last_exit_time is not None`

This is the same logic already used in `detect_dip_for_level` (line 424).

### Existing Data Available at Guard Time

The guard functions already have access to `engine._get_intraday_bars`, which is used by `_check_macd_gate` to fetch candles. The volume gate can reuse the same candle data.

---

## 5. Risks and Considerations

1. **Session start ambiguity:** In premarket, "early volume" and "late volume" may not be meaningful until enough bars exist. Guard should pass-through if < N bars available.

2. **Sim vs Live:** Bar data comes from different sources. Volume ratios from sim (historical data) may differ from live (Alpaca streaming). Test in both.

3. **Interaction with DIP_FOR_LEVEL:** DIP_FOR_LEVEL already has its own 5.0x re-entry volume check. The guard-level check would be additive (both must pass). The guard check is session-relative; the pattern check is bar-relative. They measure different things and complement each other.

4. **Pattern-level volume checks remain:** This is defense-in-depth. The guard provides a session-level baseline; patterns provide bar-level confirmation.

---

## 6. Evidence Summary

All findings verified via `view_file` and `grep_search` against the actual codebase:

- **Entry guards have no volume checks:** Verified by `grep_search` for "volume" in `warrior_entry_guards.py` — zero results.
- **DIP_FOR_LEVEL is the only re-entry-aware pattern:** Verified at line 424-460 of `warrior_entry_patterns.py`.
- **Three patterns have no volume check at all:** BULL_FLAG (868-941), PULLBACK (770-865), PMH_BREAK (492-610) — verified by reading each function in full.
- **Volume helper functions are in `warrior_entry_helpers.py`:** `check_volume_confirmed` (29-59), `check_volume_expansion` (62-96), `check_high_volume_red_candle` (99-140).
