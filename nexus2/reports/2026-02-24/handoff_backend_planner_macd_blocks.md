# Handoff: MACD Block Bucket Analysis

**Agent:** Backend Planner  
**Priority:** P2 — Investigation  
**Date:** 2026-02-24  

---

## Context

The Warrior bot's MACD gate blocked 8,884 entry attempts across 35 batch test cases. We now have verified ground truth on Ross's MACD usage:

- **MACD negative = DO NOT TRADE** (binary gate — confirmed via training video)
- **MACD crossover neg→pos = valid entry signal** (confirmed via training video + Jan 15 transcript)
- **MACD is checked on 1-min chart only** — 10s chart is for micro pullback timing
- Ross treats the MACD "green light" as an **environment check**, not a per-candle gate

## The Question

**Of the 8,884 MACD blocks, how many were legitimate vs potentially over-blocking?**

Categorize each block into one of three buckets:

### Bucket A: Deeply Negative (Legitimate Blocks)
- MACD histogram significantly below zero (e.g., < -0.10)
- Stock in clear downtrend on 1-min chart
- Ross would NOT trade here — these blocks are correct

### Bucket B: Near-Zero Oscillation (Tolerance Issue)
- Histogram between -0.05 and 0.00
- Stock consolidating, MACD chopping around zero line
- Ross might consider this "neutral" rather than "red"
- The `-0.02` tolerance partially addresses this but may not be enough

### Bucket C: Recently-Crossed-Then-Dipped (Timing Issue)  
- Histogram was positive within the last 3-5 bars but dipped slightly negative on a pullback candle
- Ross would still consider the "green light" valid — he'd be using 10s chart to time the pullback
- This is where the bot's per-bar checking clashes with Ross's broader assessment style

---

## Investigation Steps

### Step 1: Instrument the MACD Gate
In `warrior_entry_guards.py::_check_macd_gate()`, when a block occurs, log:
- `histogram` value
- `macd_line` value  
- `macd_crossover` state
- Whether histogram was positive in the previous 3 bars (need to track recent history)

### Step 2: Run Batch Test
Run full batch test with instrumented logging. Collect all MACD block events.

### Step 3: Classify Blocks
For each block, classify into Bucket A/B/C based on:

| Metric | Bucket A | Bucket B | Bucket C |
|--------|----------|----------|----------|
| Histogram | < -0.10 | -0.05 to 0.00 | -0.05 to 0.00 |
| Recent positive? | No | No | Yes (within 3-5 bars) |
| MACD trend | Declining | Flat/choppy | Was rising, slight dip |

### Step 4: Counterfactual P&L Analysis (CRITICAL)

For **every** MACD block, perform a counterfactual check:

1. **Record block time and price** — the entry price that would have been used
2. **Look forward 1, 3, and 5 minutes** after the block — what did the price do?
3. **Calculate theoretical P&L** — if the bot had entered at block_price with the standard stop (low of entry candle), would the trade have been:
   - **Winner:** Price moved up to the profit target (HOD retest, +15-20¢ base hit)
   - **Loser:** Price hit the stop (candle low)
   - **Scratch:** Price stayed flat within the stop-to-target range

4. **Classify each block as:**
   - ✅ **SAVED** — Block prevented a losing trade (price went down → gate was correct)
   - ❌ **COST** — Block prevented a winning trade (price went up → gate over-blocked)
   - ➖ **NEUTRAL** — Price didn't move enough either way

5. **Aggregate by bucket:**

| Bucket | Count | SAVED | COST | NEUTRAL | Net P&L Impact |
|--------|-------|-------|------|---------|----------------|
| A (deeply negative) | ? | ? | ? | ? | ? |
| B (near-zero) | ? | ? | ? | ? | ? |
| C (recently-crossed) | ? | ? | ? | ? | ? |

**The key output:** If Bucket C shows more COST than SAVED, we have methodology-grounded evidence to add a "recently-crossed" buffer. If Bucket A shows mostly SAVED, the hard gate is working correctly.

**Data source:** Test case price data is already in the MockMarket snapshots. Use the 1-min bar data at the block timestamp to look forward.

---

## Verified Facts

| Fact | Source | Verification |
|------|--------|-------------|
| MACD gate exists at `_check_macd_gate()` | `warrior_entry_guards.py:174-240` | `view_code_item` |
| Tolerance = `-0.02` | `warrior_entry_guards.py:213` via `engine.config.macd_histogram_tolerance` | `view_code_item` |
| Crossover detection exists | `technical_service.py:192-197` | `view_file` |
| Crossover = prev_hist < 0 and curr_hist > 0 | `technical_service.py:194` | `view_file` |
| 8,884 total MACD blocks | `gc_batch_diagnose.py` output | Previous batch run |

## Open Questions
1. Does the batch test currently log individual MACD block histogram values, or just the count?
2. Can we access the historical MACD trajectory (last 5 bars) at time of block without significant code changes?
3. Is the guard block logging (with `blocked_time` and `blocked_price`) from the recent guard analysis work sufficient, or do we need MACD-specific fields?

---

## Output

Write findings to: `nexus2/reports/2026-02-24/spec_macd_block_analysis.md`

Include:
- Block count per bucket (A/B/C)
- Histogram distribution chart (text-based)
- Estimated P&L impact of allowing Bucket C entries
- Recommendation: Should the tolerance be widened? Should we add a "recently-crossed" buffer?
