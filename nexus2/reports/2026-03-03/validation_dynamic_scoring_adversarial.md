# Adversarial Validation: Dynamic Scoring Implementation

**Date:** 2026-03-03 12:20 ET  
**Agent:** Audit Validator  
**Source Reports:**
- `backend_status_dynamic_scoring.md`
- `backend_status_scoring_timing_fix.md`
**Handoff:** `handoff_validator_dynamic_scoring_adversarial.md`

---

## Challenge Summary

| # | Challenge | Result | Details |
|---|-----------|--------|---------|
| 1 | Zero extra computation (MACD reuse) | **PASS** | MACD cached from existing snapshot |
| 2 | All 6 dynamic factors populated | **PARTIAL** | 5/6 wired; volume expansion is always `None` |
| 3 | $0 P&L change expected | **PASS** | Math confirms no case near threshold; + timing means batch defaults to neutral |
| 4 | MACD scoring curve appropriate | **NEEDS_TUNING** | Step-function with only 6 buckets; 0→0.01 = 50% jump |

---

## Challenge 1: "Zero extra computation" — Is MACD reusing existing data?

**Claim:** `update_candidate_technicals()` caches MACD histogram from its existing snapshot (zero extra computation).

**Verification Command:** `Select-String -Path "C:\Dev\Nexus\nexus2\domain\automation\warrior_entry_helpers.py" -Pattern "macd|histogram|cached_macd" -Context 3,3`

**Actual Output (key lines):**
```
warrior_entry_helpers.py:349:        # Get MACD/EMA from full history
warrior_entry_helpers.py:350:        snapshot = tech.get_snapshot(symbol, all_candle_dicts, float(current_price))
...
warrior_entry_helpers.py:360:        # Cache MACD histogram for dynamic scoring (scoring runs BEFORE MACD gate)
warrior_entry_helpers.py:361:        if snapshot.macd_histogram is not None:
warrior_entry_helpers.py:362:            watched.cached_macd_histogram = float(snapshot.macd_histogram)
```

**Analysis:**
- Line 350: `snapshot = tech.get_snapshot(...)` uses `all_candle_dicts` — these are the same candles already fetched for EMA/VWAP computation (line 338-340: `all_candle_dicts = [{"high": c.high, ...} for c in candles]`).
- Line 362: Caches `snapshot.macd_histogram` onto `watched.cached_macd_histogram` — no new fetch, no new API call.
- The MACD histogram is a byproduct of the `get_snapshot()` call that was ALREADY happening for EMA tracking.

**Additionally verified — MACD gate also updates cache:**
```
warrior_entry_guards.py:254-255:
        # Update cached MACD histogram for scoring (keeps scoring in sync with gate)
        watched.cached_macd_histogram = float(histogram)
```
The MACD gate (which fetches its own 50-bar snapshot for higher fidelity) also updates the cache, so the scoring value is always the most recent available.

**Result:** ✅ **PASS** — Zero extra computation confirmed. MACD is piggy-backed on the existing `update_candidate_technicals()` snapshot.

---

## Challenge 2: Are ALL 6 dynamic factors flowing with real values?

**Verification Command:** `Select-String -Path "C:\Dev\Nexus\nexus2\domain\automation\warrior_engine_entry.py" -Pattern "_macd_histogram|_ema_trend|_reentry_count|_vwap_distance|_vol_expansion|_extension_pct" -Context 1,3`

### Per-Factor Analysis

| # | Factor | Source | Status | Evidence |
|---|--------|--------|--------|----------|
| 1 | `macd_histogram` | `watched.cached_macd_histogram` (line 500) → fallback `entry_snapshot` (line 504) | ✅ **REAL** | Populated by `update_candidate_technicals()` (60s) and MACD gate |
| 2 | `ema_trend` | `watched.is_above_ema_9` / `watched.is_above_ema_20` (lines 507-514) | ✅ **REAL** | Populated by `update_candidate_technicals()` (lines 352-358 in helpers) |
| 3 | `reentry_count` | `watched.entry_attempt_count` (line 536) | ✅ **REAL** | Incremented on each entry attempt; always populated |
| 4 | `vwap_distance_pct` | `watched.current_vwap` (lines 517-521) | ✅ **REAL** | Computed from cached VWAP updated every 60s |
| 5 | `price_extension_pct` | `watched.pmh` (lines 524-528) | ✅ **REAL** | PMH is set when candidate is added to watchlist |
| 6 | `volume_expansion` | `_vol_expansion_ratio` (line 531) | ❌ **ALWAYS NONE** | Set to `None`, never computed |

