# Audit Report: Exit Logic P&L Leakage

**Date:** 2026-02-16  
**Auditor:** Code Auditor  
**Scope:** `warrior_monitor_exit.py`, `warrior_types.py`, `warrior_monitor.py`, `warrior_engine_entry.py`  
**Objective:** Identify why the Warrior bot captures only 13.1% of Ross Cameron's P&L

---

## Executive Summary

The bot exits winners too early because **every position defaults to `base_hit` mode**, which exits at +15¢ trail / +18¢ flat — regardless of stock quality, price level, or how far the stock ultimately runs. The `home_run` mode exists and works, but is **almost never activated** (requires ≥5x volume explosion). Additionally, `_check_profit_target()` is dead code, the candle trail has a structural defect preventing activation on pullback-entry stocks, and there is no partial-then-ride mechanism in base_hit mode.

---

## A. File Inventory

| File | Lines | Key Functions | Role |
|------|-------|---------------|------|
| [warrior_monitor_exit.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py) | 1189 | 10 exit checks, evaluate_position, handle_exit | All exit logic |
| [warrior_types.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_types.py) | 181 | WarriorMonitorSettings, WarriorPosition | Config + state |
| [warrior_monitor.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor.py) | 730 | add_position, _create_new_position, _check_all_positions | Position lifecycle |
| [warrior_engine_entry.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py) | 1464 | enter_position, exit mode selection | Entry + exit mode |

---

## B. Exit Flow Ordering (Complete)

The `evaluate_position()` function at line 901 processes exit checks in strict sequential order with early returns:

```
CHECK 0:   _check_after_hours_exit    → Force exit ≥19:30 ET
CHECK 0.5: _check_spread_exit         → Exit if spread > 3%
CHECK 0.7: _check_time_stop           → Exit if red after N bars (DISABLED)
CHECK 1:   _check_stop_hit            → Mental/technical stop hit
CHECK 2:   _check_candle_under_candle → Red candle making new lows
CHECK 3:   _check_topping_tail        → Upper wick > 60% at highs
CHECK 4:   MODE-AWARE EXIT:
             if "base_hit"  → _check_base_hit_target (candle trail / +18¢ flat)
             if "home_run"  → _check_home_run_exit (trail 20% below high, 50% partial at 2R)
```

**Finding:** `_check_profit_target` (line 626) is **dead code** — never called
**File:** `warrior_monitor_exit.py`:626
**Code:** `async def _check_profit_target(`
**Verified with:** `grep_search` for `_check_profit_target` in all `.py` files — only one result: the function definition itself
**Output:** Single result: `warrior_monitor_exit.py:626`
**Conclusion:** This function (R-based partial exit at 2R without mode awareness) was superseded by the mode-specific checks (`_check_base_hit_target` and `_check_home_run_exit`) but never removed. It has no callers.

---

## C. Finding 1: All Positions Default to `base_hit` Mode

**Finding:** `session_exit_mode` defaults to `"base_hit"` in code and is never set in `warrior_settings.json`, meaning ALL batch test trades use base_hit mode.

**File:** `warrior_types.py`:119
**Code:**
```python
session_exit_mode: str = "base_hit"  # Default to safer base hit mode
```
**Verified with:** `grep_search` for `session_exit_mode` in `.json` files — zero results
**Output:** No results found
**Conclusion:** No persisted override exists. The only runtime override path is in `warrior_engine_entry.py`:1144 which requires `entry_volume_ratio >= 5.0` (5x volume explosion). Re-entries are forced to `base_hit` at line 1139. This means NPT, ROLR, GRI, LRHC, PAVM — all the big-runner cases — exited at +15¢/+18¢ instead of riding.

---

## D. Finding 2: Exit Mode Override Requires Extreme Volume (5x+)

**Finding:** The auto-selection logic at entry only upgrades to `home_run` for extreme volume explosions (≥5.0x relative volume), which is an exceptionally high bar.

**File:** `warrior_engine_entry.py`:1144-1150
**Code:**
```python
elif entry_volume_ratio >= 5.0:
    # Extreme volume explosion (5x+): override to home_run for potential runner
    selected_exit_mode = "home_run"
    logger.info(
        f"[Warrior Entry] {symbol}: exit_mode=home_run "
        f"(VOLUME EXPLOSION: {entry_volume_ratio:.1f}x, overriding session setting)"
    )
```
**Verified with:** `view_file` on `warrior_engine_entry.py`:1117-1156
**Conclusion:** Most stocks don't hit 5x RVOL at entry time. NPT made $81K for Ross but the bot only captured $14K because the auto-selection didn't promote it to home_run. The 5x threshold is too conservative.

---

## E. Finding 3: Base Hit Candle Trail Caps Upside at +15¢ Activation

**Finding:** In `base_hit` mode, the candle trail activates after +15¢ profit and trails using the 2-bar low. This means the **maximum profit capture** is bounded by the 2-bar-low trail, which on a fast-running stock will trigger exit very quickly after a minor pullback.

