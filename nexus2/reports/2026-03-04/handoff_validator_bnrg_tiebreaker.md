# Tiebreaker Validator Handoff: BNRG Regression Root Cause

**Date:** 2026-03-04 14:55 ET  
**From:** Coordinator  
**To:** Audit Validator (Tiebreaker)  
**Planner report:** `nexus2/reports/2026-03-04/research_bnrg_regression.md`  
**Validator report:** `nexus2/reports/2026-03-04/validation_bnrg_regression.md`  
**Output:** `nexus2/reports/2026-03-04/validation_bnrg_tiebreaker.md`

---

> [!CAUTION]
> **DO NOT run `python scripts/gc_quick_test.py`.** It requires Clay's uvicorn server.

## Disagreement

**Planner says:** `relative_volume` defaults to 0 in sim via `getattr(..., 0)`, disabling the MACD gate for all test cases. Both regressions are from the RVOL bypass.

**Validator says:** `sim_context.py:283` hardcodes `relative_volume=Decimal("10.0")`. Since 10.0 ≥ 5.0, the RVOL bypass never executes. The MACD gate runs normally. The planner's root cause is wrong.

## Your Job

### Settle the Disagreement
1. Read `sim_context.py` around line 283 — what is `relative_volume` actually set to?
2. Read the RVOL check in `warrior_entry_guards.py` (lines ~291-301) — what `getattr` path does it use? Does it read from `watched.candidate.relative_volume` or somewhere else?
3. Trace the full data flow: where does the entry guard get RVOL from, and what value does it see during batch sim?

### Find the Actual Root Cause
If the RVOL bypass isn't the cause, then what IS causing the BNRG and NPT regressions?
- The falling knife extension is the other change — check if it fires for BNRG/NPT
- Read the `_check_falling_knife_guard()` function
- Check what BNRG's candle data looks like — would it trigger falling knife detection?

### Deliverable
- Which agent is correct about the RVOL/sim question
- The actual root cause of the BNRG/NPT regressions (with evidence)