**Volume Expansion Deep Dive (line 530-533):**
```python
# Volume expansion: use check_volume_expansion result if candles available
_vol_expansion_ratio = None
# We calculate this lazily from entry_snapshot candle data or rely on
# the volume ratio from scanner as a proxy
```

This is a **dead factor**. The variable is initialized to `None`, and there is NO code path that sets it to any other value. The comment says "calculate this lazily" but no lazy calculation exists. When `None` is passed to `compute_volume_expansion_score(None)`, it returns `0.5` (neutral) — meaning this factor contributes `0.5 × 0.04 = 0.02` to every score identically.

**Impact:** 4% of total weight is a no-op. This doesn't cause incorrect behavior (it's neutral), but it's dead weight in the scoring system.

**Result:** ⚠️ **PARTIAL** — 5 of 6 factors are wired to real data. Volume expansion is a permanent no-op contributing a fixed 0.02 to every score.

---

## Challenge 3: Is $0 P&L change actually expected?

**Verification Command:** `Select-String -Path "C:\Dev\Nexus\nexus2\domain\automation\warrior_entry_scoring.py" -Pattern "MIN_SCORE_THRESHOLD" -Context 1,1`

**Actual Output:**
```
warrior_entry_scoring.py:62:MIN_SCORE_THRESHOLD = 0.40
```

**Math Check — Can dynamic factors push ANY case below 0.40?**

The backend status report claims the max negative delta is -0.01 (MACD weight 10% × worst case -0.1 delta from neutral). But we need to check ALL dynamic factors, not just MACD:

| Factor | Weight | Neutral (None) | Worst Case | Max Negative Delta |
|--------|--------|----------------|------------|-------------------|
| MACD | 10% | 0.5 | 0.4 (histogram ≥ -0.01, since gate blocks < -0.02) | -0.01 |
| EMA Trend | 8% | 0.5 | 0.2 (bearish) | -0.024 |
| Re-entry | 8% | 1.0 (count=0) | 0.15 (count≥3) | -0.068 |
| VWAP | 6% | 0.5 | 0.0 (well below) | -0.03 |
| Volume Expansion | 4% | 0.5 | 0.5 (ALWAYS None) | 0.0 |
| Price Extension | 4% | 0.5 | 0.2 (very extended) | -0.012 |
| **Total worst case** | | | | **-0.134** |

**However**, in batch tests specifically:
1. `entry_attempt_count` = 0 for first entries (re-entry decay = 1.0, delta = 0.0)
2. After the timing fix, MACD *should* be populated from `cached_macd_histogram`
3. EMA/VWAP *should* be populated from `update_candidate_technicals()`

**The real question is: does `update_candidate_technicals()` run BEFORE `check_entry_triggers()`?**

Looking at the flow — `update_candidate_technicals()` runs on a 60-second cycle. For batch tests (single-pass simulation), by the time a pattern triggers, technicals MAY or MAY NOT have been updated depending on sim clock timing. The backend status report acknowledges this:

> "EMA/VWAP data updates every 60s via `update_candidate_technicals()`, may not be set for first-entry-cycle"

**So $0 is expected for batch tests because:**
1. On first entry cycle, many factors default to `None` → 0.5 (neutral)
2. MACD from `cached_macd_histogram` may be populated (timing fix), but the gate already filters bad values
3. Re-entry count = 0 (first attempt always in batch)
4. Even with all factors populated, the max negative delta (-0.134) would need a base score in the 0.40–0.534 range to push below threshold — and the test shows no cases sit there

**Result:** ✅ **PASS** — $0 batch change is expected. The combination of neutral defaults and gate pre-filtering means dynamic scoring doesn't change batch outcomes. This is structurally correct BUT also means **the claimed "55/45 dynamic split" is mostly theoretical in batch mode.**

---

## Challenge 4: MACD Scoring Curve Sensitivity

**Verification:** `view_file warrior_entry_scoring.py` lines 70-97

