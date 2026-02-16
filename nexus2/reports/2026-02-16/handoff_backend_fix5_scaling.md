# Handoff: Backend Specialist — Scaling Fix (Cooldown + Pullback Zone)

**Date:** 2026-02-16  
**From:** Coordinator  
**To:** Backend Specialist (`@agent-backend-specialist.md`)

---

## Context

Scaling logic exists in `warrior_monitor_scale.py` but never fires in simulation due to a wall-clock cooldown bug. When we fixed only the cooldown (skipping it in sim), scaling fired but **indiscriminately on every bar**, causing a -12% P&L regression. We need BOTH fixes applied together.

### Evidence: Cooldown-Only Fix Results

| Case | Fix 1 (baseline) | +Cooldown Only | Delta | Why |
|------|-------------------|----------------|-------|-----|
| VERO | $1,907 | $2,497 | +$590 | ✅ Right scaling |
| NPT | $1,733 | $2,328 | +$595 | ✅ Right scaling |
| UOKA | $824 | $1,130 | +$306 | ✅ Right scaling |
| BATL 1/27 | $2,485 | $1,152 | -$1,333 | 🔴 Over-scaled |
| ROLR | $6,140 | $5,077 | -$1,063 | 🔴 Over-scaled |
| BATL 1/26 | $771 | $150 | -$621 | 🔴 Over-scaled |
| **Total** | **$13,298** | **$11,649** | **-$1,649** | — |

---

## Your Task: Implement Both Fixes

### Fix A: Sim-Aware Cooldown (CRITICAL)

**File:** `nexus2/domain/automation/warrior_monitor_scale.py`

**Problem:** Lines 76-81 use `now_et()` (wall clock) for cooldown. In sim, all 960 bars process in ~1 second, so the 60s cooldown blocks ALL scaling after the first attempt.

**Fix:** Skip wall-clock cooldown in sim mode. The monitor object passed to `check_scale_opportunity` has a `sim_mode` attribute.

```python
# Line 76: Change from:
if position.last_scale_attempt:
# To: 
if position.last_scale_attempt and not monitor.sim_mode:
```

Also fix lines 85-90 (recovery grace) the same way:
```python
# Line 85: Change from:
if position.recovered_at:
# To:
if position.recovered_at and not monitor.sim_mode:
```

### Fix B: Fix Pullback Zone Guard (CRITICAL)

**File:** `nexus2/domain/automation/warrior_monitor_scale.py`

**Problem:** Line 98 has broken logic:
```python
is_pullback_zone = current_price <= position.entry_price or s.allow_scale_below_entry
```
Since `allow_scale_below_entry=True` by default, this evaluates to `True` on EVERY bar, so scaling fires at new highs, at entry, everywhere — not just pullbacks.

**Fix:** Ross Cameron scales on **pullbacks to support**, not at any price. Replace with:

```python
# Replace line 98 with proper pullback zone logic:
# Ross scales on pullbacks — price should be pulling back toward support,
# not running away at highs. Define pullback zone as within 50% of the
# entry-to-support range, measured from entry downward.
support_distance = position.entry_price - support
if support_distance > 0:
    pullback_threshold = position.entry_price - (support_distance * Decimal("0.5"))
    is_pullback_zone = current_price <= pullback_threshold and current_price > support
else:
    is_pullback_zone = False
```

This means if entry=$3.22 and support=$2.72 (50¢ range), the scale zone is $2.97 and below (pulled back at least 25¢ from entry, but still above support).

### Fix C: Add A/B Toggle

**File:** `nexus2/domain/automation/warrior_types.py`

Add a toggle field to `WarriorMonitorSettings` so we can A/B test:

```python
# After the existing Fix 4 section (~line 156):
# Scaling Fix (sim cooldown + pullback zone)
enable_improved_scaling: bool = True  # Fix 5: sim-aware cooldown + pullback zone
```

Wrap both Fix A and Fix B changes behind this toggle:
- If `enable_improved_scaling` is True: use sim-aware cooldown + pullback zone logic
- If False: original behavior (wall-clock cooldown, dead pullback zone)

### Fix D: Persistence

**File:** `nexus2/db/warrior_monitor_settings.py`

Add `enable_improved_scaling` to `get_monitor_settings_dict()` and `apply_monitor_settings()`.

---

## Reference Files

- Investigation: `nexus2/reports/2026-02-16/investigation_scaling_not_triggering.md`
- Scaling module: `nexus2/domain/automation/warrior_monitor_scale.py`
- Types: `nexus2/domain/automation/warrior_types.py`
- Settings persistence: `nexus2/db/warrior_monitor_settings.py`
- Monitor wiring: `nexus2/domain/automation/warrior_monitor.py` (lines 575-589)
- Strategy: `.agent/strategies/warrior.md`

---

## Verification

After implementing, run:
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/warrior/sim/run_batch_concurrent" -Method POST -ContentType "application/json" -Body "{}" -TimeoutSec 600 | ConvertTo-Json -Depth 10
```

**Expected:** Total P&L should be > $13,298 (Fix 1 baseline). The scaling should help cases like VERO, NPT, UOKA while the pullback zone prevents over-scaling on BATL, ROLR.

---

## Write Status To

`nexus2/reports/2026-02-16/status_fix5_scaling.md`
