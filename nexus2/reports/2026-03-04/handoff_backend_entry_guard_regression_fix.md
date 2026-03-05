# Backend Specialist Handoff: Fix Entry Guard Regressions

**Date:** 2026-03-04 15:38 ET  
**From:** Coordinator  
**To:** Backend Specialist  
**Tiebreaker:** `nexus2/reports/2026-03-04/validation_bnrg_tiebreaker.md`  
**Output:** `nexus2/reports/2026-03-04/backend_status_entry_guard_regression_fix.md`

---

> [!CAUTION]
> **DO NOT run `python scripts/gc_quick_test.py`.** It requires Clay's uvicorn server. Tell Clay to run it.

## Context

The entry guard improvements caused 4 regressions (BNRG -$10K, NPT -$5.6K, MLEC -$3K, BCTX -$500). Root cause identified by tiebreaker validator:

- The **falling knife guard** checks `is_macd_bullish` (histogram > 0)
- The **MACD gate** allows histogram down to -0.02
- Entries with histogram between -0.02 and 0, below 20 EMA, pass the MACD gate but get blocked by the falling knife
- Additionally, the **RVOL bypass** was added in error (strategy misinterpretation) and should be removed

## Fix 1: Remove RVOL Bypass (Revert)

**File:** `warrior_entry_guards.py`

Remove the RVOL prerequisite block added earlier (~lines 291-301). The MACD defensive gate ("red light = don't trade") is **unconditional** per warrior.md §8.1. The 5x RVOL prerequisite only applies to MACD *entry signals* (crossovers), not the defensive gate.

## Fix 2: Align Falling Knife MACD Threshold

**File:** `warrior_entry_guards.py` → `_check_falling_knife_guard()`

The falling knife guard uses `is_macd_bullish` (histogram > 0) to detect falling knives. But the MACD gate already approved entries with histogram between -0.02 and 0. The falling knife should NOT re-block entries the MACD gate approved.

**Fix:** Change the falling knife's MACD check to use the same -0.02 tolerance:
```python
# Instead of: is_macd_bullish (histogram > 0)
# Use: histogram >= tolerance (same as MACD gate)
is_macd_acceptable = snapshot.macd_histogram >= -0.02
```

## Do NOT Touch

- The falling knife extension to all patterns (Fix #1 from earlier) — keep this, it's correct
- The high-volume red candle guard — keep this

## Verification

Tell Clay to run:
```powershell
python scripts/gc_quick_test.py --all --diff
```

Expected: BNRG/NPT/MLEC/BCTX regressions should recover. UOKA +$22K improvement should be preserved.