**Actual Implementation:**
```python
def compute_macd_score(histogram: Optional[float]) -> float:
    if histogram is None:
        return 0.5  # Unknown = neutral
    if histogram >= 0.3:
        return 1.0  # Very strong momentum
    elif histogram >= 0.1:
        return 0.8  # Strong
    elif histogram >= 0.01:
        return 0.6  # Moderate positive
    elif histogram >= -0.01:
        return 0.4  # Near zero (transitional)
    elif histogram >= -0.1:
        return 0.2  # Weakening
    else:
        return 0.0  # Fading/negative
```

**Analysis:**
- This is a **step function** with only 6 discrete values (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
- The transition from `histogram = 0.00` (score = 0.4) to `histogram = 0.01` (score = 0.6) is a **50% jump** (+0.2 absolute)
- For low-priced stocks ($2-5), typical MACD histograms range from -0.05 to +0.05 — meaning most entries land in the 0.4 (near-zero) or 0.6 (moderate positive) bucket
- For higher-priced stocks ($10+), histograms can easily reach 0.1-0.5, but those also have wider swings
- The step function means there's NO differentiation within buckets: histogram = 0.02 and histogram = 0.09 both score 0.6

**Is this appropriate?** The coarse bucketing is acceptable for a 10% weight factor. The discontinuity at 0.00/0.01 is slightly concerning but with 10% weight, the actual score impact is only `0.2 × 0.10 = 0.02` — a 2% total score shift. This is unlikely to cross the 0.40 threshold for any reasonable entry.

**However**, the bucketing ignores that MACD histogram scale varies by stock price. A $3 stock with histogram = 0.01 and a $50 stock with histogram = 0.01 have very different momentum contexts. A normalized approach (histogram / ATR or histogram / price) would be more robust.

**Result:** ⚠️ **NEEDS_TUNING** — The step function works but is coarse. The 0.00→0.01 discontinuity and price-insensitive bucketing are sub-optimal. Not blocking, but worth improving.

---

## Additional Findings

### EMA Hard Gate Removal — Verified ✅

**File:** `warrior_entry_guards.py:134-137`
```python
# NOTE: EMA trend is handled by scoring penalty (not a hard gate).
# The MACD gate + falling knife guard already block truly dead trends.
# A hard EMA gate was tested but caused -$34K regression by blocking
# profitable entries where EMAs hadn't caught up to a fresh move.
```
EMA gate is properly removed — only a comment remains. The -$34K regression documented in the status report is consistent with this comment.

### WatchedCandidate Fields — Verified ✅

**File:** `warrior_engine_types.py:196-201`
```python
current_ema_20: Optional[Decimal] = None     # line 196
is_above_ema_20: bool = False                # line 200
cached_macd_histogram: Optional[float] = None # line 201
```
All three new fields exist on `WatchedCandidate` with correct types and defaults.

### Weight Sum Verification ✅

From `score_pattern()` lines 321-336:
```
0.35 + 0.10 + 0.08 + 0.04 + 0.10 + 0.08 + 0.08 + 0.06 + 0.04 + 0.04 + 0.015 + 0.015 = 1.00
```
Weights sum to exactly 1.00 (confirmed).

---

## Overall Assessment

### Is the implementation actually exercising dynamic scoring?

**In batch tests: Mostly NO.** The timing of `update_candidate_technicals()` (60s cycle) and the neutral defaults mean most factors fall through to 0.5 on first pass. The MACD timing fix helps, but the volume expansion factor is permanently dead.

**In LIVE mode: YES, partially.** With continuous technical updates:
- ✅ MACD, EMA trend, VWAP distance, and price extension WILL produce real differentiated scores
- ✅ Re-entry decay WILL penalize repeated attempts
- ❌ Volume expansion will ALWAYS be 0.5 (no-op)

### Is it a no-op dressed as a feature?

**No, but it's also not fully operational:**
- 5 of 6 factors are properly wired
- The scoring function is correctly structured
- In live mode it WILL differentiate entries
- But volume expansion (4% weight) is dead code
- And batch tests cannot exercise the system meaningfully

### Quality Rating: **MEDIUM**

**Actionable issues (for coordinator):**
1. **Volume expansion is dead** — either wire `_vol_expansion_ratio` to actual data or remove the factor and redistribute 4% weight
2. **MACD curve is price-insensitive** — consider normalizing by price or ATR for better discrimination across stock prices
3. **Batch test blind spot** — the 60s technical update cycle means batch tests won't exercise scoring; consider pre-populating technicals for test cases

---

*Validator: Audit Validator Agent | Method: Adversarial code trace, verified via Select-String commands and view_file*
