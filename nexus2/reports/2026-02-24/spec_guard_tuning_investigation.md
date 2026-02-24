# Guard Tuning Investigation Spec

**Date:** 2026-02-24  
**Agent:** Backend Planner  
**Strategy Reference:** `.agent/strategies/warrior.md`  
**Builds on:** Feb 23 reports (`spec_guard_effectiveness_analysis.md`, `spec_reentry_loss_guard_tuning.md`)

---

## 1. A/B Test Results: Guards ON vs OFF

### Summary

| Metric | Guards ON | Guards OFF | Delta |
|--------|-----------|------------|-------|
| **Bot P&L** | **$161,116** | $151,170 | **+$9,946** |
| Ross P&L | $433,000 | $433,000 | (same) |
| Capture | **37.2%** | 34.9% | **+2.3%** |

> [!IMPORTANT]
> **Guards are now NET POSITIVE by ~$10K.** This is a dramatic shift from Feb 23, when guards-ON was $136,993 vs guards-OFF at $151,170 (net-negative by -$14K). The graduated reentry fix (`max_reentry_attempts=3`) has improved guards-ON P&L by **+$24K**.

### Impact Distribution

- **10 cases** where guards HURT (guards blocked profitable entries): **+$38K lost opportunity**
- **10 cases** where guards HELP (guards prevented losses): **-$48K saved**
- **15 cases** NEUTRAL (< $50 difference)

### Per-Case Comparison (sorted by guard impact)

| Case | Guards ON | Guards OFF | Delta | Ross | Blocks | Impact |
|------|----------|-----------|-------|------|--------|--------|
| BATL 0127 | $23,293 | $35,689 | **+$12,396** | $0 | 3,609 | HURT |
| BCTX 0127 | $4,353 | $10,275 | **+$5,922** | $4,500 | 208 | HURT |
| BATL 0126 | $7,740 | $13,416 | **+$5,676** | $0 | 3,609 | HURT |
| MLEC 0213 | -$2,997 | $1,902 | **+$4,899** | $43,000 | 950 | HURT |
| TNMG 0116 | $2,152 | $6,336 | **+$4,184** | $2,102 | 771 | HURT |
| LRHC 0130 | $869 | $3,525 | **+$2,656** | $31,077 | 66 | HURT |
| ... | ... | ... | ... | ... | ... | ... |
| ROLR 0114 | $61,566 | $51,462 | **-$10,104** | $85,000 | 268 | HELP |
| VERO 0116 | $19,072 | $3,088 | **-$15,984** | $3,485 | 255 | HELP |

The full case table is available in `guard_ab_analysis.json`.

---

## 2. Per-Guard-Type Analysis

### Counterfactual Analysis from Guards-ON Run

| Guard Type | Blocks | Correct | Missed | Accuracy | Net Impact | Cases |
|-----------|--------|---------|--------|----------|-----------|-------|
| **macd** | 6,340 | 4,035 | 2,305 | 63.6% | -$854 | 13 |
| **reentry_loss** | 3,311 | 1,853 | 1,458 | 56.0% | -$712 | 6 |
| **position** | 2,448 | 1,385 | 1,063 | 56.6% | -$12 | 8 |
| sim_cooldown | 66 | 51 | 15 | 77.3% | -$3 | 2 |
| pending_entry | 6 | 0 | 6 | 0.0% | $0 | 1 |
| **TOTAL** | **12,171** | **7,324** | **4,847** | **60.2%** | **-$1,580** |

> [!NOTE]
> The net impact column shows the *counterfactual estimated* savings per guard. The actual A/B delta (+$9,946) is larger because blocking one entry cascades into different subsequent entries. Counterfactual is per-block; A/B captures systemic effects.

### Guard Rankings by Problem Severity

| Rank | Guard | Problem | Evidence |
|------|-------|---------|----------|
| 1 | **MACD** | Most blocks (6,340), lowest accuracy for high-block guard (63.6%), 2,305 missed opportunities | BATL 0127: 44.9% accuracy = near coin-flip |
| 2 | **position** | Hard-coded 25% gain threshold contradicts Ross's "add on strength" strategy | BCTX: 16.7% accuracy — blocks productive adds |
| 3 | **reentry_loss** | Already improved by graduated policy but still 56% accuracy with 3,311 blocks | BATL: 26% accuracy on Jan 27, 94% on Jan 26 — inconsistent |

---

## 3. Deep Dive: Top Problem Guards

### 3.1 MACD Guard (#1 Problem — 6,340 blocks)

**Current behavior** (`warrior_entry_guards.py:174-226`):
```python
if not snapshot.is_macd_bullish:
    return False, "MACD GATE - blocking entry (histogram=...)"
```
This is a **binary gate**: if MACD histogram is negative at all, block ALL entries.

**What Ross actually says** (warrior.md Section 8):
> "MACD: Confirmation only. 'MACD goes negative' = caution / potential exit."

And in Section 3.3, MACD negative is listed as a **full EXIT trigger**, not an entry blocker.

