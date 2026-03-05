# Audit Validator Handoff: MLEC Regression Report Challenge

**Date:** 2026-03-04 12:52 ET  
**From:** Coordinator  
**To:** Audit Validator  
**Source:** `nexus2/reports/2026-03-04/research_mlec_regression.md`  
**Output:** `nexus2/reports/2026-03-04/validation_mlec_regression.md`

---

## Core Claim to Challenge

**Planner says:** The EMA fix cannot cause the MLEC regression because:
1. Sim bypasses the scanner entirely
2. Entry technicals use `sim_get_intraday_bars` (test case JSON), not Polygon daily bars
3. The EMA fix only changed `get_daily_bars()` which is a separate data path

**Your job:** Adversarially challenge this reasoning. Specifically verify:

### Check 1: Is `get_daily_bars()` truly never called during sim?
- Search for ALL callers of `get_daily_bars()` in the codebase
- Trace whether any of those callers are reachable during batch test execution
- Don't trust the planner's claim — verify the call graph yourself

### Check 2: Is `adjusted=true` isolated to the scanner path?
- The specialist added `adjusted=true` to `polygon_adapter.py:get_daily_bars()`
- This is a global change to the adapter, not scanner-specific
- Could any sim/entry path call `get_daily_bars()` indirectly?

### Check 3: Are there other changes in the 3 modified files?
- Check `git diff` for ALL changes in the 3 files (polygon_adapter.py, warrior_scanner_service.py, gc_quick_test.py)
- Could any change besides the EMA fix affect batch test results?

### Check 4: Run MLEC twice for concurrency noise
- Run `python scripts/gc_quick_test.py ross_mlec_20260213` twice
- Compare results — if they differ, it's concurrency noise