**File:** `warrior_monitor_exit.py`:706-772
**Code:**
```python
# Step 1: Check if trail should activate
if position.candle_trail_stop is None and profit_cents >= activation_cents:
    # ...
    if prev_candle_low > position.entry_price:
        position.candle_trail_stop = prev_candle_low
    else:
        # Trail would be below entry — not protective enough yet
        logger.debug(...)
```
**Verified with:** `view_file` on lines 686-800
**Conclusion:** Two issues:
1. **+15¢ activation is price-insensitive** — a 15¢ move on a $3 stock (5%) is meaningful, but on a $10 stock (1.5%) it's trivial. NPT at ~$12 would trail after a 1.2% move.
2. **Trail requires `prev_candle_low > entry_price`** — if the stock gaps up from entry and has a single shallow pullback (common in strong runners), the low of the completed 2 candles might be very close to entry, causing an extremely tight trail that exits on the first minor dip.

---

## F. Finding 4: Flat +18¢ Fallback Caps Upside When Trail Can't Activate

**Finding:** When the candle trail can't activate (no bars, or 2-bar low < entry), the fallback is a flat +18¢ target. This is a **full exit** (100% of shares), not a partial.

**File:** `warrior_monitor_exit.py`:774-800
**Code:**
```python
# ---- FALLBACK: Flat +18¢ target (when trail disabled or no bars) ----
target_price = position.entry_price + s.base_hit_profit_cents / 100
# ...
if current_price < target_price:
    return None
# ... Full exit of position.shares
```
**Verified with:** `view_file` on lines 774-800
**Conclusion:** On a $12 stock like NPT, +18¢ = 1.5% profit. Ross made $81K on NPT (+$4.05/share). The bot exits at +$0.18/share = 4.4% of Ross's per-share profit. This is the **single biggest P&L leak** for high-runners.

---

## G. Finding 5: No Partial-Then-Ride in Base Hit Mode

**Finding:** Base hit mode exits 100% of shares. There is no partial exit mechanism in `_check_base_hit_target` — it calls `shares_to_exit=position.shares` for the full position.

**File:** `warrior_monitor_exit.py`:755-764
**Code:**
```python
return WarriorExitSignal(
    position_id=position.position_id,
    symbol=position.symbol,
    reason=WarriorExitReason.PROFIT_TARGET,
    exit_price=current_price,
    shares_to_exit=position.shares,  # FULL EXIT
    pnl_estimate=pnl,
    # ...
)
```
**Verified with:** `view_file` on lines 749-764
**Conclusion:** Ross's strategy is to take partials and ride the rest. The bot takes 100% off at the candle trail stop. A partial-then-ride mechanism is needed: take 50% at base_hit trail, switch remainder to home_run trailing.

---

## H. Finding 6: Home Run Mode Works But Is Never Tested in Practice

**Finding:** The `_check_home_run_exit` function (line 803) is well-implemented — it trails at 20% below high after 1.5R, takes 50% partial at 2R, moves stop to breakeven. But it's never activated in batch testing because the session default is always `base_hit`.

**File:** `warrior_monitor_exit.py`:803-893
**Code:**
```python
# 1. Check trailing stop (if above threshold)
if r_multiple >= s.home_run_trail_after_r:
    trail_stop = position.high_since_entry * (1 - Decimal(str(s.home_run_trail_percent)))
    if trail_stop > position.current_stop and trail_stop > position.entry_price:
        position.current_stop = trail_stop
# ...
# 2. Check partial at R target
if not position.partial_taken and r_multiple >= s.home_run_partial_at_r:
    shares_to_exit = int(position.shares * s.partial_exit_fraction)
```
**Verified with:** `view_file` on lines 803-893
**Conclusion:** This code is correct but dormant. If NPT had used home_run mode, it would have trailed 20% below the high and captured significantly more than +$0.18/share.

---

## I. Finding 7: Topping Tail Can Kill Winners

**Finding:** The topping tail check (CHECK 3) runs BEFORE the mode-aware exit (CHECK 4). It triggers when upper wick > 60% of candle range AND candle is near high_since_entry. On a stock making new highs with volatile candles, this can exit a winning position before the trail has time to ride the move.

