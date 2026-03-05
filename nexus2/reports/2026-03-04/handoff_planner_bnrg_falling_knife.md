# Backend Planner Handoff: BNRG Falling Knife Trace

**Date:** 2026-03-04 16:05 ET  
**From:** Coordinator  
**To:** Backend Planner  
**Output:** `nexus2/reports/2026-03-04/research_bnrg_falling_knife_trace.md`

---

> [!CAUTION]
> **DO NOT run `python scripts/gc_quick_test.py`.** It requires Clay's uvicorn server.

## Problem

After extending the falling knife guard to all entry patterns, BNRG (2026-02-11) regressed from +$361 to -$9,705. A previous fix attempt (aligning the MACD threshold) did not resolve it, suggesting the root cause is different from what was theorized.

## Questions

1. **What exactly blocks BNRG's winning entry?**
   - Read `_check_falling_knife_guard()` in `warrior_entry_guards.py`
   - Trace the exact conditions: what are the candle values, EMA 20 position, MACD histogram at BNRG's entry time?
   - Which specific check blocks: "falling knife" (below 20 EMA + MACD neg) or "high-vol red candle" (≥1.5x avg)?

2. **Is the high-vol red candle threshold too aggressive?**
   - The BCTX solo run showed: `[Warrior Guards] BCTX: HIGH-VOL RED CANDLE guard — red bar vol 331,438 >= 1.5x avg 2,147`
   - That's vol 154x the avg, not 1.5x. The 1.5x threshold might be catching normal pullback volume.
   - What does the avg volume baseline look like for BNRG?

3. **Would the old behavior (falling knife only on VWAP_BREAK) have allowed BNRG's profitable entry?**
   - What pattern was BNRG entering on? PMH_BREAK? HOD_BREAK?
   - If it was any pattern other than VWAP_BREAK, the old code would have allowed it through.

4. **Same analysis for NPT, MLEC, BCTX** — what specific guard blocks each?

## Deliverable

Per-case trace showing: which guard fired, the exact values that triggered it, and whether the guard criteria are too broad.
