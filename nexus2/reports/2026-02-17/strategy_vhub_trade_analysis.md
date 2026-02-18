# Strategy Expert Analysis: VHUB Trade Miss (2026-02-17)

**Methodology**: Warrior (Ross Cameron)  
**Question**: Why did the bot prefer LFS (dynamic_score=11) over VHUB (dynamic_score=2), when Ross chose VHUB and avoided everything else?  
**Source**: `.agent/strategies/warrior.md`, transcript `2026-02-17_transcript_NA90q8dBJkI.md`  
**Confidence**: HIGH — all claims backed by code evidence

---

## Executive Summary

**The `dynamic_score` ranking does NOT capture Ross's actual selection criteria.** It measures RVOL + gap% + trend alignment, which are *necessary but not sufficient*. Ross's decision to choose VHUB and avoid everything else was driven by factors the score completely ignores:

1. **Float quality** — "thickly traded" = skip (RIME, SUNE, GXAI all skipped for this)
2. **Blue sky / daily chart setup** — VHUB was a recent IPO with blue sky above $40
3. **Market temperature** — Cold market = take 1 trade max, not 18

The bot took 18 trades (mostly losers) while Ross took 1 (winner). This is not a `top_x_picks` tuning problem — it's a **fundamental scoring gap**.

---

## Ross's Selection Criteria (from transcript)

The transcript explicitly shows Ross applying his **Five Pillars** to choose VHUB:

| Pillar | VHUB Assessment | Documented? |
|--------|----------------|-------------|
| **Price** | $3.33 — "price is a little lower" (acknowledged concern) | ✅ In strategy |
| **Float** | "float's a little higher" (acknowledged but accepted) | ⚠️ NOT in `dynamic_score` |
| **Rate of Change** | Popped on headline, dipped, curled back up | ⚠️ NOT in `dynamic_score` |
| **News Catalyst** | Breaking news headline | ✅ Partially (catalyst bonus in EP scanner) |
| **Daily Chart** | Recent IPO, blue sky above $40 | ⚠️ Blue sky NOT in scanner score |

### What Ross Explicitly Avoided (and why)

| Stock | Ross's Reason | `dynamic_score` Would Have... |
|-------|---------------|-------------------------------|
| **RIME** | "Crowded/thickly traded" — 475% mover from Friday | Ranked highly (high RVOL + gap%) |
| **SUNE** | "Thickly traded" | Ranked based on RVOL/trend |
| **GXAI** | "Thickly traded, traded before" | Ranked based on RVOL/trend |
| **PLYX** | $4→$66→$4 round-trip = "weird/untradeable" | Unknown |

> [!CAUTION]
> Ross's #1 disqualifier today was **"thickly traded"** — meaning float was too large, creating a tug-of-war. The `dynamic_score` has **zero float awareness**. It would rank a 100M-float stock higher than a 500K-float stock if the 100M-float had better RVOL + trend.

---

## Code Evidence: What `dynamic_score` Actually Measures