**The problem**: Ross uses MACD as *confirmation* and an *exit signal*, but the bot treats it as an **absolute entry blocker**. In fast-moving stocks like BATL, MACD histogram can go briefly negative during sharp pullbacks before resuming — exactly when Ross would re-enter.

**Per-case evidence:**

| Case | MACD Blocks | MACD Accuracy | A/B Delta |
|------|------------|---------------|-----------|
| BATL 0127 | 2,174 | **44.9%** | +$12,396 (HURT) |
| BATL 0126 | 2,174 | 87.2% | +$5,676 (HURT) |
| MLEC 0213 | 402 | 83.1% | +$4,899 (HURT) |
| TNMG 0116 | 198 | 66.7% | +$4,184 (HURT) |

BATL Jan 27 has **44.9% MACD accuracy** — the MACD gate is worse than random on this ticker. Yet the bot still captured $23K with guards on, meaning when it DID get in, the trade worked. Without MACD blocking, it would have captured $35K.

### 3.2 Position Guard Profit-Check (#2 Problem — 2,448 blocks)

**Current behavior** (`warrior_entry_guards.py:257-268`):
```python
unrealized_pnl_pct = ((entry_price - pos.entry_price) / pos.entry_price) * 100
pnl_above_threshold = unrealized_pnl_pct > 25  # 25% gain threshold
if price_past_target or pnl_above_threshold:
    return False, "BLOCKING - position already past target. Take profit first."
```

**What Ross actually says** (warrior.md Section 2.3):
> "Add Triggers: Every 50¢ higher ($6.00 → $6.50 → $7.00). Never adds on weakness / never averages down."

Ross **adds on strength aggressively** — his signature pattern is sell partial → add back → sell again. He adds at higher prices, not stops adding once he's profitable. The 25% threshold is **invented** — Ross has no documented percentage threshold for blocking adds.

**Evidence**: BCTX position guard accuracy is **16.7%** — it's blocking 5 out of 6 productive adds. TNMG has 504 position blocks at 77.3% accuracy, meaning even for a "better" case, it still blocks 114 profitable entries.

### 3.3 Reentry Loss Guard (Already Improved)

The graduated policy (`max_reentry_attempts=3`) implemented from the Feb 23 spec has dramatically improved this guard. The overall accuracy (56%) is still below ideal, but the change from binary-block to graduated-block already moved guards-ON P&L from $137K → $161K (+$24K).

**Remaining issue**: On BATL Jan 27, accuracy is only **26%** — meaning the guard blocks 3 consecutive re-entries, but 74% of the time those entries would have been profitable. On high-volatility runners, even 3 consecutive losses don't mean the stock is dead.

---

## 4. Proposed Fixes (Ranked by Expected P&L Impact)

### Fix #1: MACD Guard → Histogram Tolerance (Expected: +$5K–$15K)

**Problem**: Binary is_macd_bullish gate blocks entries on even tiny negative histogram values during pullbacks.

**Proposed change**: Add histogram tolerance threshold. Only block when MACD is meaningfully negative.

**Implementation approach** (for Backend Specialist):
```
# Current: Binary MACD block
if not snapshot.is_macd_bullish:
    return False, "MACD GATE - blocking entry"

# Proposed: Tolerance-based MACD check
histogram = snapshot.macd_histogram or 0
tolerance = engine.config.macd_histogram_tolerance  # NEW: default -0.02 or configurable
if histogram < tolerance:
    return False, f"MACD GATE - blocking entry (histogram={histogram:.4f} < tolerance={tolerance})"
# If histogram is between tolerance and 0, allow entry with warning
```

**Strategy justification** (warrior.md Section 8): Ross uses MACD as "confirmation only" — slightly negative MACD during a pullback doesn't disqualify an entry. He only exits when MACD goes clearly negative + other signals confirm reversal.

**A/B test plan**:
1. Run batch with `macd_histogram_tolerance = 0` (current behavior)
2. Run batch with `macd_histogram_tolerance = -0.02` (slight tolerance)
3. Run batch with `macd_histogram_tolerance = -0.05` (moderate tolerance)
4. Compare P&L, particularly BATL, TNMG, MLEC cases

**Change surface**:
| File | Change |
|------|--------|
| `warrior_types.py` | Add `macd_histogram_tolerance: float = -0.02` to `WarriorEngineConfig` |
| `warrior_entry_guards.py` | Replace binary `is_macd_bullish` check with histogram threshold comparison |

**Risk**: Cases where MACD guard currently helps (VERO saved $16K, ROLR saved $10K) could see regression. The tolerance approach preserves protection for strongly negative MACD while allowing entries during pullback transitions.

---

### Fix #2: Remove Position Profit-Check Guard (Expected: +$3K–$6K)

**Problem**: The 25% unrealized gain threshold is not grounded in Ross methodology and blocks productive adds.

**Proposed change**: Remove the `pnl_above_threshold > 25` check entirely. Keep `max_scale_count` as the position size limiter.

