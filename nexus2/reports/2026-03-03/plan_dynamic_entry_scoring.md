# Implementation Plan: Dynamic Entry Scoring

Add price-action-aware factors to `score_pattern()` so the Warrior Bot can distinguish fresh momentum breakouts from fading re-entries. Currently 85% of the score comes from static scanner metadata. The bot scored RUBI identically (~0.793) across 3 entries spanning 90 minutes despite the setup visibly deteriorating.

## User Review Required

> [!IMPORTANT]
> **Weight rebalancing** changes the scoring formula that drives ALL entries. This could affect batch test P&L, but the research shows scoring is currently vestigial (everything scores ~0.79, threshold is 0.40), so meaningful regression is unlikely.

> [!IMPORTANT]
> **Cooldown interaction**: Clay noted the re-entry cooldown (`live_reentry_cooldown_minutes`) may become redundant once scoring properly degrades re-entries. Recommend keeping the cooldown but reducing to 1-2 min (anti-jitter) after this ships and is validated. Not removing it in this change.

---

## Proposed Changes

### Entry Scoring

#### [MODIFY] [warrior_entry_scoring.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_scoring.py)

Add 5 new parameters to `score_pattern()` and rebalance weights:

```python
def score_pattern(
    # EXISTING (static)
    pattern, volume_ratio, pattern_confidence,
    catalyst_strength, spread_pct, level_proximity, time_score,
    blue_sky_pct=None,
    # NEW (dynamic, all optional with backward-compatible defaults)
    macd_histogram: float = None,      # P0: from entry_snapshot
    reentry_count: int = 0,            # P0: from watched.entry_attempt_count
    ema_trend: str = None,             # P0: "strong"/"weakening"/"bearish" from 9/20 EMA
    vwap_distance_pct: float = None,   # P1: (price - vwap) / vwap * 100
    volume_expansion: float = None,    # P1: current bar vol / avg vol ratio
    price_extension_pct: float = None, # P2: (price - pmh) / pmh * 100
)
```

New weight distribution (45% static / 55% dynamic):

| Factor | Weight | Source | Dynamic? |
|--------|--------|--------|----------|
| Pattern confidence | 20% (↓50%) | Hard-coded per trigger | Static |
| MACD momentum | 12% (NEW) | `entry_snapshot.macd_histogram` | ✅ |
| EMA trend (9/20) | 10% (NEW) | `watched.is_above_ema9/ema20` | ✅ |
| Re-entry decay | 10% (NEW) | `watched.entry_attempt_count` | ✅ |
| Volume ratio (scanner) | 10% (↓20%) | Scanner RVOL | Static |
| Catalyst strength | 10% (↓15%) | Scanner metadata | Static |
| VWAP position | 8% (NEW) | `watched.current_vwap` | ✅ |
| Volume expansion | 5% (NEW) | `check_volume_expansion()` | ✅ |
| Price extension | 5% (NEW) | `watched.pmh` vs price | ✅ |
| Time score | 5% (keep) | Clock | Slow |
| Level proximity + spread | 5% (merged) | Misc | Slow |

Add scoring helper functions:
- `compute_macd_score(histogram)` → 0.0-1.0
- `compute_ema_trend_score(above_ema9, above_ema20)` → 1.0 (above both), 0.5 (above 20 only), 0.2 (below both)
- `compute_reentry_decay(count)` → 1.0, 0.6, 0.3 for attempts 0,1,2+
- `compute_vwap_score(distance_pct)` → 0.0-1.0
- `compute_volume_expansion_score(ratio)` → 0.0-1.0
- `compute_extension_score(pct)` → 0.0-1.0

---

#### [MODIFY] [warrior_engine_entry.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py)

In `check_entry_triggers()` around line 500, modify `add_candidate()` to pass dynamic data through to `score_pattern()`:

1. **Before** pattern detection loop: capture the entry snapshot data that's already computed by `update_candidate_technicals()` and store MACD, VWAP, volume expansion values as local variables.

2. **In** `add_candidate()` closure: pass these values through to `score_pattern()`:
```python
def add_candidate(trigger, confidence=0.7):
    if trigger:
        score = score_pattern(
            # existing args...
            macd_histogram=_macd_histogram,
            reentry_count=watched.entry_attempt_count,
            ema_trend=_ema_trend,
            vwap_distance_pct=_vwap_distance_pct,
            volume_expansion=_vol_expansion_ratio,
            price_extension_pct=_extension_pct,
        )
```

