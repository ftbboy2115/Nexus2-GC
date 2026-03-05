# Backend Planner Handoff: BNRG Regression Investigation

**Date:** 2026-03-04 14:23 ET  
**From:** Coordinator  
**To:** Backend Planner  
**Output:** `nexus2/reports/2026-03-04/research_bnrg_regression.md`

---

> [!CAUTION]
> **DO NOT run `python scripts/gc_quick_test.py` yourself.** It requires Clay's uvicorn server. Ask Clay to run it for you.

## Problem

After implementing two entry guard changes, BNRG (2026-02-11) regressed from +$361 to -$9,705 (delta -$10,065).

**The two changes:**
1. Falling knife guard extended to all patterns (previously only VWAP_BREAK)
2. RVOL ≥ 5x prerequisite added for MACD gate (MACD gate bypassed when RVOL < 5x)

## Questions

1. **Which fix caused the regression?** Check BNRG's RVOL value. If RVOL < 5x, the MACD gate was bypassed — meaning a MACD-negative entry that was previously blocked is now allowed through.

2. **What was BNRG's entry behavior before vs after?**
   - How many trades did the bot take before the change?
   - How many trades does it take now?
   - Did the RVOL bypass allow a new (bad) entry?

3. **Is the RVOL prerequisite logic correct?**
   - The strategy says "5x RVOL prerequisite for MACD signals to be meaningful" (warrior.md §8.1 L322)
   - Does this mean: below 5x, MACD should be IGNORED entirely (including as a block)?
   - Or does it mean: MACD signals are only ENTRY signals when RVOL ≥ 5x, but the defensive gate should always apply?
   - This is an important interpretation question.

4. **Also check NPT** — it dropped from +$10,591 to +$4,977. Same question: which fix, and why?

## How to Investigate

- Read the new guard code in `warrior_entry_guards.py`
- Check the BNRG test case for RVOL value and MACD values
- Trace the entry decision logic

## Deliverable

Short report with: which fix caused each regression, the RVOL/MACD values involved, and whether the RVOL prerequisite interpretation is correct per Ross's methodology.
