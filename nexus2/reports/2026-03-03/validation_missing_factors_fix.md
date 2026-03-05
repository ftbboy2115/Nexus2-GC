# Validation Report: Missing Scoring Factors Fix

**Date:** 2026-03-03 13:44 ET  
**Validator:** Audit Validator  
**Source:** `nexus2/reports/2026-03-03/backend_status_missing_factors_fix.md`  
**Handoff:** `nexus2/reports/2026-03-03/handoff_validator_missing_factors.md`

---

## Overall Rating: ⛔ LOW — Requires Rework

> [!CAUTION]
> **Claim 9 ($0 batch regression) is FALSE.** Actual result is a **-$9,944.48 regression** (3 cases degraded, 0 improved).
> The dynamic scoring changes are actively harmful to P&L and must be reverted or tuned.

---

## Claim Verification Table

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | `WatchedCandidate` has `cached_vol_expansion_ratio` field | ✅ PASS | `warrior_engine_types.py:202` — field exists with `Optional[float] = None` |
| 2 | `update_candidate_technicals` computes vol expansion from candles | ✅ PASS | `warrior_entry_helpers.py:368-380` — computation block found, uses last 9 bars |
| 3 | `_vol_expansion_ratio` reads cached value, not `None` | ✅ PASS | `warrior_engine_entry.py:532` — `_vol_expansion_ratio = watched.cached_vol_expansion_ratio` |
| 4 | `compute_hod_proximity_score` exists with correct tiers | ✅ PASS | `warrior_entry_scoring.py:239-263` — 4 tiers: ≤1%→1.0, ≤5%→0.7, ≤10%→0.4, >10%→0.2 |
| 5 | `score_pattern()` accepts `hod_proximity_pct` param | ✅ PASS | `warrior_entry_scoring.py:287` — parameter exists, optional, default None |
| 6 | HOD proximity computed in scoring prep block | ✅ PASS | `warrior_engine_entry.py:538-542` — computed as `(recent_high - current_price) / recent_high * 100` |
| 7 | `hod_proximity_pct` passed to `score_pattern()` | ✅ PASS | `warrior_engine_entry.py:579` — passed as keyword arg in `add_candidate()` |
| 8 | Weights sum to ~1.0 | ✅ PASS | Manual sum: 0.33+0.10+0.06+0.04+0.10+0.08+0.08+0.06+0.04+0.04+0.04+0.015+0.015 = **1.000** |
| 9 | Batch test regression = $0 | ⛔ **FAIL** | Actual: **-$9,944.48** regression. See batch test section below. |

---

## Challenge 1: Volume Expansion — Real Values?

**Verdict: YES, computes real values, but timing is correct.**

**Claim:** `cached_vol_expansion_ratio` is computed in `update_candidate_technicals()` using already-fetched candles.

**Verification:** Code at `warrior_entry_helpers.py:368-380`:
```python
# Cache volume expansion ratio for dynamic scoring
if len(candles) >= 10:
    prev_vols = [c.volume for c in candles[-10:-1] if hasattr(c, 'volume')]
    if prev_vols:
        avg_vol = sum(prev_vols) / len(prev_vols)
        current_vol = candles[-1].volume if hasattr(candles[-1], 'volume') else 0
        if avg_vol > 0:
            watched.cached_vol_expansion_ratio = current_vol / avg_vol
```

**Timing analysis:** `update_candidate_technicals()` fires on the FIRST check_entry_triggers call because `_last_tech_update_ts` defaults to 0 (line 409: `getattr(watched, '_last_tech_update_ts', 0)`), making `_now - 0 >= 60` always true. The `await` at line 412 blocks until complete, so cached values ARE available before scoring runs.

**Conclusion:** Volume expansion IS computing real values. NOT a no-op for this factor.

---

## Challenge 2: HOD Proximity — Real Values?

**Verdict: STRUCTURALLY ALWAYS 1.0 ON FIRST ENTRY. Effectively a no-op for primary entries.**

**Code trace:**
1. `warrior_engine_entry.py:402-403`: `if watched.recent_high is None or current_price > watched.recent_high: watched.recent_high = current_price`
2. `warrior_engine_entry.py:538-542`: `_hod_proximity_pct = (watched.recent_high - current_price) / watched.recent_high * 100`

On the **first** check_entry_triggers call for any symbol: `recent_high` starts as `None` → set to `current_price` → `_hod_proximity_pct = 0.0` → `compute_hod_proximity_score(0.0) = 1.0` (max score).

**This means:**
- On first entry attempt: HOD proximity = 1.0 (ALWAYS, structurally)
- Previously (when missing): HOD proximity = 0.5 (neutral default)
- Net change: +0.5 * 0.04 = **+0.020 score boost** to EVERY first entry

This +0.020 boost is combined with the **weight redistribution** that REDUCES pattern confidence (35%→33%) and catalyst (8%→6%):
- Pattern loss: ~-0.017 (for conf=0.85)
- Catalyst loss: ~-0.010 (for cat=0.5)
- HOD gain: +0.020
- Net: approximately -0.007 to +0.005 depending on input values

**Result:** HOD proximity doesn't differentiate between entries on first attempt — it gives the same +0.020 boost to ALL entries. It only provides useful differentiation on RE-ENTRIES (where `recent_high` accumulated over multiple cycles), but re-entry penalty (8% weight) already handles that more aggressively.

