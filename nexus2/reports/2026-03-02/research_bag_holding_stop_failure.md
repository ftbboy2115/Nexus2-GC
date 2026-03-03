# Research: Bag Holding / Stop Failure & Missed Profit-Taking

**Agent:** Backend Planner  
**Date:** 2026-03-02  
**Priority:** CRITICAL (P&L blocker #1)  
**Reference:** `handoff_planner_bag_holding.md`

---

## Executive Summary

The root cause of bag holding is **NOT a stop failure** — the stop DID fire correctly. The real problem is that **the stop was set absurdly wide** due to the consolidation-low-based stop method using sparse premarket data. For MNTS ($7.80 entry), the 5-bar consolidation low could have been as low as ~$6.50, making the technical stop ~$6.45 — a **17% drawdown tolerance** on what should be a quick scalp.

**Two distinct issues:**
1. **Wide stops from premarket consolidation lows** → positions survive massive drops before stops trigger
2. **No trailing profit protection** → positions reach +$1 profit during the day but give it all back because the stop never moves up

---

## Finding #1: Consolidation Low Produces Extremely Wide Stops

**Finding:** The `calculate_stop_price` function uses the lowest low of the last 5 candles as the stop basis, with only a 2¢ buffer below it. In sparse premarket (where bars span wide price ranges), this can produce stops 10-20% below entry.

**File:** [warrior_entry_sizing.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_entry_sizing.py):60-88  
**Code:**
```python
candles = await engine._get_intraday_bars(symbol, "1min", limit=5)
if candles and len(candles) >= 1:
    # MULTI-CANDLE LOW: Use lowest low of last 5 candles (consolidation support)
    consolidation_low = min(Decimal(str(c.low)) for c in candles)
    entry_candle_low = Decimal(str(candles[-1].low))
    
    # Use consolidation low as support, with 2¢ buffer
    calculated_candle_low = consolidation_low
    mental_stop = consolidation_low - Decimal("0.02")
    stop_method = "consolidation_low"
```

**Impact:** For MNTS:
- Entry: $7.80 at 08:00  
- 5-bar premarket lows could include bars from first minutes of premarket when MNTS was at $6.49 (previous close)
- Consolidation low ≈ $6.50 → mental stop ≈ $6.48
- This means the stock can drop $1.32 (17%) before the stop fires

**Cap exists but is too wide:**
```python
max_stop_pct: float = 0.10  # 10% cap
```
Even capped at 10%, stop is $7.02 — still allows a $0.78 drawdown on a base_hit trade that's targeting +$0.18.

**Conclusion:** The risk/reward is inverted: **risking $0.78-$1.32 to make $0.18**. This is the fundamental P&L destroyer.

---

## Finding #2: Technical Stop Overrides Mental Stop in Monitor

**Finding:** When a `support_level` (calculated candle low) is available, the monitor uses it as the `current_stop`, ignoring the tighter mental stop (15¢).

**File:** [warrior_monitor.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_monitor.py):405-428  
**Code:**
```python
# Mental stop: 15¢ below entry (base_hit mode)
mental_stop = entry_price - s.base_hit_stop_cents / 100  # $7.80 - $0.15 = $7.65

# Technical stop: calculated from support_level
if support_level and s.use_technical_stop:
    technical_stop = support_level - s.technical_stop_buffer_cents / 100

# CRITICAL: Candle low is PRIMARY, mental stop is FALLBACK
if technical_stop and s.use_candle_low_stop:
    current_stop = technical_stop  # ← THIS IS THE WIDE STOP
else:
    current_stop = mental_stop    # ← THIS IS NEVER USED when candle data exists
```

**Settings (warrior_types.py):**
```python
mental_stop_cents: Decimal("50")      # 50¢ FALLBACK (line 62)
base_hit_stop_cents: Decimal("15")    # 15¢ for base_hit (line 171)
use_candle_low_stop: bool = True      # Candle low is PRIMARY (line 63)
use_technical_stop: bool = True       # Use support levels (line 64)
```

**Conclusion:** The architecture always prefers the wide consolidation-low stop. The 15¢ mental stop is dead code in practice.

---

## Finding #3: Stop Check Logic is Correct

**Finding:** The `_check_stop_hit` function itself works correctly. If `current_price <= position.current_stop`, it fires. The issue is only with WHAT value `current_stop` is set to.

**File:** [warrior_monitor_exit.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py):402-435  
**Code:**
```python
def _check_stop_hit(position, current_price, r_multiple):
    if current_price > position.current_stop:
        return None  # Price above stop → no exit
    # ... generate exit signal
```

**Conclusion:** No bug here. Stop check works as designed.

---

## Finding #4: Monitor Runs Every Sim Minute — No Polling Gap

**Finding:** In simulation, `step_clock_ctx` calls `_check_all_positions()` on every clock step (every 1 minute or 10 seconds). There is no polling gap.

**File:** [sim_context.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/simulation/sim_context.py):170-186  
**Code:**
```python
# Check positions for exits (monitor tick)
if ctx.monitor._positions:
    await ctx.monitor._check_all_positions()
```

**Conclusion:** No polling gap. Stops are checked every minute in sim.

---

## Finding #5: After-Hours Exit is the Backstop — Not the Problem

**Finding:** `after_hours_exit` fires at 19:30 ET as a forced exit. It exists to prevent overnight holds. The real question is: WHY was the position still open at 19:30?

**File:** [warrior_monitor_exit.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py):228  
**Code:**
```python
# Force exit at 7:30 PM ET with ESCALATING offset
if current_time_str >= s.force_exit_time_et:
```

**Answer:** Because the wide stop never fired. MNTS entered at $7.80, stop was set to ~$6.45-$7.02 (depending on candle data), and the price slowly declined from $7.80 to $6.14 over the day. The stop would only fire when price crosses below $6.45-$7.02. If MNTS didn't drop sharply below the stop but hovered above it until after-hours when it gapped down to $6.14, the after-hours exit caught it.

---

## Finding #6: No Trailing Stop for Base Hit Mode in Practice

**Finding:** The candle trail (base_hit's trailing mechanism) requires the price to first reach `activation_cents` (15¢) above entry AND the candle low must be above entry price before activating. If MNTS never reached $7.95 with a sustained move, the trail would never activate.

**File:** [warrior_monitor_exit.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py):783-813  
**Code:**
```python
# Step 1: Check if trail should activate
if position.candle_trail_stop is None and profit_cents >= activation_cents:
    # ... lookup candle low
    # Only activate if trail stop would be above entry (protective)
    if prev_candle_low > position.entry_price:
        position.candle_trail_stop = prev_candle_low
```

**Conclusion:** Trail activates only when position is profitable AND candle low is above entry. This means positions that briefly go green then turn red never get trailing protection.

---

## Finding #7: MFE Tracking Exists but Isn't Used for Exits

**Finding:** The code tracks `high_since_entry` (MFE) in `evaluate_position`, but this is only used for informational logging. There is no exit that says "if price drops X% from high_since_entry, exit."

**File:** [warrior_monitor_exit.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py):1267-1274  
**Code:**
```python
# Update high since entry (MFE tracking)
if current_price > position.high_since_entry:
    position.high_since_entry = current_price
```

**Conclusion:** MFE data is captured but not used for risk management. This is the missed profit-taking issue.

---

## Ghost Trades ($0 P&L, No Exit)

**Hypothesis:** These are likely trades that were entered via `log_warrior_entry` (intent logging to DB) but the monitor never processed them because the sim clock moved past them quickly (entry and immediate exit before any significant price move), or they were duplicate DB entries from scaling that share the same symbol but different position IDs.

**Not investigated further** — requires running a specific batch case with verbose logging to trace.

---

## Proposed Fix (Spec for Backend Specialist)

### Fix 1: Cap Max Stop Distance for Base Hit Mode (HIGH PRIORITY)

**Rationale:** A base_hit trade targets +18¢ profit. Risking more than 30-50¢ is irrational.

**Where:** `warrior_entry_sizing.py:71-82` and/or `warrior_monitor.py:422-428`

**Approach:** Add a `base_hit_max_stop_cents` setting (e.g., 30¢) that caps `current_stop` to `entry_price - base_hit_max_stop_cents / 100`, regardless of what the consolidation low says.

```python
# In _create_new_position:
if exit_mode == "base_hit":
    max_stop_distance = s.base_hit_max_stop_cents / 100  # e.g., 30¢
    min_stop = entry_price - max_stop_distance
    current_stop = max(current_stop, min_stop)  # Use tighter of candle low and max distance
```

**Estimated P&L Impact:** MNTS would stop at ~$7.50 instead of $6.14, saving ~$12K.

### Fix 2: MFE-Based Trailing Protection (MEDIUM PRIORITY)

**Rationale:** When a position reaches +$0.50 from entry, the stop should trail upward. Currently there's no protection against round-tripping profits.

**Where:** `warrior_monitor_exit.py` — new exit check between CHECK 0.7 (time stop) and CHECK 1 (stop hit)

**Approach:** If `high_since_entry - current_price > mfe_trail_cents`, generate an exit signal:
```python
# MFE protection: if price dropped X cents from the high, exit
mfe_drawdown = position.high_since_entry - current_price
if mfe_drawdown > s.mfe_trail_cents / 100:
    # Generate exit signal
```

### Fix 3: Use Entry Bar Low Instead of 5-Bar Consolidation (LOW PRIORITY)

**Rationale:** The 5-bar consolidation low spans too much time in premarket. The entry bar's low is a more relevant support level.

**Where:** `warrior_entry_sizing.py:62-68`

**Approach:** Replace `min(c.low for c in candles)` with `candles[-1].low` (entry bar only).

---

## Wiring Checklist (for Backend Specialist)

### Fix 1: Base Hit Max Stop Cap
- [ ] Add `base_hit_max_stop_cents: Decimal = Decimal("30")` to `WarriorMonitorSettings` in `warrior_types.py`
- [ ] Modify `_create_new_position` in `warrior_monitor.py` to apply cap when `exit_mode == "base_hit"`
- [ ] Expose new setting via `/warrior/monitor/settings` API
- [ ] Add to `warrior_settings_batch.json` for batch testing

### Fix 2: MFE Trail
- [ ] Add `enable_mfe_trail: bool` and `mfe_trail_cents: Decimal` to `WarriorMonitorSettings`
- [ ] Create `_check_mfe_trail()` function in `warrior_monitor_exit.py`
- [ ] Wire into `evaluate_position()` between CHECK 0.7 and CHECK 1
- [ ] Add `MFE_TRAIL` to `WarriorExitReason` enum in `warrior_types.py`

### Fix 3: Entry Bar Low
- [ ] Modify `warrior_entry_sizing.py:63` to use `candles[-1].low` instead of `min(c.low for c in candles)`
- [ ] Keep 5-bar consolidation as A/B testable option via config flag

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Fix 1 caps stop too tight → more stop-outs | Win rate drops | Make cap configurable, backtest with param sweep |
| Fix 2 MFE trail too tight → cuts winners short | P&L drag from premature exits | Set generous default (e.g., 50¢), A/B testable |
| Fix 3 entry bar low too tight → frequent stops | Same as Fix 1 | A/B test vs consolidation low |

---

## Verification Plan

1. Run batch test with current settings → baseline P&L
2. Apply Fix 1 (30¢ cap) → rerun batch → compare
3. Apply Fix 2 (MFE trail) → rerun batch → compare
4. Check MNTS and HIND cases specifically — confirm they exit before after_hours
5. Verify no regressions on winner cases (NPT, MLEC, HIND)
