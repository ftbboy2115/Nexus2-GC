# Backend Status: Round 3 Scoring Revert

**Date:** 2026-03-03 14:19 ET  
**Agent:** Backend Specialist  
**Task:** Surgically revert Round 3 scoring changes (-$9,944 regression)

---

## Result: ✅ SUCCESS — Zero Regression

```
  DIFF vs BASELINE (39 cases)
  Baseline saved: 2026-03-02 22:01:05
  Improved:  0/39
  Regressed: 0/39
  Unchanged: 39/39
  Net change:  $+0.00
  New total P&L: $355,038.66  (Ross: $446,405.87)
  Capture: 79.5%  (Fidelity: 47.4%)
  Runtime: 133.4s  (baseline: 102.3s, delta: +31.1s)
```

---

## Files Changed

### 1. `warrior_entry_scoring.py`

| Change | Detail |
|--------|--------|
| **DELETED** `compute_hod_proximity_score()` | Lines 239-263 removed entirely |
| **REMOVED** `hod_proximity_pct` parameter | From `score_pattern()` signature |
| **REMOVED** `hod_score` computation | Line `hod_score = compute_hod_proximity_score(hod_proximity_pct)` |
| **REMOVED** `hod_score * 0.04` weight | From weighted composite sum |
| **REVERTED** `pattern_confidence` weight | `0.33` → `0.35` (back to Round 2 value) |
| **REVERTED** `catalyst_strength` weight | `0.06` → `0.08` (back to Round 2 value) |
| **UPDATED** docstring | 53%/47% → 55%/45% split, removed HOD line |

### 2. `warrior_engine_entry.py`

| Change | Detail |
|--------|--------|
| **REMOVED** `compute_hod_proximity_score` import | Line 95 |
| **SET** `_vol_expansion_ratio = None` | Was `watched.cached_vol_expansion_ratio` (line 532) |
| **REMOVED** `_hod_proximity_pct` computation block | Lines 537-542 (6 lines) |
| **REMOVED** `_hod_str` debug variable | Line 546 |
| **REMOVED** `hod={_hod_str}` from debug log | Line 551 |
| **REMOVED** `hod_proximity_pct=_hod_proximity_pct` | From `score_pattern()` call (line 579) |
| **REMOVED** `"hod_proximity": _hod_proximity_pct` | From factors dict (line 598) |

### 3. `warrior_engine_types.py`

| Change | Detail |
|--------|--------|
| **REMOVED** `cached_vol_expansion_ratio` field | Line 202 from `WatchedCandidate` dataclass |

### 4. `warrior_entry_helpers.py`

| Change | Detail |
|--------|--------|
| **REMOVED** volume expansion caching block | Lines 368-380 (13 lines) from `update_candidate_technicals()` |

---

## What Was Preserved (Round 1-2)

All Round 1-2 changes remain intact:
- `compute_macd_score()` — function + wiring
- `compute_ema_trend_score()` — function + wiring
- `compute_reentry_decay()` — function + wiring
- `compute_vwap_score()` — function + wiring
- `compute_volume_expansion_score()` — function exists (NOT wired, returns neutral)
- `compute_extension_score()` — function + wiring
- `cached_macd_histogram` field on `WatchedCandidate`
- `current_ema_20`, `is_above_ema_20` fields
- MACD histogram caching in `update_candidate_technicals()`
- MACD timing fix (caching before gate check)

---

## Testable Claims

1. **`warrior_entry_scoring.py`:** `compute_hod_proximity_score` does NOT exist  
   - Verify: `Select-String -Path warrior_entry_scoring.py -Pattern "compute_hod_proximity_score"` → 0 results

2. **`warrior_entry_scoring.py`:** `pattern_confidence` weight is `0.35`  
   - Verify: `Select-String -Path warrior_entry_scoring.py -Pattern "pattern_confidence \* 0.35"` → 1 result

3. **`warrior_entry_scoring.py`:** `catalyst_strength` weight is `0.08`  
   - Verify: `Select-String -Path warrior_entry_scoring.py -Pattern "catalyst_strength \* 0.08"` → 1 result

4. **`warrior_engine_entry.py`:** `_vol_expansion_ratio = None` (not reading from cache)  
   - Verify: `Select-String -Path warrior_engine_entry.py -Pattern "_vol_expansion_ratio = None"` → 1 result

5. **`warrior_engine_types.py`:** `cached_vol_expansion_ratio` field does NOT exist  
   - Verify: `Select-String -Path warrior_engine_types.py -Pattern "cached_vol_expansion_ratio"` → 0 results

6. **`warrior_entry_helpers.py`:** No volume expansion caching block  
   - Verify: `Select-String -Path warrior_entry_helpers.py -Pattern "cached_vol_expansion_ratio"` → 0 results