3. **Compute** the dynamic values once per symbol per cycle (not per pattern):
```python
# MACD: from cached snapshot (throttled to 60s updates)
_macd_histogram = None
if hasattr(watched, 'entry_snapshot') and watched.entry_snapshot:
    _macd_histogram = watched.entry_snapshot.macd_histogram

# VWAP: from cached technicals
_vwap_distance_pct = None
if hasattr(watched, 'current_vwap') and watched.current_vwap and watched.current_vwap > 0:
    _vwap_distance_pct = float((current_price - watched.current_vwap) / watched.current_vwap * 100)

# EMA trend: from cached technicals (Ross uses 9 and 20 EMA)
_ema_trend = None
if hasattr(watched, 'is_above_ema9') and hasattr(watched, 'is_above_ema20'):
    if watched.is_above_ema9 and watched.is_above_ema20:
        _ema_trend = "strong"
    elif watched.is_above_ema20:
        _ema_trend = "weakening"
    else:
        _ema_trend = "bearish"

# Price extension from PMH
_extension_pct = float((current_price - watched.pmh) / watched.pmh * 100) if watched.pmh > 0 else None

# Re-entry count
# watched.entry_attempt_count already tracked
```

4. **Volume expansion**: This needs candle data which is already fetched in the MACD gate. We'll use `watched.entry_snapshot` which has the candle data, OR compute lazily and store on `watched`.

---

---

### Guard Changes

#### [MODIFY] [warrior_entry_guards.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py)

**Hybrid EMA Gate:** Add a hard gate in `check_entry_guards()` that blocks entry when price is below BOTH 9 AND 20 EMA. This is separate from the existing falling knife guard (which requires MACD negative too).

```python
# HARD GATE: Below both 9 and 20 EMA = uptrend is dead
# This is INDEPENDENT of MACD — even barely positive MACD doesn't save it
# Note: below 9 EMA but above 20 EMA is handled by scoring penalty, not a gate
if hasattr(watched, 'is_above_ema9') and hasattr(watched, 'is_above_ema20'):
    if not watched.is_above_ema9 and not watched.is_above_ema20:
        reason = f"EMA GATE - price below both 9 EMA and 20 EMA (trend over)"
        # log + return blocked
```

This tightens the gap where falling knife guard allows entries below both EMAs when MACD is barely positive.

---

### No Other Files Modified

No changes to:
- `warrior_entry_patterns.py` (pattern detection unchanged)
- `warrior_types.py` (no new settings needed — weights are in scoring code)
- `warrior_monitor.py` / `warrior_monitor_exit.py` (exit logic unchanged)

---

## Verification Plan

### Automated Tests

**1. Unit tests for scoring (NEW)**

Create `nexus2/tests/domain/test_warrior_entry_scoring.py`:
- Test `score_pattern()` with all-static inputs (backward compat)
- Test MACD scoring: strong (+0.3) vs weak (+0.01) vs fading (-0.01)
- Test re-entry decay: 0th, 1st, 2nd, 3rd attempt
- Test VWAP scoring: above by 5%, at VWAP, below VWAP
- Test volume expansion: 10x, 3x, 1x, 0.5x
- Test price extension: at PMH, +5%, +15%, +30%
- Test combined: "fresh breakout" scenario vs "fading re-entry" scenario, verify score difference

```powershell
python -m pytest nexus2/tests/domain/test_warrior_entry_scoring.py -v
```

**2. Batch test regression**

Run the full 39-case batch test and compare against the $355,039 baseline:

```powershell
python scripts/gc_quick_test.py --all --diff
```

Expected outcome: P&L should be **within 5% of baseline** ($337K-$373K). If significantly different, examine per-case breakdown for which cases changed and why.

**3. Targeted case test — RUBI-like scenarios**

Pick 2-3 cases that have known re-entry behavior (check for cases where the bot entered the same stock multiple times):

```powershell
python scripts/gc_quick_test.py --case ross_mnts_20260209 --verbose
python scripts/gc_quick_test.py --case ross_batl_20260302 --verbose
```

These cases (MNTS, BATL-Mar2) are known losers — verify that late re-entries now score lower.

### Manual Verification

After deploying to VPS, during the next live PAPER session:
1. Watch server logs for scoring output — confirm re-entries show **lower scores** than first entries
2. Confirm at least one re-entry is blocked by falling below 0.40 threshold
3. Compare to today's session (18 trades, RUBI 3x, identical 0.793 scores)
