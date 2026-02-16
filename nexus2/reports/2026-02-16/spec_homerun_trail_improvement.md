# Spec: Home Run Trail Improvement (Fix 4)

**Date:** 2026-02-16  
**Author:** Backend Planner  
**Input:** `handoff_planner_homerun_trail.md`, code audit of `warrior_monitor_exit.py`

---

## A. Current `_check_home_run_exit` Logic — Mapped

**File:** `nexus2/domain/automation/warrior_monitor_exit.py`  
**Function:** `_check_home_run_exit` — Lines 973–1063

### Parameters (from `warrior_types.py` lines 139–143)

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `home_run_trail_after_r` | 1.5 | Start trailing stop after this R-multiple |
| `home_run_trail_percent` | 0.20 | Trail = `high_since_entry × (1 - 0.20)` |
| `home_run_partial_at_r` | 2.0 | Take 50% partial at this R-multiple |
| `home_run_move_to_be` | True | Move stop to breakeven after partial |

### Decision Flow

```
_check_home_run_exit(position, current_price, r_multiple)
│
├── STEP 1: Trailing Stop Check (if r ≥ 1.5R)
│   ├── trail_stop = high_since_entry × 0.80
│   ├── Only update stop if trail_stop > current_stop AND > entry_price
│   └── If current_price ≤ current_stop → FULL EXIT (all shares)
│
├── STEP 2: Partial at R Target (if partial not taken AND r ≥ 2.0R)
│   ├── Sell 50% of shares
│   ├── If home_run_move_to_be: stop → breakeven (entry_price)
│   └── Return PARTIAL_EXIT signal
│
└── Return None (hold)
```

### Critical Observations

**Finding #1: The trailing stop is a fixed 20%-below-high — no tiered widening.**

```python
# Line 993
trail_stop = position.high_since_entry * (1 - Decimal(str(s.home_run_trail_percent)))
```

For a $5 stock that rallies to $6 (high_since_entry = $6.00):
- Trail = $6.00 × 0.80 = **$4.80** → 20% below high = **$1.20 trail width**
- But if stock dips to $5.50 (only -50¢ from high), the trail is at $4.80 — still far away
- **Problem**: The trail is too wide initially (20% = $1.20) but too tight for big moves. On a stock going from $5 to $12 (like GRI), 20% of $12 = $2.40 trail — but Ross held through much larger pullbacks.

Actually wait — let me reconsider. 20% below $12 high = $9.60 trail stop. That's a $2.40 buffer. For a stock that went $5→$12 (entry $5), this means locking in $4.60 profit. That's **not bad** — but the problem is that the trail activates too early:

**Finding #2: Trail activates at 1.5R — which could be as little as +15¢ profit on a tight-stop trade.**

```python
# Line 992
if r_multiple >= s.home_run_trail_after_r:
```

For a trade with risk_per_share = $0.10 (tight 10¢ stop):
- 1.5R = +$0.15 profit → high_since_entry ≈ $5.15
- Trail = $5.15 × 0.80 = **$4.12** → This is below entry ($5.00), so the `trail_stop > position.entry_price` guard prevents update
- **BUT**: The trail_stop calculation is relative to high_since_entry, not entry_price. Once the stock runs higher, the trail tightens relative to price, not relative to profit.

**Finding #3: When Fix 1 sends a position to home_run, `partial_taken = True` — the 2R partial NEVER fires.**

```python
# Line 815 (base_hit_target, candle trail path)
position.partial_taken = True
position.exit_mode_override = "home_run"

# Line 1023 (home_run_exit)
if not position.partial_taken and r_multiple >= s.home_run_partial_at_r:
    # ^^^ This is ALWAYS False for Fix 1 positions
```

