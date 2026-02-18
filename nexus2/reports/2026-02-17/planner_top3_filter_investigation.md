# Backend Planner Investigation: TOP_3 Filter & dynamic_score

**Date:** 2026-02-17  
**Handoff:** `handoff_vhub_trade_miss_investigation.md` (Q2)  
**Investigator:** Backend Planner Agent

---

## Executive Summary

VHUB was blocked by the `TOP_3_ONLY` filter because its `dynamic_score` was 2 while LFS had 11. The root cause is that `dynamic_score` is dominated by the **static `quality_score`** from the scanner (which rewards float, RVOL, gap%, catalyst, freshness, price sweet spot, etc.) and only adds a small VWAP/EMA trend bonus (+3/+1/-2). The scoring system has **no awareness of**: blue sky status, recent IPO, liquidity quality ("thickly traded"), or Ross's selectivity preferences.

The `first_times=['?','?','?']` anomaly is **benign** — it's a diagnostic log artifact from bars lacking a `.time` attribute in LIVE mode.

---

## Q2.1: How is `dynamic_score` computed?

### Finding: `dynamic_score` is a computed property on `WatchedCandidate`
**File:** `warrior_engine_types.py:243-268`  
**Code:**
```python
@property
def dynamic_score(self) -> int:
    base_score = getattr(self.candidate, 'quality_score', 0) or 0
    
    # Trend bonus (only if we have VWAP data)
    if self.current_vwap is not None and self.current_price is not None:
        if self.is_above_vwap:
            if self.is_above_ema_9:
                base_score += 3  # Strong trend: above both VWAP and 9 EMA
            else:
                base_score += 1  # Moderate: above VWAP but below 9 EMA
        else:
            base_score -= 2  # Weak/fading: below VWAP
    
    return max(base_score, 0)  # Don't go negative
```

### Formula:
```
dynamic_score = quality_score + trend_bonus
    where trend_bonus:
        +3 if above VWAP AND above 9 EMA
        +1 if above VWAP only
        -2 if below VWAP
        +0 if no VWAP data available
```

### VWAP/EMA data is updated in `update_candidate_technicals()`
**File:** `warrior_entry_helpers.py:258-374`  
**Called from:** `warrior_engine_entry.py:395-402` (throttled to 60s intervals)

---

## Q2.2: What factors contribute to `quality_score`?

### Finding: `quality_score` is a property on `WarriorCandidate`
**File:** `warrior_scanner_service.py:306-394`  
**Code:**
```python
@property
def quality_score(self) -> int:
    score = 0
    
    # Float quality (3 points max)
    if float_shares < 10M:    score += 3
    elif float_shares < 20M:  score += 2
    elif float_shares < 50M:  score += 1
    
    # RVOL quality (2 points max)
    if rvol >= 5x:  score += 2
    elif rvol >= 3x: score += 1
    
    # Gap quality (2 points max)
    if gap >= 10%:  score += 2
    elif gap >= 5%: score += 1
    
    # Catalyst quality (2 points max)
    if catalyst == "earnings": score += 2
    elif catalyst == "news":   score += 1
    
    # Catalyst freshness (3 points max) — Ross's flame colors
    if hours_old <= 2:   score += 3  # 🔴 Red flame
    elif hours_old <= 12: score += 2  # 🟠 Orange
    elif hours_old <= 24: score += 1  # 🟡 Yellow
    
    # Price sweet spot (1 point)
    if $5 <= price <= $15: score += 1
    
    # Former runner (1 point)
    if is_former_runner: score += 1
    
    # Hard-to-borrow (1 point)
    if hard_to_borrow: score += 1
    
    # Reverse split (2 points)
    if is_reverse_split: score += 2
    
    return min(score, 16)  # Max 16
```

### Score Component Summary

| Component | Max Points | What It Measures |
|-----------|-----------|-----------------|
| Float quality | 3 | Low float = more volatile |
| RVOL | 2 | Volume relative to average |
| Gap % | 2 | Premarket gap size |
| Catalyst type | 2 | earnings vs news vs none |
| Catalyst freshness | 3 | Hours since catalyst |
| Price sweet spot | 1 | $5-$15 range |
| Former runner | 1 | History of big moves |
| HTB | 1 | Short squeeze potential |
| Reverse split | 2 | Proactive bonus |
| **Subtotal** | **17** | (capped at 16) |
| Trend bonus | +3/-2 | VWAP/EMA alignment |
| **dynamic_score max** | **19** | |

---

## Q2.3: Why LFS=11, VHUB=2?

### Hypothesis (needs runtime verification):

**LFS likely scored high because:**
- Low float (≤10M) → +3
- High RVOL (≥5x) → +2
- Large gap% (≥10%) → +2
- Fresh catalyst → +2 or +3
- Above VWAP + 9 EMA → +3
- **Total: ~15 dynamic**

**VHUB likely scored low because:**
- VHUB at $3.33 is **below the $5 price sweet spot** → +0
- catalyst_type may have been "news" → +1
- Float/RVOL may have been moderate
- **VWAP data may have been missing** (see Q2.4 — first_times='?') → no trend bonus (+0)
- **Total: ~2 dynamic** (matches the log)

