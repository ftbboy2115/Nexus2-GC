# Backend Planner Handoff: MLEC Regression Investigation

**Date:** 2026-03-04 12:41 ET  
**From:** Coordinator  
**To:** Backend Planner  
**Output:** `nexus2/reports/2026-03-04/research_mlec_regression.md`

---

## Problem

After the EMA bar reversal fix, MLEC (2026-02-13) regressed from ~+$844 to -$578 (delta -$1,422). MNTS also regressed by -$618. We need to understand if the EMA fix caused this.

## Questions

1. **What was MLEC's EMA 200 before the fix (reversed bars) vs after (correct order)?**
   - Run MLEC case with `--trades` to see entry/exit details
   - Check if the EMA value changed significantly

2. **Did the EMA change cause MLEC to enter differently?**
   - Different entry timing, different stop, different exit?
   - Or did the scanner reject/accept differently?

3. **Is the new result more correct?**
   - If the old EMA was garbage data and happened to produce a better trade, the regression is acceptable
   - If the new EMA is correct and the trade is worse, that's a real problem

4. **Same question for MNTS** — is the -$618 delta from the EMA fix or from something else (entry guards, PMH changes)?

## How to Investigate

```powershell
# Run with trade details
python scripts/gc_quick_test.py ross_mlec_20260213 --trades

# Check what EMA value the scanner computes for MLEC
# Add temporary logging or check the scan history
```

## Deliverable

Short report: did the EMA fix cause the regression, and is the new behavior more correct?
