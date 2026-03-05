# Tiebreaker Validation: Structural Claims

**Date:** 2026-03-03 14:00 ET  
**Validator:** Independent Tiebreaker (Audit Validator #2)  
**First validator's report:** `validation_missing_factors_fix.md`  
**Handoff:** `handoff_validator_tiebreaker.md`

---

## Summary Table

| Claim | Result | Confidence |
|-------|--------|------------|
| A: HOD proximity structurally always 1.0 on first entry | ✅ **CONFIRMED** | High |
| B: Vol expansion causes performance regression | ❌ **DISPUTED** | High |
| C: Root cause of -$9,944 regression | ⚠️ **PARTIAL** — weight redistribution is structurally suspect, but isolation requires A/B test | Medium |

---

## Claim A: HOD Proximity Structurally Always 1.0 on First Entry

**First validator's claim:** `recent_high` is set to `current_price` before scoring runs, making HOD proximity always 1.0 on first entry.

**Result: ✅ CONFIRMED**

### Evidence Chain (4 steps)

**Step 1 — Field default:**

**File:** `warrior_engine_types.py:189`  
**Verified with:** `Select-String -Path "nexus2\domain\automation\warrior_engine_types.py" -Pattern "recent_high"`  
**Output:** `recent_high: Optional[Decimal] = None  # Intraday high for pullback detection`  
**Conclusion:** `recent_high` starts as `None` for every new `WatchedCandidate`.

---

**Step 2 — First assignment:**

**File:** `warrior_engine_entry.py:402-403`  
**Code:**
```python
if watched.recent_high is None or current_price > watched.recent_high:
    watched.recent_high = current_price
```
**Verified with:** `Select-String -Path "nexus2\domain\automation\warrior_engine_entry.py" -Pattern "recent_high"`  
**Conclusion:** On first call, `None` is truthy for the `is None` branch → `watched.recent_high = current_price`. This runs at line 402, **before** the scoring block at lines 537-542.

---

**Step 3 — HOD proximity calculation:**

**File:** `warrior_engine_entry.py:538-542`  
**Code:**
```python
_hod_proximity_pct = None
if watched.recent_high and watched.recent_high > 0 and current_price > 0:
    _hod_proximity_pct = float(
        (watched.recent_high - current_price) / watched.recent_high * 100
    )
```
**Conclusion:** Since `watched.recent_high == current_price` (set 136 lines earlier at 402-403), the calculation is: `(current_price - current_price) / current_price * 100 = 0.0`. Always zero on first entry.

---

**Step 4 — Score mapping:**

**File:** `warrior_entry_scoring.py:253-257`  
**Code:**
```python
if pct_below_hod is None:
    return 0.5  # Unknown = neutral (backward compat)

if pct_below_hod <= 1.0:
    return 1.0  # At or near HOD (within 1%) — making new highs
```
**Conclusion:** `compute_hod_proximity_score(0.0)` → `0.0 <= 1.0` → returns **1.0** (max score).

### Net Impact

| Scenario | HOD Score | Weight | Contribution |
|----------|-----------|--------|--------------|
| Before (factor missing) | 0.5 (neutral default) | 0% (didn't exist) | 0.000 |
| After (always 1.0 on first entry) | 1.0 | 4% | 0.040 |

But this weight was taken FROM pattern confidence (35%→33%) and catalyst (8%→6%), so the net is:
- **Gained:** +0.040 (HOD, constant for all entries)
- **Lost:** −0.017 (pattern conf @ 0.85) + −0.010 (catalyst @ 0.5) = −0.027
- **Net:** approximately +0.013 uniform boost

The factor adds no **differentiation** — it boosts every first entry by the same amount. It's purely a threshold-shift, not a quality signal.

---

## Claim B: Volume Expansion Causes Performance Regression

**First validator's claim:** Runtime 102s → 236s (+130%) is caused by volume expansion computation.

**Result: ❌ DISPUTED**

### Evidence

**File:** `warrior_entry_helpers.py:368-380`  
**Code:**
```python
# Cache volume expansion ratio for dynamic scoring
# Uses the candles already fetched above — no extra API call
if len(candles) >= 10:
    prev_vols = [c.volume for c in candles[-10:-1] if hasattr(c, 'volume')]
    if prev_vols:
        avg_vol = sum(prev_vols) / len(prev_vols)
        current_vol = candles[-1].volume if hasattr(candles[-1], 'volume') else 0
        if avg_vol > 0:
            watched.cached_vol_expansion_ratio = current_vol / avg_vol
```

**Analysis:**
1. The `candles` variable is fetched at line 283: `await engine._get_intraday_bars(symbol, "1min", limit=30)` — this call was **already present** before the dynamic scoring changes (it's used for EMA/MACD/VWAP).
2. The vol expansion computation at lines 370-380 is **6 lines of pure arithmetic** on the same already-fetched `candles` list. No network calls, no disk I/O.
3. The function `update_candidate_technicals()` is throttled to 60-second intervals (line 409-413 in `warrior_engine_entry.py`). This throttle was pre-existing.

**Conclusion:** The vol expansion computation adds **nanoseconds** of arithmetic to an already-executing function. It cannot account for +134s of runtime. The runtime regression source is elsewhere — likely not related to the code changes under review (possibly server restart timing, cache cold-start, or an unrelated change).

> [!NOTE]
> I cannot verify the runtime regression root cause from a structural code review alone. The first validator correctly measured the regression but incorrectly attributed it to vol expansion. Isolated profiling would be needed to pinpoint the actual cause.

---

## Claim C: Root Cause of -$9,944 Regression

**First validator's claim:** Not specified — validator identified the regression but didn't isolate which change caused it.

**Result: ⚠️ PARTIAL — structurally suspect, requires A/B test for definitive answer**

### Structural Analysis

The changes introduced two new factors AND redistributed weight from existing factors:

| Factor | Old Weight | New Weight | Delta |
|--------|-----------|------------|-------|
| Pattern confidence | 35% | 33% | **−2%** |
| Catalyst strength | 8% | 6% | **−2%** |
| Volume expansion | 0% | 4% | +4% (NEW) |
| HOD proximity | 0% | 4% | +4% (NEW) |

**Root cause hypothesis: Weight redistribution, not new factors**

The two new factors are benign in isolation:
- **HOD proximity** always scores 1.0 on first entry → adds constant +0.04 to all entries (no differentiation)
- **Vol expansion** produces variable scores → adds real signal, but at only 4% weight, impact is small

The **weight taken from proven factors** is the structural risk:
- Pattern confidence is the **highest-leverage factor** (multiplied by the largest weight). Reducing it from 35%→33% reduces score differentiation between high-quality and low-quality patterns.
- Catalyst strength reduction similarly flattens scores.

**Impact math for a borderline entry** (pattern_conf=0.65, catalyst=0.3):

```
Old score contribution: 0.65 * 0.35 + 0.3 * 0.08 = 0.2275 + 0.024 = 0.2515
New score contribution: 0.65 * 0.33 + 0.3 * 0.06 = 0.2145 + 0.018 = 0.2325
+ HOD (always 1.0):    1.0 * 0.04 = 0.040
+ Vol expansion (5x):  0.8 * 0.04 = 0.032
Net new:               0.2325 + 0.040 + 0.032 = 0.3045

Diff: 0.3045 - 0.2515 = +0.053 (score INCREASE)
```

For borderline entries near the 0.40 threshold, a +0.05 boost could push entries through that **should have been blocked**. This aligns with the PAVM, MLEC, MNTS regressions — entries that were previously rejected or entered at different times may now be accepted.

**Conclusion:** The weight redistribution (stealing from pattern confidence and catalyst to fund always-high or variable new factors) is the most structurally likely cause. But isolating volume expansion's individual impact vs HOD proximity's impact requires separate A/B tests — one factor at a time.

---

## Overall Assessment

The first validator's structural analysis was **largely correct**:
- ✅ HOD always 1.0 claim: confirmed with complete code trace
- ❌ Vol expansion causing runtime: incorrect attribution (pure arithmetic, no extra API calls)
- ⚠️ Regression root cause: plausible hypothesis (weight redistribution) but needs isolated testing

### Quality Rating: **MEDIUM-HIGH**

The first validator's core finding (HOD always 1.0, $0 claim was false, -$9,944 actual regression) was accurate and actionable. The runtime attribution to vol expansion was the main error.