---

## Challenge 3: Why $0 P&L Claimed (But Actually -$9,944)?

### Batch Test Execution

**Verification Command:**
```powershell
python scripts/gc_quick_test.py --all --diff
```

**Actual Output:**
```
DIFF vs BASELINE (39 cases)
Baseline saved: 2026-03-02 22:01:05

  Improved:  0/39
  Regressed: 3/39
  Unchanged: 36/39
  Net change:  $-9,944.48
  New total P&L: $345,094.18  (Ross: $446,405.87)
  Capture: 77.3%  (Fidelity: 45.3%)
  Runtime: 236.2s  (baseline: 102.3s, delta: +133.9s)

  Case                           |      Old P&L |      New P&L |       Change
  ross_pavm_20260121             | $ 19,046.82 | $ 11,521.52 | $ -7,525.30
  ross_mlec_20260213             | $   -578.33 | $ -2,000.67 | $ -1,422.34
  ross_mnts_20260209             | $-15,502.64 | $-16,499.48 | $   -996.84
```

**Result: ⛔ FAIL**

The backend specialist claimed $0 regression. The actual result is **-$9,944.48** with:
- **PAVM**: -$7,525.30 regression (massive, from $19K to $11.5K)
- **MLEC**: -$1,422.34 regression
- **MNTS**: -$996.84 regression
- **0 improvements**

**Possible explanations for the discrepancy:**
1. Backend specialist ran against a different baseline
2. Backend specialist ran with the server already running (cached state)
3. Backend specialist didn't actually run `--all --diff` after making the changes
4. Additional code changes were made between the specialist's test and this validation

### Runtime Regression

Runtime increased from 102.3s → 236.2s (+130% slower). This suggests the volume expansion computation in `update_candidate_technicals()` is adding significant overhead despite claiming "no extra API calls."

---

## Challenge 4: Weight Math

**Verified manually from `warrior_entry_scoring.py:352-368`:**

| Factor | Weight |
|--------|--------|
| Pattern confidence | 0.33 |
| Volume ratio | 0.10 |
| Catalyst strength | 0.06 |
| Time score | 0.04 |
| MACD momentum | 0.10 |
| EMA trend | 0.08 |
| Re-entry decay | 0.08 |
| VWAP position | 0.06 |
| Volume expansion | 0.04 |
| Price extension | 0.04 |
| HOD proximity | 0.04 |
| Spread score | 0.015 |
| Level proximity | 0.015 |
| **TOTAL** | **1.000** |

**Result: ✅ PASS** — weights sum to exactly 1.0.

---

## Challenge 5: Per-Factor Real Value Audit

| Factor | Real Value? | Evidence | Notes |
|--------|------------|----------|-------|
| MACD histogram | ✅ YES | Cached via `update_candidate_technicals()` on first cycle | Falls back to `entry_snapshot` if not cached |
| EMA trend (9/20) | ✅ YES | Set in `update_candidate_technicals():353-358` | Both EMA 9 and 20 computed from full candle history |
| Re-entry decay | ✅ YES | `watched.entry_attempt_count` tracked on WatchedCandidate | Always 0 on first entry (score=1.0) |
| VWAP position | ✅ YES | Computed in `update_candidate_technicals():386-394` | Uses today's candles only |
| Vol expansion | ✅ YES | Cached in `update_candidate_technicals():368-380` | Requires ≥10 candles (may be None if < 10) |
| Price extension | ✅ YES | Computed inline at `warrior_engine_entry.py:525-529` | Uses `watched.pmh` (always available) |
| HOD proximity | ⚠️ TECHNICALLY | Computed at `:538-542` | **Structurally always 0.0% (=score 1.0) on first entry** because `recent_high` is set to `current_price` at :402-403 |

**Conclusion:** 6 of 7 factors produce genuinely variable real values. HOD proximity produces a real value but it's structurally invariant on first entry (always 1.0).

---

## Is This Feature a No-Op?

**NO — it is NOT a no-op. It is worse: it is an ACTIVE REGRESSION.**

The feature computes real values and those values are changing scores sufficiently to alter 3 test case outcomes, all for the worse (-$9,944.48). The backend specialist's claim of $0 change was false.

---

## Additional Findings

### Handoff CLI Commands Were Wrong

The handoff document suggested these commands:
```powershell
python scripts/gc_quick_test.py --case ross_cmct_20260109 --verbose
```
**Neither `--case` nor `--verbose` exist.** Correct syntax: positional args (e.g., `python scripts/gc_quick_test.py ross_cmct_20260109 --trades`).

---

## Recommendation

> [!CAUTION]
> **These changes should be REVERTED immediately.** The dynamic scoring modifications caused a -$9,944.48 P&L regression with zero improvements. The weight redistribution (reducing pattern confidence from 35%→33% and catalyst from 8%→6%) hurt more than the new factors helped.

Specific issues to address before re-attempting:
1. **HOD proximity is structurally useless on first entry** — needs redesign (e.g., use premarket candle data for HOD instead of setting it to current_price on first observation)
2. **Weight redistribution should not steal from proven factors** — new factors should get weight from neutral/low-value sources
3. **Volume expansion and MACD changes need isolated A/B testing** — test each factor individually to identify which is causing the regression
4. **Runtime doubled** — the 130% runtime increase needs investigation
