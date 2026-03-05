# Backend Specialist Handoff: Fix Missing Scoring Factors

**Date:** 2026-03-03 12:53 ET  
**From:** Coordinator  
**To:** Backend Specialist  
**Previous work:** `nexus2/reports/2026-03-03/backend_status_dynamic_scoring.md`, `backend_status_scoring_timing_fix.md`  
**Validator findings:** `nexus2/reports/2026-03-03/validation_dynamic_scoring_adversarial.md`  
**Output:** `nexus2/reports/2026-03-03/backend_status_missing_factors_fix.md`

---

## Task

The adversarial validator found 2 gaps in the dynamic scoring implementation. Fix both.

---

## Fix 1: Volume Expansion — Dead Code (HIGH PRIORITY)

**Problem:** `_vol_expansion` variable is initialized at `warrior_engine_entry.py` line ~531 but **never assigned a value**. It always passes `None` to `score_pattern()`, which defaults to 0.5 (neutral). The 4% weight allocated to volume expansion is wasted.

**What volume expansion measures:** Is the breakout candle(s) showing significantly higher volume than recent average? Ross Cameron requires volume confirmation on breakouts — a breakout without volume is a fake breakout.

**Available data:** `check_volume_expansion()` exists as a standalone function. The validator confirmed it IS called in `detect_whole_half_anticipatory()` and `detect_dip_for_level()` patterns.

**Investigate:**
1. Where is `check_volume_expansion()` defined? What does it return?
2. Does it need candle data that's already fetched in the scoring preparation block?
3. If candle data is already available (e.g., from `update_candidate_technicals()` or cached bars), compute the ratio and assign it.

**Expected implementation:** Compute volume expansion ratio in the same block where MACD, EMA, and VWAP are prepared (around lines 492-542 in `warrior_engine_entry.py`), then assign to `_vol_expansion`.

```python
# Volume expansion: current bar vol vs recent avg
# If bars are available from technicals cache, compute ratio
_vol_expansion = None
if cached_bars and len(cached_bars) >= 10:
    current_vol = cached_bars[-1].volume
    avg_vol = sum(b.volume for b in cached_bars[-11:-1]) / 10
    if avg_vol > 0:
        _vol_expansion = current_vol / avg_vol
```

---

## Fix 2: Price vs HOD — Missing Factor (MEDIUM PRIORITY)

**Problem:** `watched.recent_high` tracks the high of day, but this is NOT used in scoring. Price vs HOD tells you whether the stock is trading into strength (at/near HOD = making new highs) or weakness (far below HOD = fading from peak).

**Why it matters:** Ross enters near HOD. A stock 10% below HOD is in a pullback or fade — very different quality than a stock making new highs.

**Implementation:**
1. Add `hod_proximity` parameter to `score_pattern()` (optional, default None)
2. Add `compute_hod_proximity_score(current_price, recent_high)` helper:
   - At HOD (within 1%): 1.0
   - 1-5% below HOD: 0.7
   - 5-10% below: 0.4
   - >10% below: 0.2
3. Compute in `warrior_engine_entry.py` scoring prep block:
```python
_hod_proximity = None
if hasattr(watched, 'recent_high') and watched.recent_high and watched.recent_high > 0:
    _hod_proximity = float((current_price - watched.recent_high) / watched.recent_high * 100)
```
4. Weight: redistribute from static factors. Suggested: catalyst 8% → 6%, pattern confidence 35% → 33%, giving HOD proximity 4%.

---

## Verification

```powershell
python scripts/gc_quick_test.py --all --diff
```

- If P&L change is within ±5% of $355K baseline → commit
- If significantly negative → investigate which cases regressed and report before committing
- Log the per-case diff for any changes
