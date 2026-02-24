# Backend Status: Guard Tuning Fixes

**Date:** 2026-02-24  
**Agent:** Backend Specialist  
**Spec:** `nexus2/reports/2026-02-24/spec_guard_tuning_investigation.md`  
**Status:** ✅ COMPLETE — all 3 fixes implemented, pytest 757 passed

---

## Changes Made

### Fix 1: max_reentry_count 3 → 5

**File:** [warrior_types.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_types.py)  
**Line:** 122  
**Change:** `max_reentry_count: int = 3` → `max_reentry_count: int = 5`  
**Justification:** Ross trades 3-5 times per stock per session (warrior.md §4.3). Default of 3 was bottom of range.  
**Risk:** Low — still capped, prevents infinite revenge trading.

---

### Fix 2: Remove 25% Profit-Check Guard

**File:** [warrior_entry_guards.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py)  
**Lines:** 257-268 (removed)  
**Change:** Removed `pnl_above_threshold > 25` and `price_past_target` checks entirely.  
**Kept:** `max_scale_count` guard (line 253-255) as legitimate position limiter.  
**Justification:** Ross adds on strength past 25% gain — threshold was invented, not from methodology (warrior.md §2.3).  
**Risk:** Low — `max_scale_count` still limits total adds.

---

### Fix 3: MACD Histogram Tolerance

**Files changed:**
| File | Change |
|------|--------|
| [warrior_engine_types.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_types.py) L117 | Added `macd_histogram_tolerance: float = -0.02` to `WarriorEngineConfig` |
| [warrior_entry_guards.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py) L209-237 | Replaced binary `is_macd_bullish` with `histogram < tolerance` comparison |

**Behavior change:**
- **Before:** Block ALL entries when `is_macd_bullish == False` (histogram < 0)
- **After:** Block only when `histogram < -0.02` (configurable). Values between -0.02 and 0 are allowed with info log.

**Justification:** Ross uses MACD as "confirmation only" (warrior.md §8). Slightly negative histogram during pullbacks doesn't disqualify entry. 44.9% accuracy on BATL Jan 27 showed binary gate was worse than random.  
**Risk:** Medium — could regress VERO (-$16K saved) and ROLR (-$10K saved) if tolerance too loose. Default -0.02 is conservative.

---

## Verification

```
pytest nexus2/tests/ -x -q
757 passed, 4 skipped, 3 deselected in 106.45s
```

## Testable Claims

| # | Claim | Verify With |
|---|-------|-------------|
| 1 | `max_reentry_count` default is now 5 | `Select-String -Path "nexus2\domain\automation\warrior_types.py" -Pattern "max_reentry_count"` |
| 2 | No `pnl_above_threshold` or `price_past_target` in guard code | `Select-String -Path "nexus2\domain\automation\warrior_entry_guards.py" -Pattern "pnl_above_threshold"` → 0 results |
| 3 | `macd_histogram_tolerance` exists in engine config | `Select-String -Path "nexus2\domain\automation\warrior_engine_types.py" -Pattern "macd_histogram_tolerance"` |
| 4 | MACD gate uses `histogram < tolerance` not `is_macd_bullish` | `Select-String -Path "nexus2\domain\automation\warrior_entry_guards.py" -Pattern "is_macd_bullish"` → 0 results in `_check_macd_gate` |
| 5 | All tests pass | `pytest nexus2/tests/ -x -q` → 757 passed |

## Next Steps

Run A/B batch tests to measure P&L impact:
1. Baseline (before these changes)
2. Current (all 3 fixes applied)
3. Individual fix isolation if needed