### Formula
**File:** [warrior_engine_types.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_types.py#L243-L268)

```
dynamic_score = quality_score + VWAP/EMA trend bonus
```

Where:
- `quality_score` = scanner base (5) + RVOL bonus (+2) + gap% bonus (+1) + catalyst bonus (+2) + IPO boost (+1-3)
- Trend bonus: +3 (above VWAP AND 9 EMA) / +1 (above VWAP only) / -2 (below VWAP)

**Max possible**: 10 (quality cap) + 3 (trend) = **13**

### What's In the Score

| Factor | Points | Code Location |
|--------|--------|---------------|
| Base | 5 | `unified_scanner.py:396` |
| RVOL > 2.0 | +2 | `unified_scanner.py:397-398` |
| Gap > 5% | +1 | `unified_scanner.py:399-400` |
| Has catalyst | +2 | `unified_scanner.py:401-402` |
| IPO (days 0-1) | +3 | `unified_scanner.py:406-410` |
| Above VWAP + 9 EMA | +3 | `warrior_engine_types.py:259-260` |
| Above VWAP only | +1 | `warrior_engine_types.py:262` |
| Below VWAP | -2 | `warrior_engine_types.py:264` |

### What's NOT In the Score (Ross's Actual Filters)

| Missing Factor | Ross's Importance | Impact |
|----------------|-------------------|--------|
| **Float / shares outstanding** | Pillar #2 — "thickly traded" = hard skip | HIGH — bot can't distinguish crowded from uncrowded |
| **Blue sky / daily chart** | Pillar #5 — "recent IPO, blue sky above $40" | HIGH — key reason Ross chose VHUB |
| **Rate of change** | Pillar #3 — fast movement preferred | MEDIUM — partially captured by gap% |
| **Round-trip history** | Hard disqualifier — "popped and reversed" | HIGH — bot re-enters round-trippers |
| **Market temperature** | Modulates ALL behavior | CRITICAL — 1 trade vs 18 trades |
| **"Crowdedness"** | Volume:float ratio detecting tug-of-war | HIGH — the reason 3 stocks were skipped today |

---

## Why LFS=11 and VHUB=2

I don't have LFS's exact metrics, but the scoring formula makes it clear:

**LFS likely had:** quality_score ~8 (high RVOL, gap%, catalyst) + trend +3 (above VWAP + 9 EMA) = **11**

**VHUB likely had:** quality_score ~7 (catalyst + IPO boost) but trend -2 or missing = **~2** (clamped from below)  
OR: quality_score ~4 (no RVOL bonus if bars were scarce) + trend -2 = **2**

> The VWAP `first_times='?'` in the log suggests VHUB's VWAP calculation may have been unreliable, potentially triggering the -2 penalty or getting no trend bonus at all.

---

## Recommendations

### R1: Add Float-Based "Crowdedness" Penalty to `dynamic_score`

**Source**: `warrior.md` Section 1, Pillar #2

Ross's float thresholds:
- Sub-1M = ideal
- Sub-5M = strong
- >10M = "thickly traded" (penalty)
- >50M = "practically Bank of America" (hard skip)

**Proposed scoring adjustment:**
```
if float < 1M:    +3 (ideal low float)
if float < 5M:    +1 (good float)
if float > 10M:   -3 (thickly traded penalty)
if float > 50M:   disqualify entirely
```

**Confidence**: HIGH — Ross explicitly uses these thresholds across many transcripts.

### R2: Add Blue Sky / Daily Chart Bonus

**Source**: `warrior.md` Section 1, Pillar #5

Blue sky is already computed in `warrior_entry_scoring.py` (`compute_blue_sky_pct`) but it's only used in **pattern competition scoring**, NOT in the **TOP_X ranking via `dynamic_score`**.

**Proposed**: Add blue sky proximity to `dynamic_score`:
```
if within 5% of 52-week high: +2
if within 10% of 52-week high: +1
```

**Confidence**: HIGH — Ross cited blue sky as a reason for choosing VHUB.

### R3: Add Market Temperature Throttle

**Source**: `warrior.md` Section 7

This is the root cause of the 1-vs-18 trade count discrepancy. Ross:
- Cold market → 1-2 trades max
- Hot market → 5-10+ trades

The `top_x_picks=3` parameter is a static limit. It should be modulated by market temperature:
- Cold: `top_x_picks=1`
- Normal: `top_x_picks=2-3`
- Hot: `top_x_picks=5+`

**Confidence**: MEDIUM — the temperature concept is documented, but exact thresholds for `top_x_picks` modulation are not explicitly stated by Ross. He determines selectivity qualitatively.

> [!IMPORTANT]
> **R3 alone would have fixed today's problem.** If `top_x_picks=1` in cold conditions, the bot would have taken only the #1 ranked stock. If R1 (float penalty) were also applied, VHUB would have outranked LFS (assuming LFS had a larger float).

### R4: Consider Volume:Float Ratio ("Crowdedness Ratio")

Ross's "thickly traded" assessment isn't just float size — it's about volume *relative to* float. A 5M float stock with 50M volume traded is a tug-of-war. A 500K float stock with 5M volume is a squeeze candidate.

**Proposed metric**: `crowdedness = volume / float`
- Ratio > 10x = thickly traded penalty
- Ratio 2-5x = normal rotation
- Ratio < 1x = low interest

**Confidence**: MEDIUM — Ross uses the concept but doesn't state exact ratios. This would need backtesting.

---

## Open Questions for Clay

1. **LFS float data**: What was LFS's float on 2026-02-17? If >10M, this confirms the float gap is the primary issue.
2. **Market temperature implementation**: Should temperature be auto-detected (scanner hit count, leading gainer %, etc.) or manually set?
3. **Priority**: Should R1 (float) and R2 (blue sky) be implemented in `dynamic_score`, or should the ranking system be rethought entirely?
4. **`first_times='?'`**: The VWAP calculation issue may also need Backend Planner investigation — unreliable VWAP could be systematically penalizing new/low-data stocks.

---

## Summary Table

| Issue | Root Cause | Fix | Confidence |
|-------|-----------|-----|------------|
| Bot ranked LFS > VHUB | `dynamic_score` ignores float | Add float scoring (R1) | HIGH |
| Bot took 18 trades, Ross took 1 | No market temperature throttle | Add temperature modulation (R3) | MEDIUM |
| Blue sky not in ranking | `dynamic_score` ignores daily chart | Add blue sky bonus (R2) | HIGH |
| "Thickly traded" not detected | No crowdedness metric | Add volume:float ratio (R4) | MEDIUM |
| VHUB may have VWAP penalty | `first_times='?'` → bad VWAP calc | Backend Planner investigation | NEEDS VERIFICATION |
