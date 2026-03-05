# Backend Status: Entry Guard Regression Fix

**Date:** 2026-03-04 15:45 ET
**Agent:** Backend Specialist
**Reference:** `handoff_backend_entry_guard_regression_fix.md`

---

## Changes Made

### Fix 1: Remove RVOL Bypass (Revert)

**File:** `warrior_entry_guards.py:291-301` → removed

The RVOL prerequisite block was added based on a misinterpretation of warrior.md §8.1. The 5x RVOL prerequisite applies to MACD *entry signals* (crossovers), not the defensive MACD gate ("red light = don't trade"). The gate is now unconditional again.

**Before:**
```python
rvol = float(getattr(watched.candidate, 'relative_volume', 0) or 0)
if rvol < 5.0:
    logger.info(f"MACD gate BYPASSED — RVOL {rvol:.1f}x < 5x prerequisite")
    # Still store snapshot/candles for falling knife guard downstream
elif histogram < tolerance and snapshot.macd_crossover != "bullish":
    return False, reason
```

**After:**
```python
# MACD GATE is UNCONDITIONAL (warrior.md §8.1 — "red light = don't trade")
if histogram < tolerance and snapshot.macd_crossover != "bullish":
    return False, reason
```

### Fix 2: Align Falling Knife MACD Threshold

**File:** `warrior_entry_guards.py`, `_check_falling_knife_guard()` (lines 357-372)

The falling knife guard used `check_falling_knife()` → `is_macd_bullish` (histogram > 0). This re-blocked entries with histogram between -0.02 and 0 that the MACD gate had already approved. Now uses the same `-0.02` tolerance from `engine.config.macd_histogram_tolerance`.

**Before:**
```python
is_falling, fk_reason = check_falling_knife(current_price, snapshot)
# check_falling_knife uses snapshot.is_macd_bullish → histogram > 0
```

**After:**
```python
tolerance = engine.config.macd_histogram_tolerance  # default -0.02
histogram = snapshot.macd_histogram or 0
is_macd_acceptable = histogram >= tolerance
```

### Cleanup: Removed Unused Import

Removed `check_falling_knife` from the import block since the falling knife logic is now inlined with the aligned tolerance.

## What Was NOT Changed

- ✅ Falling knife extension to all patterns — **kept** (correct behavior)
- ✅ High-volume red candle guard — **kept**
- ✅ `check_falling_knife` helper function in `warrior_entry_helpers.py` — **untouched** (may be used elsewhere)

## Testable Claims

| # | Claim | File:Line | Pattern |
|---|-------|-----------|---------|
| 1 | RVOL bypass removed | `warrior_entry_guards.py:291` | No `rvol < 5.0` anywhere in file |
| 2 | MACD gate unconditional | `warrior_entry_guards.py:291-301` | `if histogram < tolerance` without RVOL condition |
| 3 | Falling knife uses -0.02 tolerance | `warrior_entry_guards.py:360` | `is_macd_acceptable = histogram >= tolerance` |
| 4 | Falling knife still applies to all patterns | `warrior_entry_guards.py:163` | `_check_falling_knife_guard` called unconditionally |
| 5 | Unused import cleaned up | `warrior_entry_guards.py:21-23` | `check_falling_knife` no longer imported |

## Verification

> [!IMPORTANT]
> **Clay must run batch tests:**
> ```powershell
> python scripts/gc_quick_test.py --all --diff
> ```
> Expected: BNRG/NPT/MLEC/BCTX regressions recover. UOKA +$22K improvement preserved.
