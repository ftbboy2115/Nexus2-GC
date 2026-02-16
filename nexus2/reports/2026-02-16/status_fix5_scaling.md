# Status: Fix 5 — Scaling (Cooldown + Pullback Zone)

**Date:** 2026-02-16  
**Agent:** Backend Specialist  
**Result:** ⚠️ REGRESSION — needs investigation before accepting

---

## Changes Implemented

### Fix A: Sim-Aware Cooldown
**File:** `nexus2/domain/automation/warrior_monitor_scale.py`  
- Line 76: `if position.last_scale_attempt and not (s.enable_improved_scaling and monitor.sim_mode):`
- Line 85: `if position.recovered_at and not (s.enable_improved_scaling and monitor.sim_mode):`
- Both cooldown and recovery grace period are skipped in sim mode when toggle is on.

### Fix B: Pullback Zone Guard
**File:** `nexus2/domain/automation/warrior_monitor_scale.py`  
- Lines 96-111: Replaced broken `is_pullback_zone = current_price <= entry or allow_scale_below_entry` (always True) with proper pullback zone logic.
- New logic: `pullback_threshold = entry - (support_distance * 0.5)`, zone is `price <= threshold AND price > support`.
- Example: entry=$3.22, support=$2.72 → scale zone = ≤$2.97 and >$2.72.

### Fix C: A/B Toggle
**File:** `nexus2/domain/automation/warrior_types.py`  
- Added `enable_improved_scaling: bool = True` to `WarriorMonitorSettings` (line 159).

### Fix D: Persistence
**File:** `nexus2/db/warrior_monitor_settings.py`  
- Added `enable_improved_scaling` to both `apply_monitor_settings()` and `get_monitor_settings_dict()`.

---

## Verification: Unit Tests

```
✅ enable_improved_scaling defaults to True
✅ Persists in settings dict
✅ Restored via apply_monitor_settings
✅ check_scale_opportunity imports OK
```

---

## Verification: Batch Sim Results

| Case | Fix 1 Baseline | Fix 5 | Delta | Assessment |
|------|---------------|-------|-------|------------|
| VERO | $1,907 | $240 | -$1,667 | 🔴 Major regression |
| NPT | $1,733 | $1,157 | -$576 | 🔴 Regression |
| UOKA | $824 | $898 | +$74 | ✅ Slight improvement |
| BATL 1/27 | $2,485 | $1,997 | -$488 | 🔴 Regression |
| ROLR | $6,140 | $5,114 | -$1,026 | 🔴 Regression |
| BATL 1/26 | $771 | $922 | +$151 | ✅ Improvement |
| **Total (all 29)** | **$13,298** | **$9,796** | **-$3,502** | ⚠️ **-26% regression** |

### Analysis

The regression is unexpected. With the old code, wall-clock cooldown **blocked ALL scaling in sim** (all 960 bars process in <1s, so the 60s cooldown was never satisfied). So the baseline had **zero scaling**. The new code now allows scaling to fire, but the pullback zone guard should prevent indiscriminate scaling.

**Possible causes of regression:**

1. **Pullback zone IS triggering** — scaling fires on pullbacks but the adds raise cost basis, then price continues down, increasing loss. This would explain why VERO and ROLR lost money — the pullback was real but the stock then kept falling.

2. **Interaction with partial-then-ride (Fix 1)** — Fix 1 sells 50% and switches to home_run mode. If scaling adds shares back during the home_run trail phase, it could re-expand position size at the wrong time.

3. **Support calculation mismatch** — The scaling code uses `position.technical_stop` as "support", but this is the stop price (support - 5¢ buffer), not the true support. This shifts the pullback zone lower than intended.

### Recommendation

**REJECT Fix 5** (set `enable_improved_scaling = False`) until further investigation. The pullback zone logic may be correct in concept but the thresholds need tuning, or there's an interaction with Fix 1 partial-then-ride that causes position re-expansion at bad times.

**Quick fix to test:** Set `enable_improved_scaling: bool = False` to revert to baseline behavior.