**Implementation approach**:
```
# REMOVE this block entirely:
pnl_above_threshold = unrealized_pnl_pct > 25  # 25% gain threshold
if price_past_target or pnl_above_threshold:
    return False, "BLOCKING - position already past target."

# KEEP max_scale_count check (line 253-255) — this is the legitimate position guard
```

**Strategy justification** (warrior.md Section 2.3):
> "Add Triggers: Every 50¢ higher. Each add raises cost basis — he is aware of this risk. Adds are progressively smaller if price is getting expensive."

Ross explicitly adds well past 25% gain. His signature pattern is entry at $6 → add at $6.50 → add at $7.00 → that's already +16% and he keeps going. No documented 25% cap.

**A/B test plan**:
1. Run batch with profit-check guard enabled (current)
2. Run batch with profit-check guard disabled
3. Monitor BCTX and TNMG cases specifically

**Change surface**:
| File | Change |
|------|--------|
| `warrior_entry_guards.py` | Remove lines 257-268 (profit-check block) |

**Risk**: Without the profit-check, the bot may add at very extended prices. Mitigated by `max_scale_count` which still limits total adds. Could also replace with a progressively-smaller add size instead of a hard block.

---

### Fix #3: Increase max_reentry_after_loss on High-Volatility Cases (Expected: +$2K–$4K)

**Problem**: On high-volatility runners (BATL-type stocks), even 3 consecutive losses don't mean the opportunity is over. BATL Jan 27 shows 26% accuracy for reentry_loss guard.

**Proposed change**: Make `max_reentry_after_loss` configurable per-case or dynamically adjustable based on stock volatility.

**Option A** (simple): Increase default from 3 → 5 to match Ross's documented "3-5 trades per session."

**Option B** (dynamic): Use rate-of-change or daily range to set a higher limit for volatile stocks.

**Strategy justification** (warrior.md Section 4.3):
> "Typically 3-5 trades on same stock per session. After 2+ failed re-entries: 'gave up on this one.'"

The current default of 3 is at the bottom of Ross's range. Moving to 5 better captures the full re-entry behavior.

**A/B test plan**:
1. Run batch with `max_reentry_after_loss = 3` (current)
2. Run batch with `max_reentry_after_loss = 5`
3. Compare P&L, focus on BATL cases

**Change surface**:
| File | Change |
|------|--------|
| `warrior_types.py` | Change default from 3 → 5 in `WarriorMonitorSettings` |

**Risk**: Low risk — `max_reentry_after_loss = 5` still provides a cap against infinite revenge trading. Ross himself trades up to 5 times on the same stock.

---

## 5. Fix Priority Ranking

| Rank | Fix | Expected Impact | Effort | Risk |
|------|-----|----------------|--------|------|
| 1 | MACD histogram tolerance | +$5K–$15K | Medium | Medium (could regress VERO/ROLR) |
| 2 | Remove profit-check guard | +$3K–$6K | Small | Low (max_scale still limits) |
| 3 | Raise max_reentry to 5 | +$2K–$4K | Trivial | Low (well within Ross methodology) |

**Combined expected improvement**: +$10K–$25K additional P&L, bringing total capture from 37.2% toward 40%+.

---

## 6. Comparison to Feb 23 Findings

| Metric | Feb 23 | Feb 24 | Change | Cause |
|--------|--------|--------|--------|-------|
| Guards-ON P&L | $136,993 | **$161,116** | **+$24,123** | Graduated reentry fix |
| Guards-OFF P&L | $151,170 | $151,170 | $0 | Expected (no guard code runs) |
| Net guard impact | **-$14,177** | **+$9,946** | **+$24,123** | Guards flipped from net-negative to net-positive |
| Guard accuracy | 62.2% | 60.2% | -2.0% | Slight decrease due to more blocks being attempted |
| Total blocks | ~9,400 | 12,171 | +2,771 | More attempts reaching guards now |

> [!TIP]
> The Feb 23 reentry fix was the single largest improvement in Warrior bot history (+$24K). The remaining fixes in this spec are incremental but meaningful — primarily targeting the MACD gate which is the last remaining guard with >50% missed opportunities on key cases.

---

## 7. A/B Test Execution Plan

For each fix, run independently against the current baseline ($161K):

```
Fix 1 (MACD tolerance):
  POST /warrior/sim/run_batch_concurrent {"include_trades": true, "macd_tolerance": -0.02}
  → Requires new config param to be implemented first
  
Fix 2 (Remove profit-check):
  → Code change, then standard batch run
  
Fix 3 (max_reentry = 5):
  → Config change to default, then standard batch run
```

**Execution order**: Fix 3 first (trivial, low risk) → Fix 2 next (small, low risk) → Fix 1 last (needs implementation, medium risk).

After all fixes, run combined A/B to measure total improvement.

---

## 8. Raw Data Files

| File | Contents |
|------|----------|
| `batch_guards_on.json` | Full batch results with guards enabled (35 cases) |
| `batch_guards_off.json` | Full batch results with guards disabled (35 cases) |
| `guard_ab_analysis.json` | Parsed analysis with per-case deltas and guard breakdown |
