# 10s vs 1min Forensic Analysis — Root Cause & Findings

**Date:** 2026-02-26  
**Context:** With optimized parameters (max_stop=0.10, partial_exit=0.25, max_scale=4), the gap between 1min ($359K) and 10s ($149K) P&L is **$210K**.

---

## Key Finding: The Hybrid is Already Implemented ✅

After reading the stepping code in `sim_context.py` (L112-122), I discovered that **the hybrid approach is already working**:

```python
# step_clock_ctx (sim_context.py:112-122)
use_10s_stepping = any(
    ctx.loader.has_10s_bars(sym) for sym in ctx.loader.get_loaded_symbols()
)
if use_10s_stepping:
    total_steps = minutes * 6     # 10s steps
    step_seconds = 10
else:
    total_steps = minutes         # 1min steps
    step_seconds = 0
```

The stepping interval is determined by **whether 10s sidecar files exist** — completely independent of `entry_bar_timeframe`. Since all 35 test cases have 10s sidecar files (backfilled on Feb 25), the "1min" batch run already uses:
- **1min candles** for pattern detection (via `entry_bar_timeframe: "1min"`)
- **10s stepping** for stop checking (via auto-detected sidecar files)

The **$359K is already the hybrid result**. No code changes needed.

---

## What the $149K "10s" Test Actually Measures

The forensic script's "10s" run sets `config_overrides: {"entry_bar_timeframe": "10s"}` — this switches **pattern detection** to use 10s candles. The stepping was already 10s in both runs.

The $210K gap is entirely caused by entry patterns (micro-pullback, VWAP break, etc.) producing bad entries when applied to noisy 10s candle structure instead of smooth 1min candles. This is expected — the patterns were designed for 1min.

---

## Root Cause: Entry Price Inflation with 10s Patterns

### The Top 4 Cases Account for $210K (100% of the gap)

| Case | Symbol | 1min Entry | 10s Entry | Entry Δ | 1min P&L | 10s P&L | Case Δ |
|------|--------|-----------|----------|---------|----------|---------|--------|
| NPT | NPT | $6.96 | $7.92 | +$0.96 | +$68,021 | -$926 | -$68,947 |
| BATL | BATL | $2.78 | $3.69 | +$0.91 | +$61,366 | -$3,513 | -$64,879 |
| ROLR | ROLR | $4.38 | $15.82 | +$11.44 | +$45,724 | -$1,458 | -$47,181 |
| EVMN | EVMN | $17.20 | $20.97 | +$3.77 | +$42,355 | +$13,554 | -$28,801 |

In every case, 10s pattern detection enters **higher on the move**, leaving less profit room and triggering mental stops.

---

## Conclusions

1. **$359K is already the hybrid result** — 1min patterns + 10s stop checking
2. **No code changes needed** — the architecture already separates the two concerns
3. **`entry_bar_timeframe` should stay at `"1min"`** — 10s candles are too noisy for pattern detection
4. **The $9K drop** (from pre-backfill $368K → post-backfill $359K) represents the realistic cost of 10s stop checking — confirmed by the prior `spec_10s_stepping_impact.md`

---

## Summary Statistics

| Metric | Value |
|--------|-------|
| Total delta (10s patterns - 1min patterns) | -$209,744 |
| Cases worsened by 10s patterns | 9 |
| Cases improved by 10s patterns | 5 |
| Cases unchanged | 21 |
| P&L lost from worsened | -$217,847 |
| P&L gained from improved | +$8,103 |
| Top 4 cases account for | 96% of total gap |