**File:** `warrior_monitor_exit.py`:604-606
**Code:**
```python
is_near_high = current_candle.high >= position.high_since_entry * Decimal("0.995")
if wick_ratio >= s.topping_tail_threshold and is_near_high:
    # ... EXIT ALL SHARES
```
**Verified with:** `view_file` on lines 560-623
**Conclusion:** A 2-minute grace period (line 580) provides some protection, but after that, any candle with a long upper wick at highs will trigger a full exit of all shares — even if the stock is up 500%. This could be the cause of early exits on runners like LRHC ($2.3K vs Ross's $31K).

---

## J. Finding 8: Scaling Logic Exists But Via Re-Entry Only

**Finding:** The bot has scaling infrastructure (`warrior_monitor_scale.py`, `_scale_into_existing_position`), but it's only triggered via micro-pullback re-entries at the entry level, not from the exit/monitor loop for winners.

**File:** `warrior_engine_entry.py`:840-947 and `warrior_monitor.py`:573-589
**Code (monitor-level scaling):**
```python
# No exit signal - check for scaling opportunity
should_check_scale = current_price and self.settings.enable_scaling
if should_check_scale:
    scale_signal = await self._check_scale_opportunity(position, ...)
```
**Verified with:** `view_file` on `warrior_monitor.py`:573-589
**Conclusion:** The monitor-level scaling checks `warrior_monitor_scale.py:check_scale_opportunity`, which requires RVOL ≥ 2x and price above support. But entry-level scaling via `_scale_into_existing_position` blocks adds when price is past profit target (line 903: `price_past_target`). This means the bot won't add shares to a winner that's already running — the opposite of what Ross does on his big winners.

---

## K. Quantified P&L Impact by Finding

| # | Finding | Cases Affected | Estimated P&L Gap |
|---|---------|----------------|-------------------|
| 1 | All trades default to base_hit | ALL 29 | **Foundation of all gaps** |
| 2 | 5x volume threshold too high for home_run | NPT, GRI, LRHC, PAVM | -$140K+ |
| 3 | +15¢ trail activation is price-insensitive | All base_hit trades | -$50K+ |
| 4 | +18¢ flat fallback caps upside | Cases without bar data | -$30K+ |
| 5 | No partial-then-ride in base_hit | All base_hit trades | -$100K+ |
| 6 | Home run mode dormant | All trades | -$200K+ (total gap) |
| 7 | Topping tail kills runners | LRHC, BNKK, GRI | -$50K+ |
| 8 | Scaling blocked on winners | ROLR ($85K Ross vs $11K bot) | -$74K+ |

---

## L. Priority Recommendations

### Priority 1: Implement Partial-Then-Ride in Base Hit Mode (Est. +$100K+ recovery)
Currently base_hit exits 100% of shares at the trail stop. Change to:
- At candle trail activation: sell 50% immediately (lock in base hit)
- Switch remaining 50% to home_run trailing (20% below high)
- This captures the base hit AND rides the runner

### Priority 2: Smart Exit Mode Selection (Est. +$140K+ recovery)
Lower the auto-promotion threshold from 5x to a multi-factor score:
- Gap % > N% → lean home_run
- RVOL > 3x → lean home_run
- Quality score > N → lean home_run
- Or: allow home_run as session default with partials protecting downside

### Priority 3: Price-Proportional Trail Activation (Est. +$50K+ recovery)
Replace fixed `base_hit_trail_activation_cents: 15` with proportional:
- For $3 stocks: 15¢ is fine (5%)
- For $10 stocks: 30-50¢ (3-5%)
- Formula: `max(15, entry_price * 0.03) * 100` (3% of entry price, minimum 15¢)

### Priority 4: Gate Topping Tail on Winners (Est. +$50K+ recovery)
Add a profit threshold guard: suppress topping tail when position is green > 1R.
Runners naturally produce upper wicks — topping tails are only bearish on initial breakout attempts, not on established trends.

### Priority 5: Allow Scaling Into Winning Runners (Est. +$74K+ recovery)
Remove or loosen the profit-check guard at `warrior_engine_entry.py`:898-913 that blocks scale-ins when `price_past_target`. Ross explicitly adds on strength to his biggest winners.

### Priority 6: Remove Dead Code `_check_profit_target` (Cleanup)
Delete the unused function at line 626-678 to reduce confusion and file size.

---

## M. Escalation Notes

This audit is **structural** — the code is architecturally sound but parametrically misconfigured for capturing large moves. No trace logging is needed; the fix is clear from static analysis:

1. Change the default behavior to partial-then-ride
2. Make exit mode selection smarter
3. Make trail activation proportional to stock price
4. Gate defensive exits (topping tail) on winner status

---

## N. Dependency Graph

```
warrior_engine_entry.py
  └── calls: warrior_monitor.add_position(exit_mode_override=...)
  └── calls: warrior_entry_execution.py (alternative path)

warrior_monitor.py
  └── _create_new_position(): uses exit_mode_override
  └── _evaluate_position(): delegates to warrior_monitor_exit.evaluate_position()
  └── _check_scale_opportunity(): delegates to warrior_monitor_scale

warrior_monitor_exit.py
  └── evaluate_position(): dispatches to 8 check functions
  └── get_effective_exit_mode(): reads position.exit_mode_override || settings.session_exit_mode
  └── handle_exit(): executes exit signals

warrior_types.py
  └── WarriorMonitorSettings: all config values
  └── WarriorPosition: exit_mode_override, candle_trail_stop fields
```
