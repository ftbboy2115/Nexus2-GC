# Backend Specialist Handoff: Dynamic Entry Scoring

**Date:** 2026-03-03 11:06 ET  
**From:** Coordinator  
**To:** Backend Specialist  
**Plan:** `nexus2/reports/2026-03-03/plan_dynamic_entry_scoring.md`  
**Output:** `nexus2/reports/2026-03-03/backend_status_dynamic_scoring.md`

---

## Task

Implement price-action-aware dynamic scoring for Warrior Bot entries. The current scoring system is blind to real-time price action — 85% of weight comes from static scanner metadata. Every PMH_BREAK scores ~0.79 regardless of whether the stock is in fresh momentum or fading.

**Read the full plan at:** `nexus2/reports/2026-03-03/plan_dynamic_entry_scoring.md`

---

## Implementation Steps

### Step 1: Modify `warrior_entry_scoring.py` (202 lines)

1. Add 6 new parameters to `score_pattern()` — all optional with backward-compatible defaults:
   - `macd_histogram` (float)
   - `reentry_count` (int)
   - `ema_trend` (str: "strong"/"weakening"/"bearish")
   - `vwap_distance_pct` (float)
   - `volume_expansion` (float)
   - `price_extension_pct` (float)

2. Rebalance weights to 45% static / 55% dynamic (see plan for exact table)

3. Add 6 scoring helper functions:
   - `compute_macd_score(histogram)` → 0.0-1.0
   - `compute_ema_trend_score(above_ema9, above_ema20)` → 1.0/0.5/0.2
   - `compute_reentry_decay(count)` → 1.0/0.6/0.3
   - `compute_vwap_score(distance_pct)` → 0.0-1.0
   - `compute_volume_expansion_score(ratio)` → 0.0-1.0
   - `compute_extension_score(pct)` → 0.0-1.0

### Step 2: Modify `warrior_engine_entry.py` (line ~500)

Wire dynamic data into `add_candidate()` closure in `check_entry_triggers()`:
- Compute MACD, EMA trend, VWAP distance, extension, volume expansion ONCE per symbol per cycle
- Pass through to `score_pattern()` in the `add_candidate()` closure
- Data sources are already computed — see plan for exact attribute names

### Step 3: Modify `warrior_entry_guards.py`

Add EMA hard gate in `check_entry_guards()`:
- Below BOTH 9 AND 20 EMA = BLOCKED (independent of MACD)
- Below 9 only but above 20 = allowed (scoring penalty handles this)
- Place BEFORE the existing falling knife guard

### Step 4: Create Unit Tests

Create `nexus2/tests/domain/test_warrior_entry_scoring.py`:
- Test backward compat (old args still work)
- Test each new factor in isolation
- Test combined "fresh breakout" vs "fading re-entry" scenario
- Test hard EMA gate in guards

### Step 5: Run Batch Tests

```powershell
python scripts/gc_quick_test.py --all --diff
```

Compare against $355,039 baseline. Expected: within 5% ($337K-$373K).

---

## Key Context

- `MIN_SCORE_THRESHOLD = 0.40` — this is the gate. Currently everything passes (~0.79). With dynamic factors, bad re-entries should fall below 0.40.
- `watched.entry_attempt_count` — already tracked, no changes needed
- `watched.entry_snapshot` — already contains MACD, EMA, VWAP from `_check_macd_gate()`
- `watched.is_above_ema9` / `watched.is_above_ema20` — already set by `update_candidate_technicals()`
- `watched.current_vwap` — already populated every 60s
- `watched.pmh` — already set by scanner

## Research References

- `nexus2/reports/2026-03-03/research_entry_quality_gap.md` — Full analysis
- `nexus2/reports/2026-03-03/validation_entry_quality_gap.md` — Validator results
- `nexus2/reports/2026-03-03/live_session_review_morning.md` — Today's live trade data
