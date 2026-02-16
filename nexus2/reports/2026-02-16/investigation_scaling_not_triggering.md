# Investigation: Scaling Logic Not Triggering in Batch Simulation

**Date:** 2026-02-16  
**Author:** Backend Planner  
**From:** Coordinator handoff (handoff_planner_scaling_investigation.md)

---

## Executive Summary

Scaling logic exists in `warrior_monitor_scale.py` and IS wired into the simulation path. However, **multiple compounding issues** prevent it from ever successfully firing. The primary blocker is the 60-second cooldown timer using wall-clock time (`now_et()`), which makes scaling mechanically impossible after the first attempt in simulation. Additionally, the pullback zone check is logically broken, RVOL confirmation is completely bypassed, and the PSM transition in `execute_scale_in` may silently fail.

---

## A. Full Scale Opportunity Logic Map

### File: `warrior_monitor_scale.py`

#### `check_scale_opportunity()` (lines 31–120) — 8 Guard Conditions

| # | Guard | Line | Condition | Default | Sim Impact |
|---|-------|------|-----------|---------|------------|
| 1 | Enable scaling | 49 | `s.enable_scaling` | `True` | ✅ PASS |
| 2 | Max scale count | 52 | `scale_count >= max_scale_count` | `0 < 2` | ✅ PASS |
| 3 | Support exists | 57–60 | `technical_stop or mental_stop > 0` | Set at entry | ✅ PASS |
| 4 | Pending exit | 64 | `_is_pending_exit(symbol)` | DB query | ⚠️ DEPENDS |
| 5 | Stop buffer | 70–73 | `(price - support) / price * 100 < 1.0` | 3%+ typically | ✅ PASS |
| 6 | Cooldown | 76–81 | `elapsed < 60 seconds` (wall clock) | None initially | 🔴 **BLOCKS AFTER 1ST** |
| 7 | Recovery grace | 85–90 | `recovered_at` within 10s | `None` | ✅ PASS |
| 8 | Price vs support | 93 | `current_price < support` | Above support | ✅ PASS |
| 9 | Pullback zone | 98–101 | `current_price <= entry OR allow_below` | `allow=True` | ⚠️ **DEAD GUARD** |

**Evidence for each guard:**

**Guard 1 — enable_scaling:**
```
File: warrior_types.py:100
Code: enable_scaling: bool = True  # Ross adds on strength - enabled by default
Verified: load_monitor_settings() returns None → dataclass defaults used
```

**Guard 5 — Stop buffer example (ROLR, entry ~$4.50):**
```
support = $4.35 (15¢ mental stop)
stop_buffer_pct = (4.50 - 4.35) / 4.50 * 100 = 3.33%
Result: PASS (3.33% > 1.0%)
```

**Guard 6 — Cooldown (CRITICAL):**
```
File: warrior_monitor_scale.py:76-81
Code:
    if position.last_scale_attempt:
        cooldown_seconds = 60
        elapsed = (now_et() - position.last_scale_attempt).total_seconds()
        if elapsed < cooldown_seconds:
            return None

Problem: now_et() returns WALL CLOCK time, not sim clock time.
In sim, ALL 960 minutes of bars process in ~1-2 seconds of real time.
After the first scale attempt sets last_scale_attempt = now_et(),
ALL subsequent bars see elapsed ≈ 0 seconds < 60 → BLOCKED.
```

**Guard 9 — Pullback zone (BROKEN LOGIC):**
```
File: warrior_monitor_scale.py:98
Code: is_pullback_zone = current_price <= position.entry_price or s.allow_scale_below_entry

Problem: allow_scale_below_entry defaults to True (warrior_types.py:104).
This makes is_pullback_zone ALWAYS True regardless of price.
The guard is logically dead — scaling triggers on every bar, not just pullbacks.
```

### Missing Check: `min_rvol_for_scale` (NEVER REFERENCED)

```
File: warrior_types.py:103
Code: min_rvol_for_scale: float = 2.0  # Volume confirmation (2x relative volume)

Finding: This config field exists but is NEVER checked in check_scale_opportunity().
The function has no volume confirmation at all.
Verified via: grep_search for "min_rvol_for_scale" in warrior_monitor_scale.py → 0 results
Also confirmed by previous trade_management_audit.md (line 161, 186, 266)
```

---

## B. Where `check_scale_opportunity` Is Called

### Call Chain (VERIFIED)

```
step_clock_ctx() [sim_context.py:157]
  └→ monitor._check_all_positions() [warrior_monitor.py:526]
       └→ For each position with no exit signal:
            └→ should_check_scale = current_price and self.settings.enable_scaling [line 575]
            └→ if should_check_scale and not self.sim_mode:  [line 576]
            │     └→ Market calendar filter (NON-SIM ONLY)
            └→ if should_check_scale:  [line 583]
                  └→ scale_signal = await self._check_scale_opportunity(...) [line 584]
                  └→ if scale_signal:
                        └→ await self._execute_scale_in(...) [line 589]
```

**Key Evidence:**

```
File: warrior_monitor.py:576
Code: if should_check_scale and not self.sim_mode:

Finding: The `not self.sim_mode` guard ONLY applies to the market calendar filter.
In sim_mode, the calendar check is SKIPPED (correctly), and should_check_scale
remains True. The actual scaling check at line 583 runs unconditionally.
```

```
File: sim_context.py:462  
Code: ctx.engine.monitor._submit_scale_order = sim_submit_order_historical

Finding: The _submit_scale_order callback IS wired to the sim order function.
Line 401 initially sets it to None, then line 462 overwires it.
```

