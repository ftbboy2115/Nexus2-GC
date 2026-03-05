# Backend Specialist Handoff: Revert Round 3 Changes

**Date:** 2026-03-03 13:52 ET  
**From:** Coordinator  
**To:** Backend Specialist  
**Output:** `nexus2/reports/2026-03-03/backend_status_round3_revert.md`

---

## Task

Surgically remove the Round 3 changes (volume expansion wiring + HOD proximity) that caused a **-$9,944 regression** (3 cases degraded: PAVM -$7,525, MLEC -$1,422, MNTS -$997).

Keep ALL Round 1 and Round 2 changes (MACD, EMA trend, re-entry decay, VWAP, price extension, MACD timing fix). Those were verified at $0 regression.

---

## What to Remove (Round 3 Only)

### 1. `warrior_entry_scoring.py`

- **DELETE** the `compute_hod_proximity_score()` function entirely
- **DELETE** the `hod_proximity_pct` parameter from `score_pattern()`
- **REVERT** weight changes from Round 3:
  - Pattern confidence: 33% → back to **35%**
  - Catalyst: 6% → back to **8%**
  - Remove 4% HOD proximity weight
- **DO NOT** remove these (they're from Round 1-2): `compute_macd_score`, `compute_ema_trend_score`, `compute_reentry_decay`, `compute_vwap_score`, `compute_volume_expansion_score`, `compute_extension_score`

### 2. `warrior_engine_entry.py`

- **REMOVE** the `_hod_proximity_pct` computation and its `score_pattern()` argument
- **REMOVE** the `_vol_expansion_ratio` assignment that reads from `watched.cached_vol_expansion_ratio`
- **SET** `_vol_expansion_ratio = None` (back to neutral — the function exists but wiring caused regression)
- **DO NOT** remove MACD, EMA, VWAP, re-entry, or price extension wiring

### 3. `warrior_engine_types.py`

- **REMOVE** the `cached_vol_expansion_ratio` field from `WatchedCandidate`
- **DO NOT** remove `cached_macd_histogram`, `current_ema_20`, `is_above_ema_20` (Round 2)

### 4. `warrior_entry_helpers.py`

- **REMOVE** the volume expansion computation block added in `update_candidate_technicals()`
- **DO NOT** remove the MACD histogram caching or EMA-20 population (Round 2)

---

## Verification

```powershell
python scripts/gc_quick_test.py --all --diff
```

**Expected result:** $355,038.66 (zero regression). If the result is ANYTHING other than this, report the diff and DO NOT claim success.

> [!CAUTION]
> The previous specialist claimed $0 regression when the actual result was -$9,944.
> **Run the batch test YOURSELF and report the EXACT output.**

---

## Status Report Format

List each file changed, exact lines removed, and paste the batch test output verbatim.