### Critical Missing Factors

The `quality_score` does **NOT** consider:

| Missing Factor | Ross's Weight | Impact on VHUB |
|----------------|---------------|----------------|
| **Blue sky** (near 52w high) | Very high priority | VHUB was near all-time highs — should boost |
| **Recent IPO** | Mentioned by Ross for VHUB | IPO boost exists in `unified_scanner.py` EP path but NOT in `warrior_scanner_service.py` |
| **Liquidity quality** | Ross avoided "thickly traded" | Not scored — bot doesn't penalize crowded names |
| **Chart cleanliness** | Ross likes "clean" charts | Not scored |
| **Market regime** | Ross took only 1 trade in cold market | Bot has no market regime awareness |

> [!WARNING]
> IPO boost code exists in `unified_scanner.py:406-410` for EP signals, but `WarriorCandidate.quality_score` (used by the Warrior bot in LIVE mode) does NOT include IPO boost. This is a gap.

---

## Q2.4: Where is `top_x_picks` configured?

### Finding: Hardcoded default, no API override
**File:** `warrior_engine_types.py:83-84`  
**Code:**
```python
# top_x_picks: how many of the highest-scoring candidates can enter (1 = Ross style, 0 = disabled)
top_x_picks: int = 3  # Only top X highest-scoring candidates can enter (0 = no limit)
```

**API override check:** Searched `nexus2/api/` for `top_x_picks` — **no results**. This value is never exposed via API and cannot be changed at runtime.

**Related:** `min_entry_score: int = 6` — a separate minimum quality_score gate checked at `warrior_entry_guards.py:84-87`.

---

## Q2.5: Why VWAP `first_times` show '?'

### Finding: Benign diagnostic artifact from missing `.time` attribute
**File:** `warrior_vwap_utils.py:227`  
**Code:**
```python
sample_times = [getattr(c, 'time', '?') for c in candles[:3]]
```

**Root cause:** In LIVE mode, Alpaca bars are returned as `Bar` objects that don't have a `.time` attribute (they use `.timestamp` as a full datetime). The `getattr(c, 'time', '?')` falls back to `'?'` for display only.

**Impact: NONE on VWAP calculation.** The actual VWAP filtering happens at lines 189-216 where bars without `.time` are **included** (not excluded):
```python
bar_time = getattr(c, 'time', '') or ''
if not bar_time:
    # No timestamp — include to avoid dropping data
    today_candles.append(c)
    no_time_count += 1
    continue
```

**However**, this means **no session filtering occurs for LIVE bars**. All 487 bars passed the filter because none had `.time` and all were auto-included. This is by design for Alpaca (which returns only today's bars), but the log looks confusing.

### Impact on VHUB's dynamic_score

The VWAP value itself WAS computed (from the included bars), so the trend bonus in `dynamic_score` should still have applied. The `first_times='?'` is not the cause of VHUB's low score.

---

## Change Surface (if implementation is needed)

### Identified Gaps

| # | Gap | File | Potential Fix |
|---|-----|------|--------------|
| 1 | No IPO boost in `WarriorCandidate.quality_score` | `warrior_scanner_service.py:306-394` | Add IPO boost from `ipo_service` (same as `unified_scanner.py:406-410`) |
| 2 | No blue sky score boost in `quality_score` | `warrior_scanner_service.py` | Add blue sky proximity bonus (data available from FMP) |
| 3 | `top_x_picks` not tunable at runtime | `warrior_engine_types.py:84` | Expose via settings API or config endpoint |
| 4 | No "liquidity quality" negative score | `warrior_scanner_service.py` | Penalize high-float/high-volume "thickly traded" names |
| 5 | Price sweet spot too narrow ($5-$15) | `warrior_scanner_service.py:384` | VHUB at $3.33 gets NO price bonus. Ross clearly trades $2-4 stocks |

### Recommended Priority

1. **Fix #5** (price sweet spot) — easiest, immediate impact. Widen to $2-$20 or recalibrate tiers.
2. **Fix #1** (IPO boost) — already implemented elsewhere, just needs porting.
3. **Fix #3** (runtime tuning) — important for experimentation.
4. **Fix #2** (blue sky) — data available, moderate implementation.
5. **Fix #4** (liquidity penalty) — requires strategy clarification with Strategy Expert.

---

## Wiring Checklist (for Backend Specialist)

If strategy decision is to improve scoring:

- [ ] Add IPO boost to `WarriorCandidate.quality_score` (port from `unified_scanner.py:406-410`)
- [ ] Widen price sweet spot range ($2-$20) or add intermediate tiers
- [ ] Expose `top_x_picks` via warrior settings API
- [ ] Add blue sky proximity bonus to `quality_score`
- [ ] (Pending strategy decision) Add liquidity quality penalty

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Widening price sweet spot may increase trades in illiquid sub-$5 stocks | Medium | Keep min_price filter in scanner |
| IPO boost may overweight recent IPOs in ranking | Low | Port exact same logic as unified_scanner |
| Blue sky data may not always be available | Low | Bonus is additive, absence = no change |
| Changing scoring may alter all existing batch test results | High | Run full batch test before/after comparison |