### Conclusion: Scaling IS wired in simulation. The issue is NOT missing wiring.

---

## C. Root Cause Analysis

### Root Cause 1 (PRIMARY): Cooldown Timer Uses Wall-Clock Time

The 60-second cooldown at `warrior_monitor_scale.py:76-81` uses `now_et()` which returns **real wall-clock time**, not simulation time. In batch simulation:

- All 960 minutes of bars process in ~1-2 seconds of real time
- After the first `check_scale_opportunity` call sets `position.last_scale_attempt = now_et()` (via `execute_scale_in` line 219), every subsequent bar sees `elapsed ≈ 0 seconds`
- Since `0 < 60`, the cooldown blocks ALL subsequent scaling attempts

**Impact:** Maximum 1 scale per sim run (if the first attempt succeeds).

### Root Cause 2: First Attempt May Fail at PSM Transition

Even if the first attempt passes all guards, `execute_scale_in` at line 166 calls:
```python
if not set_scaling_status(position.position_id):
    logger.warning(f"[Warrior Scale] {symbol}: Cannot scale - PSM transition blocked")
    return False
```

This performs a DB lookup by `position_id` and checks `OPEN → SCALING` transition. In the per-process in-memory DB (created at `_run_case_sync` lines 487-494), the trade record was created by `log_warrior_entry` in `complete_entry` (line 462 of `warrior_entry_execution.py`). The PSM transition should work... **BUT** this is a silent failure point. If the trade status is anything other than "open" (e.g., "partial" after a partial exit), the transition is blocked and scaling fails silently (only a `logger.warning`).

### Root Cause 3: Pullback Zone Logic Is Inverted

```python
is_pullback_zone = current_price <= position.entry_price or s.allow_scale_below_entry
```

Since `allow_scale_below_entry=True`, this evaluates to `True` on EVERY bar, making the gate logically dead. The intent was to only scale on pullbacks (when price pulls back near support), but the boolean logic makes it a no-op. This means if scaling DID work, it would fire on every single bar — including at new highs — which contradicts Ross Cameron's "add on pullbacks to support" methodology.

### Root Cause 4: No Volume Confirmation

The `min_rvol_for_scale` config field (default 2.0x) is defined but never checked. This means scaling has no volume gate, allowing it to fire even during low-volume drift.

---

## D. Proposed Fix

### Fix 1: Use Sim Clock for Cooldown (CRITICAL)

```
File: warrior_monitor_scale.py, lines 76-81
Current: elapsed = (now_et() - position.last_scale_attempt).total_seconds()
Fix: Use monitor._sim_clock.current_time if monitor.sim_mode and hasattr(monitor, '_sim_clock'),
     falling back to now_et() for live trading.
```

### Fix 2: Fix Pullback Zone Logic

```
File: warrior_monitor_scale.py, line 98
Current: is_pullback_zone = current_price <= position.entry_price or s.allow_scale_below_entry
Fix: The logic should be:
  - If allow_scale_below_entry=True: scale when price is NEAR support (pullback zone)
  - If allow_scale_below_entry=False: scale only when price > entry (adding on strength)
  
Corrected logic:
  if s.allow_scale_below_entry:
      # Pullback zone: price between support and entry (within 2% of support)
      pullback_range = (current_price - support) / support * 100
      is_pullback_zone = pullback_range <= 3.0  # Within 3% of support
  else:
      # Strength zone: only add above entry
      is_pullback_zone = current_price > position.entry_price
```

> [!IMPORTANT]
> The pullback zone fix depends on which scaling methodology the Warrior bot should follow.
> Ross Cameron adds on **pullbacks to support** AND on **new highs breaking out**.
> The current config `allow_scale_below_entry` conflates these two modes.
> Recommend consulting the Strategy Expert before implementing.

### Fix 3: Wire RVOL Check

```
File: warrior_monitor_scale.py (insert after line 90, before price check)
Add: Get current RVOL from market data and compare against s.min_rvol_for_scale.
     Skip scaling if RVOL < threshold.
Note: In sim, RVOL data may not be available from historical bars.
      May need to skip this check in sim_mode or compute from bar volumes.
```

### Fix 4: Improve PSM Transition Logging

```
File: warrior_monitor_scale.py, line 167
Add: Include current trade status in the warning message for easier debugging.
```

---

## E. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Fixing cooldown enables too-frequent scaling | Medium | Combine with pullback zone fix; A/B toggle |
| Pullback zone fix changes scaling behavior | Medium | A/B test with `enable_improved_scaling` toggle |
| RVOL check blocks all scaling in sim (no RVOL data) | Low | Skip RVOL check in sim_mode |
| Scale order creates duplicate broker position | Low | MockBroker already handles this (lines 363-370) |
| PSM transition fails silently | Medium | Improve logging, consider bypassing PSM in sim |

---

## F. Verification Commands

```powershell
# Verify cooldown uses now_et() (wall clock)
Select-String -Path "nexus2\domain\automation\warrior_monitor_scale.py" -Pattern "now_et"

# Verify min_rvol_for_scale is never checked
Select-String -Path "nexus2\domain\automation\warrior_monitor_scale.py" -Pattern "rvol"

# Verify pullback zone logic
Select-String -Path "nexus2\domain\automation\warrior_monitor_scale.py" -Pattern "pullback_zone"

# Verify _submit_scale_order is wired in sim
Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "submit_scale_order"

# Verify enable_scaling default
Select-String -Path "nexus2\domain\automation\warrior_types.py" -Pattern "enable_scaling"
```
