# Audit Validator Handoff: BNRG Regression Claims Challenge

**Date:** 2026-03-04 14:49 ET  
**From:** Coordinator  
**To:** Audit Validator  
**Source:** `nexus2/reports/2026-03-04/research_bnrg_regression.md`  
**Strategy:** `.agent/strategies/warrior.md`  
**Output:** `nexus2/reports/2026-03-04/validation_bnrg_regression.md`

---

> [!CAUTION]
> **DO NOT run `python scripts/gc_quick_test.py`.** It requires Clay's uvicorn server.

## Claims to Verify

### Code Claims

1. **"relative_volume is never populated in sim — defaults to 0 via getattr(..., 0)"**
   - Verify how `relative_volume` is set on watched candidates in sim mode
   - Verify the `getattr` fallback in the RVOL check code

2. **"The code bypasses the MACD defensive gate when RVOL < 5x"**
   - Read lines 291-301 of `warrior_entry_guards.py`
   - Verify the exact logic: does RVOL < 5x skip the MACD gate?

3. **"Both BNRG and NPT regressions are from the RVOL bypass, not the falling knife extension"**
   - Is there evidence the falling knife guard did NOT trigger for these cases?

### Methodology Claim (CRITICAL — read warrior.md)

4. **"Ross's rule is that MACD is a hard gate regardless of volume. The 5x prerequisite is for MACD entry signals, not the defensive blocker."**
   - Read warrior.md §8.1 (lines 313-338)
   - The file says two things:
     - Line 320: "Red light, green light — MACD negative = DO NOT TRADE"
     - Line 322: "Requires 5x RVOL as a prerequisite for MACD signals to be meaningful"
   - Is the planner's interpretation correct that these are two separate rules?
   - Does "5x RVOL prerequisite" apply to MACD *entry signals* only, or to the defensive gate too?

### Fix Claim

5. **"Fix: Remove the RVOL bypass block (lines 291-301)"**
   - Is removal the correct fix, or should the RVOL check be preserved but applied differently (e.g., only for MACD crossover entry signals)?
