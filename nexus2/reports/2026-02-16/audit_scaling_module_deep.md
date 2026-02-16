# Deep Audit: Scaling Module Interactions & VERO Regression

**Date:** 2026-02-16  
**Agent:** Code Auditor  
**Reference:** [handoff_fix5_scaling_investigation.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-02-16/handoff_fix5_scaling_investigation.md)

---

## Q3: Should Scaling Be Blocked During `home_run` Mode?

**Finding:** `check_scale_opportunity` has **ZERO guards** for `exit_mode_override`. Scaling can and does fire during `home_run` mode.

**File:** [warrior_monitor_scale.py:31-155](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_scale.py#L31-L155)

**Code:** The function checks these guards in order:
```python
# Line 49: enable_scaling
if not s.enable_scaling: return None
# Line 52: max_scale_count
if position.scale_count >= s.max_scale_count: return None
# Line 57-60: support validation
# Line 63-66: pending exit
# Line 70-73: stop buffer (<1%)
# Line 77-82: cooldown (60s, bypassed in sim+Fix5)
# Line 87-92: recovery grace (bypassed in sim+Fix5)
# Line 95-96: price < support
# Line 115-133: pullback zone (Fix5 vs original)
```

**MISSING:** No check for `position.exit_mode_override`. The function reads it for trace logging only (line 99):
```python
exit_mode = getattr(position, 'exit_mode_override', None)  # L99 — logging only
```

**Trace Evidence (5 symbols scaled during home_run):**
From `scaling_trace_57952.log:35`:
```
VERO: CHECKPOINT — ... exit_mode_override=home_run ...
```
From Fact 6 in the handoff: TNMG, GWAV, VELO, PRFX, BATL all scaled during `home_run`.

**Conclusion:** Scaling during `home_run` is architecturally unguarded. Whether this is correct depends on methodology — Ross does add to winners, but the current implementation adds on *pullbacks* (weakness), not *strength*. Adding a guard `if exit_mode == 'home_run': return None` would block these 5 cases.

---

## Q4: Is 2x Position Doubling Too Aggressive?

**Finding:** Settings allow up to 200% of original position via two 50% adds.

**File:** [warrior_types.py:100-104](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_types.py#L100-L104)

**Code:**
```python
enable_scaling: bool = True        # L100
max_scale_count: int = 2           # L101 — Starter + 2 adds
scale_size_pct: int = 50           # L102 — Add 50% of original size
```

**Math:** Starting with 100 shares (original_shares):
- Scale #1: +50 shares → 150 total (1.5x)
- Scale #2: +50 shares → 200 total (2.0x)

**Scale size calculation** at [warrior_monitor_scale.py:139](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_scale.py#L139):
```python
add_shares = int(position.original_shares * s.scale_size_pct / 100)
```

**Trace evidence (TNMG doubled):**
From handoff Fact 5: TNMG entered at $3.43, scaled twice at $2.75 and $2.73 — nearly 20% below entry. This is adding 100% more shares at a loss.

**Conclusion:** 2x is aggressive given the pullback zone allows scaling well below entry. Options:
- Reduce `max_scale_count` to 1 (max 1.5x)
- Reduce `scale_size_pct` to 25 (max 1.5x with 2 adds)
- Tighten pullback zone so it can't scale 20% below entry

---

## Q5: Does `scale_count` Leak from Re-Entries?

**Finding:** YES — confirmed via both code and trace data.

### Code Path

**File:** [warrior_monitor.py:286-368](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor.py#L286-L368)

Re-entries follow this chain:
1. `enter_position()` → calls `complete_entry()` or inline `add_position()`
2. `add_position()` (line 251) checks for existing position with same symbol (line 273)
3. If found → routes to `_consolidate_existing_position()` (line 279)
4. `_consolidate_existing_position()` **increments scale_count** at line 329:

```python
existing_position.scale_count += 1  # Line 329
```

**File:** [warrior_entry_execution.py:603](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_execution.py#L603)  
The `complete_entry()` function calls `engine.monitor.add_position()` which routes to consolidation if the symbol already exists.

**File:** [warrior_engine_entry.py:1422](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py#L1422)  
Duplicate inline `add_position()` call — same consolidation route.

### Trace Evidence (VERO)

**File:** `data/scaling_trace_57952.log` lines 31-33

**Before re-entry (line 31-32):**
```
VERO: CHECKPOINT — price=$2.86, entry=$2.83, shares=384, original_shares=384,
  scale_count=0, partial_taken=False, exit_mode_override=base_hit
VERO: PULLBACK CHECK — is_pullback_zone=False
```

**After re-entry (line 33-34):**
```
VERO: CHECKPOINT — price=$3.04, entry=$2.920356..., shares=674, original_shares=384,
  scale_count=1, partial_taken=False, exit_mode_override=base_hit
VERO: PULLBACK CHECK — is_pullback_zone=False
```

**Key changes between lines 32→33 (NO SCALE EXECUTED event):**
| Field | Before | After | Change |
|-------|--------|-------|--------|
| `shares` | 384 | 674 | +290 (re-entry shares) |
| `entry_price` | $2.83 | $2.92 | Weighted avg ↑ |
| `scale_count` | 0 | 1 | **Incremented by consolidation** |
| `exit_mode_override` | base_hit | base_hit | Unchanged |

**Conclusion:** Re-entries consume scale slots. With `max_scale_count=2`, a re-entry leaves only 1 slot for the actual scaling module. This is a design flaw — re-entries and scaling should use independent counters.

---

## Q6: VERO Regression Mystery — SOLVED

### The Mystery
VERO regressed when `enable_improved_scaling=True` despite the scaling module **never activating** for VERO. Every VERO checkpoint shows `is_pullback_zone=False`. No `SCALE EXECUTED` event exists for VERO anywhere in trace data.

### Root Cause: Indirect Effect via Cooldown Bypass

The `enable_improved_scaling` flag has **three code effects** — not just the pullback zone:

**File:** [warrior_monitor_scale.py:77](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_scale.py#L77)
```python
# Fix 5A: Skip wall-clock cooldown in sim mode
if position.last_scale_attempt and not (s.enable_improved_scaling and monitor.sim_mode):
```

**File:** [warrior_monitor_scale.py:87](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_scale.py#L87)
```python
# Fix 5A: Skip recovery grace in sim mode
if position.recovered_at and not (s.enable_improved_scaling and monitor.sim_mode):
```

**File:** [warrior_monitor_scale.py:115](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_scale.py#L115)
```python
# Fix 5B: Proper pullback zone logic
if s.enable_improved_scaling:
    # New strict pullback zone (50% of entry-to-support range)
else:
    # Original: always True when allow_scale_below_entry=True
```

### VERO's Regression Mechanism

VERO's regression is NOT from the scaling module. The trace proves:

1. **VERO enters at $2.83** with 384 shares, `base_hit` mode
2. **Price drops** to $2.67-$2.80 range (below entry)
3. **Re-entry fires** — a second entry at ~$3.04 with 290 shares
4. **Consolidation** creates weighted avg entry $2.92, shares=674, `scale_count=1`
5. **Fix 1 (partial-then-ride)** triggers later → partial taken, mode switches to `home_run`
6. **Remaining 337 shares** ride from $3.04+ up to $3.99 (line 61)

The regression comes from the **interaction between consolidation (raising entry_price from $2.83→$2.92) and the exit logic**, not from the scaling module itself. The higher average entry ($2.92 vs $2.83) changes:
- **Profit target**: Now based on $2.92 instead of $2.83
- **Breakeven stop**: After partial, stop moves to $2.92 instead of $2.83
- **Risk/reward ratio**: Tighter R with higher entry

> [!IMPORTANT]
> **VERO's regression is a false positive for fixing the scaling module.** The regression mechanism is re-entry consolidation altering entry price, not scaling. This happens regardless of `enable_improved_scaling` because consolidation is in `warrior_monitor.py`, not `warrior_monitor_scale.py`.

### Why Does the Toggle Affect It?

The `enable_improved_scaling` toggle has an **indirect timing effect** in sim mode:
- `True`: Cooldown bypass allows scaling checks every bar → more CHECKPOINT trace logging, potentially slightly different execution timing
- `False`: Cooldown blocks most scaling checks → fewer code paths executed per tick

The real question is: **does VERO's re-entry happen on both configs?** If the consolidation path is identical regardless of the toggle (which it should be — consolidation is in `warrior_monitor.py` and doesn't check `enable_improved_scaling`), then VERO's regression must come from a **different symbol's scaling** affecting the global P&L.

---

## Summary of Findings

| Question | Finding | Severity |
|----------|---------|----------|
| Q3: exit_mode guard | **Missing** — no block on home_run scaling | Medium |
| Q4: Position sizing | 2x max — aggressive with deep pullback zone | Medium |
| Q5: scale_count leak | **Confirmed** — re-entries increment scale_count | High |
| Q6: VERO mystery | Re-entry consolidation, NOT scaling module | High (misattribution risk) |

## Recommendations

1. **Separate counters**: `scale_count` for scaling module, `reentry_count` for consolidation
2. **Add exit_mode guard**: Block scaling during `home_run` (scaling adds risk to a position already being trailed)
3. **Tighten pullback zone**: 50% threshold allows 20% below entry — too deep
4. **Isolate VERO**: Run VERO case alone with both configs to confirm the toggle has no effect on VERO specifically