This means Fix 1 positions enter home_run mode and the ONLY exit mechanism is:
1. The 20%-below-high trailing stop, OR
2. The breakeven stop set by Fix 1 (see Finding #4), OR
3. Pre-home_run checks: stop_hit, candle_under_candle, topping_tail, or time_stop

**Finding #4: Fix 1 sets `current_stop = entry_price` (breakeven) when entering home_run mode.**

```python
# Line 819 (base_hit_target)
position.current_stop = position.entry_price
```

Then in `evaluate_position`, CHECK 1 runs BEFORE the mode-specific check:

```python
# Lines 1144-1147
signal = _check_stop_hit(position, current_price, r_multiple)
if signal:
    return signal
```

And `_check_stop_hit` (line 381):
```python
if current_price > position.current_stop:
    return None
```

**Problem**: If the stock dips even 1¢ below entry after Fix 1 sends it to home_run mode, `_check_stop_hit` fires a FULL EXIT at breakeven. The home_run trailing logic never gets a chance to run.

**Finding #5: Candle-under-candle and topping tail checks are EXIT-MODE AGNOSTIC.**

```python
# Lines 1149-1157 (evaluate_position)
signal = await _check_candle_under_candle(...)
if signal: return signal

signal = await _check_topping_tail(...)
if signal: return signal
```

These fire BEFORE the mode-specific check (line 1168). CUC has a guard for green positions (`candle_exit_only_when_red=True`, line 447), but topping tail has NO such guard — it checks if price is near high_since_entry (line 604) and if wick ratio is high.

**For home_run positions**: A topping tail at the highs of a multi-dollar move would cause a FULL EXIT of the riding shares — exactly the kind of momentary signal Ross ignores when in home_run mode.

---

## B. Analysis: Why the Trail Exits Too Early

### Root Cause #1: Breakeven Stop Kills Most Home Run Positions (CRITICAL)

When Fix 1 sends a position to home_run mode:
1. `current_stop = entry_price` (breakeven)
2. Stock makes a small pullback to entry → `_check_stop_hit` fires → FULL EXIT

This is the **primary cause** of early exit. The home_run trailing logic at 20%-below-high never engages because the breakeven stop triggers first.

**Evidence**: In the check order (evaluate_position lines 1144-1177):
```
CHECK 1: _check_stop_hit        ← breakeven stop fires here
CHECK 2: _check_candle_under_candle
CHECK 3: _check_topping_tail
CHECK 4: _check_home_run_exit   ← never reached if stop already hit
```

### Root Cause #2: Topping Tail Exits Home Run Positions

Topping tail (line 560) fires when:
- Wick > 60% of candle range
- Candle high ≥ 99.5% of high_since_entry

This is a reversal pattern that makes sense for base_hit trades but is **too aggressive** for home_run positions. Ross explicitly tolerates "topping tail candles" during big moves and only uses them as a final exit signal when combined with other weakness.

### Root Cause #3: No Trail Tiering (Minor)

The 20%-below-high trail is actually quite wide and unlikely to be the primary problem. However, it has no adaptation:
- At 2R: Trail is 20% below high (reasonable)
- At 5R: Trail is still 20% below high (could be wider for bigger moves)
- At 10R: Trail is still 20% below high (Ross gives more room on parabolic moves)

### Root Cause #4: No Candle-Based Trail for Home Run Mode

Ross does NOT use percentage-based trailing stops at all (per research doc §4). He uses:
1. **Structural level-based profit-taking** (take profit at $7, $7.50, $8, etc.)
2. **Visual exit triggers** (tape reading, big sellers, widening spreads)
3. **Give-back tolerance** (~20-25% of peak P&L)

The bot's current approach (fixed 20% from high) is a **synthetic approximation** that doesn't match Ross's actual method. A candle-low trail (like base_hit mode uses) would better approximate Ross's behavior, but with wider lookback.

---

## C. Proposed Fix 4: Improved Home Run Trail

### Design: Three Sub-Fixes (All Behind A/B Toggle)

#### Fix 4a: Remove Breakeven Stop for Home Run Positions
**Impact: HIGH** — The breakeven stop is the #1 position killer.

When entering home_run mode from Fix 1, do NOT set `current_stop = entry_price`. Instead, use the existing trailing logic to manage the stop.

**Approach**: After the partial exit, set `current_stop` to the candle trail stop value that was just hit (the level that triggered the partial), rather than moving to breakeven. This preserves a reasonable stop level without being as tight as breakeven.

This is configurable: `home_run_stop_after_partial: str = "trail_level"` with options:
- `"breakeven"` — current behavior (entry_price)
- `"trail_level"` — use the candle trail stop that triggered the partial
- `"none"` — keep the original entry stop (most permissive)

#### Fix 4b: Skip Topping Tail for Home Run Positions
**Impact: MEDIUM** — Prevents premature reversal exits during big moves.

Add an exit-mode check to `_check_topping_tail`: if position is in home_run mode, skip the topping tail check entirely.

#### Fix 4c: Use Candle-Low Trail Instead of Percentage Trail
**Impact: HIGH** — Replaces synthetic 20%-from-high with Ross-aligned candle trailing.

Replace the percentage-based trail in `_check_home_run_exit` with a candle-low trailing stop, similar to base_hit mode but with a wider lookback (e.g., 5-bar low instead of 2-bar). This better approximates Ross's behavior of trailing at intraday lows.

New parameters:
- `home_run_candle_trail_enabled: bool = True` — use candle trail instead of % trail
- `home_run_candle_trail_lookback: int = 5` — looback bars for home run (wider than base_hit's 2)
- `home_run_trail_activation_r: float = 0.5` — start trailing after 0.5R from the partial exit point (i.e., after re-establishing profit beyond the partial level)

---

## D. Change Surface Enumeration

| # | File | Change | Location | Template |
|---|------|--------|----------|----------|
| 1 | `warrior_types.py` | Add Fix 4 config fields + A/B toggle | After line 148 (enable_partial_then_ride) | Follows existing toggle pattern |
| 2 | `warrior_monitor_exit.py` | Fix 4a: Change breakeven logic in Fix 1 partial-then-ride | Lines 815-827 (candle trail path) and 928-940 (fallback path) | Existing breakeven pattern |
| 3 | `warrior_monitor_exit.py` | Fix 4b: Add home_run guard to `_check_topping_tail` | Line 569 (after enable_topping_tail check) | CUC's green position guard (line 447) |
| 4 | `warrior_monitor_exit.py` | Fix 4c: Rewrite `_check_home_run_exit` trailing logic | Lines 991-1020 | `_check_base_hit_target` candle trail (lines 745-865) |
| 5 | `warrior_monitor_settings.py` | Persist new Fix 4 settings | Lines 94-106 (apply) and 131-137 (get) | Existing Fix 1/3 persistence pattern |

---

## E. Detailed Change Specifications

### Change #1: Add Config Fields to `warrior_types.py`

**File:** `nexus2/domain/automation/warrior_types.py`  
**Location:** After line 148 (`enable_partial_then_ride: bool = True`)

**Add:**
```python
    # Home Run Trail Improvement (Fix 4: A/B testable)
    enable_improved_home_run_trail: bool = False  # Master toggle for Fix 4
    home_run_stop_after_partial: str = "trail_level"  # "breakeven" | "trail_level" | "none"
    home_run_skip_topping_tail: bool = True  # Skip topping tail check for home_run positions
    home_run_candle_trail_enabled: bool = True  # Use candle-low trail instead of % trail
    home_run_candle_trail_lookback: int = 5  # N-bar low (wider than base_hit's 2)
```

### Change #2: Fix 4a — Change Breakeven Logic in Partial-Then-Ride

**File:** `nexus2/domain/automation/warrior_monitor_exit.py`

There are TWO identical blocks that set breakeven when entering home_run mode. Both need changing.

**Path A — Candle trail hit (lines 815-827):**

**Current code:**
```python
                    # Switch to home_run mode for remainder
                    position.exit_mode_override = "home_run"
                    position.candle_trail_stop = None  # Clear stale trail
                    
                    # Move stop to breakeven
                    position.current_stop = position.entry_price
                    if monitor._update_stop:
                        await monitor._update_stop(position.position_id, position.entry_price)
                    trade_event_service.log_warrior_breakeven(
                        position_id=position.position_id,
                        symbol=position.symbol,
                        entry_price=position.entry_price,
                    )
                    logger.info(f"[Warrior] {position.symbol}: Stop moved to breakeven, mode → home_run")
```

**Approach:** Wrap the breakeven logic in an `if` that checks `enable_improved_home_run_trail` and `home_run_stop_after_partial`:

- If Fix 4 disabled → existing behavior (breakeven)
- If `home_run_stop_after_partial == "trail_level"` → keep `current_stop` at the candle_trail_stop that just triggered (save it before clearing it)
- If `home_run_stop_after_partial == "none"` → don't change `current_stop` at all

**Path B — Flat fallback target hit (lines 928-940):** Same change pattern.

### Change #3: Fix 4b — Add Home Run Guard to Topping Tail

**File:** `nexus2/domain/automation/warrior_monitor_exit.py`  
**Location:** Inside `_check_topping_tail`, after line 569

**Current code (line 569):**
```python
    if not s.enable_topping_tail or not monitor._get_intraday_candles:
        return None
```

**Add after this check:**
```python
    # Fix 4b: Skip topping tail for home_run positions — Ross tolerates reversal patterns during big moves
    if getattr(s, 'enable_improved_home_run_trail', False) and getattr(s, 'home_run_skip_topping_tail', True):
        exit_mode = get_effective_exit_mode(monitor, position)
        if exit_mode == "home_run":
            logger.debug(
                f"[Warrior] {position.symbol}: Topping tail skipped (home_run mode, Fix 4b)"
            )
            return None
```

**Template:** This follows the exact pattern of the green-position guard in `_check_candle_under_candle` (lines 446-452).

### Change #4: Fix 4c — Candle-Low Trail for Home Run Mode

**File:** `nexus2/domain/automation/warrior_monitor_exit.py`  
**Function:** `_check_home_run_exit` (lines 973-1063)

**Current trailing logic (lines 991-1020):**
```python
    # 1. Check trailing stop (if above threshold)
    if r_multiple >= s.home_run_trail_after_r:
        trail_stop = position.high_since_entry * (1 - Decimal(str(s.home_run_trail_percent)))
        
        # Only trail UP, never down
        if trail_stop > position.current_stop and trail_stop > position.entry_price:
            old_stop = position.current_stop
            position.current_stop = trail_stop
            # ... logging ...
        
        # Check if price hit trailing stop
        if current_price <= position.current_stop:
            # ... FULL EXIT ...
```

**Approach:** When `enable_improved_home_run_trail` and `home_run_candle_trail_enabled`:
1. Replace the percentage trail with candle-low trail using `monitor._get_intraday_candles`
2. Use `home_run_candle_trail_lookback` (default 5) instead of base_hit's 2
3. Only activate after R ≥ `home_run_trail_after_r` (1.5R) — keeps existing gate
4. Trail = min(low of last N completed 1min candles)
5. Trail only moves UP, never down (same as base_hit)
6. When trail hit → FULL EXIT (remainder)

**If `home_run_candle_trail_enabled = False`:** fall back to existing 20% percentage trail.

**Template:** The candle trail logic in `_check_base_hit_target` (lines 756-790) is the direct template. Adapt lookback count and activation threshold.

### Change #5: Persist New Settings

**File:** `nexus2/db/warrior_monitor_settings.py`

**In `apply_monitor_settings` (after line 106):**
```python
    # Fix 4: Improved home run trail
    if "enable_improved_home_run_trail" in settings:
        monitor_settings_obj.enable_improved_home_run_trail = settings["enable_improved_home_run_trail"]
    if "home_run_stop_after_partial" in settings:
        monitor_settings_obj.home_run_stop_after_partial = settings["home_run_stop_after_partial"]
    if "home_run_skip_topping_tail" in settings:
        monitor_settings_obj.home_run_skip_topping_tail = settings["home_run_skip_topping_tail"]
    if "home_run_candle_trail_enabled" in settings:
        monitor_settings_obj.home_run_candle_trail_enabled = settings["home_run_candle_trail_enabled"]
    if "home_run_candle_trail_lookback" in settings:
        monitor_settings_obj.home_run_candle_trail_lookback = settings["home_run_candle_trail_lookback"]
```

**In `get_monitor_settings_dict` (after line 137):**
```python
        # Fix 4: Improved home run trail
        "enable_improved_home_run_trail": monitor_settings_obj.enable_improved_home_run_trail,
        "home_run_stop_after_partial": monitor_settings_obj.home_run_stop_after_partial,
        "home_run_skip_topping_tail": monitor_settings_obj.home_run_skip_topping_tail,
        "home_run_candle_trail_enabled": monitor_settings_obj.home_run_candle_trail_enabled,
        "home_run_candle_trail_lookback": monitor_settings_obj.home_run_candle_trail_lookback,
```

---

## F. Wiring Checklist

- [ ] Config fields added to `WarriorMonitorSettings` in `warrior_types.py`
- [ ] Fix 4a: Breakeven logic conditioned on `enable_improved_home_run_trail` and `home_run_stop_after_partial` (BOTH paths: candle trail and flat fallback)
- [ ] Fix 4b: Topping tail guard for home_run positions added
- [ ] Fix 4c: Candle-low trail logic added to `_check_home_run_exit`
- [ ] Fix 4c: Fallback to percentage trail when `home_run_candle_trail_enabled = False`
- [ ] Settings persistence added to `apply_monitor_settings`
- [ ] Settings persistence added to `get_monitor_settings_dict`
- [ ] Master toggle `enable_improved_home_run_trail = False` ensures no regression when disabled
- [ ] Run batch test with Fix 4 disabled → P&L matches current baseline
- [ ] Run batch test with Fix 4 enabled → compare P&L

---

## G. Risk Assessment

### What Could Go Wrong

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Stop too loose** — removing breakeven stop lets losers run | Positions that re-enter loss territory won't stop out quickly | `home_run_stop_after_partial = "trail_level"` keeps stop at the candle trail level (~breakeven but slightly more permissive). NOT "none" by default. |
| **Candle trail lookback too wide** — 5 bars may be too slow to react to sharp reversals | Late exit on reversal could give back significant profit | Start with 5 bars (default), A/B test against 3 and 7. Monitor max drawdown from peak. |
| **Topping tail skip too aggressive** — some topping tails DO signal the end of a move | Missing genuine reversal signals on home_run positions | This is Ross-aligned: he tolerates topping tails during big moves. Can be independently disabled via `home_run_skip_topping_tail = False`. |
| **Duplicate candle fetch** — `_check_home_run_exit` now fetches candles (didn't before) | Extra API calls per evaluation cycle | Single fetch per eval, cached by Polygon adapter. Minimal impact. |

### What Existing Behavior Might Break

1. **With Fix 4 OFF**: Zero risk. All changes gated behind `enable_improved_home_run_trail = False`.
2. **With Fix 4 ON**: Positions that enter home_run mode will be held longer. If the stock reverses hard, the wider stop means more give-back. This is the explicit tradeoff.

### What to Test After Implementation

1. **Batch test (Fix 4 OFF)**: Must exactly match current baseline P&L
2. **Batch test (Fix 4 ON, Fix 1 ON)**: Primary test — expect significant P&L improvement on big winners (NPT, GRI, ROLR)
3. **Batch test (Fix 4 ON, Fix 1 OFF)**: Verify Fix 4 works for native home_run mode (not just Fix 1 flow)
4. **Individual case validation**: NPT, GRI — trace exit reason and confirm it's the candle trail, not breakeven stop
5. **Regression check**: Verify no winners turned to losers by wider stop
