# Handoff: Investigate 10s Price Stepping Impact on P&L

**Agent:** Backend Planner
**Priority:** P2 — simulation fidelity
**Date:** 2026-02-25
**Reference:** `sweep_entry_bar_timeframe.json`

---

## Context

After backfilling 10s bar data for all 35 test cases, the **1min baseline P&L dropped ~$9K** (from ~$164K to ~$155K), even though `entry_bar_timeframe` stayed at `"1min"`. This happened because the `historical_bar_loader` auto-discovers `*_10s.json` sidecar files and enables:

1. **6x clock stepping** (10s steps instead of 1min)
2. **More precise quote resolution** (10s price interpolation for stops/entries)

Meanwhile, switching `entry_bar_timeframe` to `"10s"` (so patterns also use 10s candles) made things much WORSE: P&L dropped to $91K.

## Open Questions (Investigate)

1. **How does live WB get price data?**
   - Does it use Polygon WebSocket for continuous real-time quotes?
   - Or does it poll at 10s intervals?
   - What's the actual price resolution WB uses in production?

2. **Is 10s stepping making simulation MORE realistic?**
   - If live WB gets sub-second price updates, 10s stepping is closer to reality than 1min
   - The $155K number might be more accurate than $164K
   - OR: 10s stepping might expose phantom triggers (stop hits that wouldn't happen with real spread data)

3. **Why did 3 specific cases lose big with 10s stepping?**
   - NPT: $26.7K → -$65 (total loss)
   - ROLR: $31.4K → $6.6K  
   - EVMN: $20.7K → $5.2K
   - Are these getting stopped out earlier due to more granular price movement?
   - Or getting worse entries due to 10s candle analysis?

4. **What's the interaction between 10s stepping and entry timing?**
   - 10s stepping means the engine checks for entries 6x more often
   - Does this cause earlier entries at worse prices?
   - Or does it cause better entries by catching breakouts faster?

5. **Should we treat the $155K number as the new baseline?**
   - If 10s stepping is closer to live behavior, yes
   - If 10s stepping introduces unrealistic artifacts, no

## Suggested Investigation Approach

- Read `sim_context.py` for how 10s stepping affects entry/exit timing
- Read the quote resolution logic to understand how 10s prices are interpolated
- Check live WB's data feed configuration (Polygon adapter)  
- Compare the 3 big losers case-by-case: where exactly does the entry/exit price differ?

## Output

Write findings to: `nexus2/reports/2026-02-25/spec_10s_stepping_impact.md`
