# Technical Spec: Fix 1 — Partial-Then-Ride

**Date:** 2026-02-16  
**Author:** Backend Planner  
**Deliverable For:** Backend Specialist  
**Feature:** Convert base_hit 100%-exit to 50%-partial + home_run trailing on remainder  
**Toggle:** `enable_partial_then_ride: bool = True` on `WarriorMonitorSettings`

---

## Context

The Warrior bot captures ~13% of Ross Cameron's P&L. The primary cause: **every base_hit exit sells 100% of shares** at +15¢ candle trail or +18¢ flat. Ross always takes partials at structural levels, then rides the rest.

This spec implements the **simplest possible** A/B-testable change: when the base_hit candle trail fires, sell 50% and switch the remaining 50% to `home_run` trailing mode.

### Strategy Alignment

From `warrior.md` §9.1: *"Never sells everything at once — always partial exits"*  
From research: *"Ross always takes partials at structural levels, never full exits on winners"*

---

## A. Existing Pattern Analysis (Template)

The `_check_home_run_exit` function at L852-891 already implements partial exits correctly. This is the **exact template** to follow:

| Aspect | `_check_home_run_exit` (L852-891) | Template for `_check_base_hit_target` |
|--------|-----------------------------------|---------------------------------------|
| **Partial calc** | `shares_to_exit = int(position.shares * s.partial_exit_fraction)` (L854) | Same formula |
| **P&L calc** | `pnl = (current_price - position.entry_price) * shares_to_exit` (L858) | Same formula |
| **Mark partial** | `position.partial_taken = True` (L865) | Same |
| **Decrement shares** | `position.shares -= shares_to_exit` (L866) | Same |
| **Move stop to BE** | `position.current_stop = position.entry_price` (L870) | Same |
| **Log event** | `trade_event_service.log_warrior_breakeven(...)` (L873) | Same |
| **Increment counter** | `monitor.partials_triggered += 1` (L880) | Same |
| **Return signal** | `WarriorExitSignal(reason=PARTIAL_EXIT, ...)` (L882-891) | Same |

### Critical Template Code (copy-pasted from L852-891)

```python
# 2. Check partial at R target (if not already taken)
if not position.partial_taken and r_multiple >= s.home_run_partial_at_r:
    shares_to_exit = int(position.shares * s.partial_exit_fraction)
    if shares_to_exit < 1:
        return None
    
    pnl = (current_price - position.entry_price) * shares_to_exit
    
    logger.info(
        f"[Warrior] {position.symbol}: HOME RUN {s.home_run_partial_at_r}R target hit "
        f"at {r_multiple:.1f}R -> Partial exit ({shares_to_exit} shares)"
    )
    
    position.partial_taken = True
    position.shares -= shares_to_exit
    
    # Move stop to breakeven
    if s.home_run_move_to_be:
        position.current_stop = position.entry_price
        if monitor._update_stop:
            await monitor._update_stop(position.position_id, position.entry_price)
        trade_event_service.log_warrior_breakeven(
            position_id=position.position_id,
            symbol=position.symbol,
            entry_price=position.entry_price,
        )
        logger.info(f"[Warrior] {position.symbol}: Stop moved to breakeven")
    
    monitor.partials_triggered += 1
    
    return WarriorExitSignal(
        position_id=position.position_id,
        symbol=position.symbol,
        reason=WarriorExitReason.PARTIAL_EXIT,
        exit_price=current_price,
        shares_to_exit=shares_to_exit,
        pnl_estimate=pnl,
        r_multiple=r_multiple,
        trigger_description=f"Home run {s.home_run_partial_at_r}:1 R target hit",
    )
```

---

## B. Change Surface Enumeration

| # | File | Change | Location | Template |
|---|------|--------|----------|----------|
| 1 | `warrior_types.py` | Add config flag `enable_partial_then_ride: bool = True` | After L131 (home_run settings block) | Other bool flags in same dataclass |
| 2 | `warrior_monitor_exit.py` | Modify `_check_base_hit_target` candle trail hit path to partial | L749-764 | `_check_home_run_exit` L852-891 |
| 3 | `warrior_monitor_exit.py` | Modify `_check_base_hit_target` flat fallback to partial | L786-800 | Same template |
| 4 | `warrior_monitor_exit.py` | After partial, switch position to `home_run` mode | Inline at change #2 and #3 | `position.exit_mode_override = "home_run"` |
| 5 | `warrior_monitor_exit.py` | Reset `candle_trail_stop` after Mode switch | Inline at change #2 and #3 | Set to `None` |
| 6 | `warrior_monitor_settings.py` | Add `enable_partial_then_ride` to `get_monitor_settings_dict` | L98-118 | Same pattern as other keys |
| 7 | `warrior_monitor_settings.py` | Add `enable_partial_then_ride` to `apply_monitor_settings` | L64-95 | Same pattern as other keys |

---

## C. Detailed Change Specifications

### Change #1: Config Flag on `WarriorMonitorSettings`

**File:** [warrior_types.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_types.py)  
**Location:** After L131 (`home_run_move_to_be: bool = True`), before the `WarriorPosition` class at L137

**Current Code (L128-134):**
```python
    home_run_partial_at_r: float = 2.0  # Take 50% partial at 2:1 R
    home_run_trail_after_r: float = 1.5  # Start trailing stop after 1.5R
    home_run_trail_percent: float = 0.20  # Trail 20% below high_since_entry
    home_run_move_to_be: bool = True  # Move stop to breakeven after partial


@dataclass
class WarriorPosition:
```

**Approach:** Add a new config flag in the exit mode config section, between the home_run settings and the `WarriorPosition` class:

```python
    home_run_move_to_be: bool = True  # Move stop to breakeven after partial
    
    # Partial-Then-Ride (Fix 1: A/B testable)
    # When True: base_hit exits sell 50% and switch remainder to home_run trailing
    # When False: base_hit exits sell 100% (current behavior)
    enable_partial_then_ride: bool = True
```

**Dependencies:** None — this is a dataclass field with a default.

---

### Change #2: Candle Trail Hit → Partial (PRIMARY CHANGE)

**File:** [warrior_monitor_exit.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py)  
**Location:** `_check_base_hit_target`, L748-764 — the candle trail stop hit block

**Current Code (L748-764):**
```python
            # Step 3: Check if trail stop hit
            if current_price <= position.candle_trail_stop:
                pnl = (current_price - position.entry_price) * position.shares
                logger.info(
                    f"[Warrior] {position.symbol}: CANDLE TRAIL STOP HIT at ${current_price:.2f} "
                    f"(trail=${position.candle_trail_stop:.2f}) → Full exit, P&L=${float(pnl):.2f}"
                )
                return WarriorExitSignal(
                    position_id=position.position_id,
                    symbol=position.symbol,
                    reason=WarriorExitReason.PROFIT_TARGET,
                    exit_price=current_price,
                    shares_to_exit=position.shares,
                    pnl_estimate=pnl,
                    r_multiple=r_multiple,
                    trigger_description=f"Candle trail stop hit (trail=${position.candle_trail_stop:.2f})",
                )
```

**Approach:** Replace the full-exit block with a conditional:
- If `enable_partial_then_ride` is ON and `partial_taken` is False:
  - Calculate `shares_to_exit` = 50% of `position.shares`
  - Set `position.partial_taken = True`
  - Decrement `position.shares -= shares_to_exit` 
  - Set `position.exit_mode_override = "home_run"` (mode switch)
  - Set `position.candle_trail_stop = None` (clear stale trail)
  - Move stop to breakeven (`position.current_stop = position.entry_price`)
  - Log breakeven event
  - Return `PARTIAL_EXIT` signal
- If `enable_partial_then_ride` is OFF or `partial_taken` is True:
  - Full exit (current behavior — sell all remaining shares)

**Template:** `_check_home_run_exit` L852-891 (see Section A)

> [!IMPORTANT]
> The `import` for `trade_event_service` must be added at the top of `_check_base_hit_target`. Currently, `_check_base_hit_target` does NOT import `trade_event_service` — only `_check_home_run_exit` does (at L817). Add `from nexus2.domain.automation.trade_event_service import trade_event_service` inside the function.

---

### Change #3: Flat Fallback Hit → Partial

**File:** [warrior_monitor_exit.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py)  
**Location:** `_check_base_hit_target`, L786-800 — the flat +18¢ fallback exit

**Current Code (L786-800):**
```python
    pnl = (current_price - position.entry_price) * position.shares
    logger.info(
        f"[Warrior] {position.symbol}: BASE HIT flat target hit at ${current_price:.2f} "
        f"(+{s.base_hit_profit_cents}¢ target) -> Full exit"
    )
    return WarriorExitSignal(
        position_id=position.position_id,
        symbol=position.symbol,
        reason=WarriorExitReason.PROFIT_TARGET,
        exit_price=current_price,
        shares_to_exit=position.shares,
        pnl_estimate=pnl,
        r_multiple=r_multiple,
        trigger_description=f"Base hit +{s.base_hit_profit_cents}¢ flat target hit (candle trail unavailable)",
    )
```

**Approach:** Same conditional branching as Change #2:
- If `enable_partial_then_ride` ON and `partial_taken` False → partial exit + mode switch
- Otherwise → full exit (current behavior)

---

### Change #4: Position Mode Switch (Inline in #2 and #3)

When the partial fires, the remaining shares must switch to `home_run` trailing. This is done inline:

```python
position.exit_mode_override = "home_run"
```

**Why this works:** `get_effective_exit_mode()` at L39-54 already checks `position.exit_mode_override` first:
```python
def get_effective_exit_mode(monitor, position):
    if position.exit_mode_override:
        return position.exit_mode_override
    return monitor.settings.session_exit_mode
```

On the next `evaluate_position` call, the dispatch at L998-1007 will route to `_check_home_run_exit` instead of `_check_base_hit_target`.

---

### Change #5: Clear Candle Trail Stop (Inline in #2 and #3)

When switching to `home_run` mode, the `candle_trail_stop` must be cleared to prevent interference:

```python
position.candle_trail_stop = None
```

**Why this matters:** `_check_home_run_exit` uses `position.current_stop` and `position.high_since_entry` for its trailing logic. The `candle_trail_stop` is only used by `_check_base_hit_target`. If left set, it won't directly interfere (different function), but it's cleaner to reset.

> [!NOTE]
> `_check_home_run_exit` does NOT read `position.candle_trail_stop`. It only uses:
> - `position.high_since_entry` (for trailing calc at L823)
> - `position.current_stop` (for stop comparison at L836)
> - `position.partial_taken` (already set to True after our partial)
> - `position.shares` (already decremented)
> 
> So clearing `candle_trail_stop` is hygiene, not strictly necessary. But recommended.

---

### Change #6: Settings Persistence — `get_monitor_settings_dict`

**File:** [warrior_monitor_settings.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/db/warrior_monitor_settings.py)  
**Location:** `get_monitor_settings_dict`, L98-118

**Current Code (L98-118):**
```python
def get_monitor_settings_dict(monitor_settings_obj) -> dict:
    """Convert WarriorMonitorSettings to a saveable dictionary."""
    return {
        "mental_stop_cents": float(monitor_settings_obj.mental_stop_cents),
        # ... (15 more fields)
        "move_stop_to_breakeven_after_scale": monitor_settings_obj.move_stop_to_breakeven_after_scale,
    }
```

**Approach:** Add one line at the end of the dict:
```python
        "enable_partial_then_ride": monitor_settings_obj.enable_partial_then_ride,
```

---

### Change #7: Settings Persistence — `apply_monitor_settings`

**File:** [warrior_monitor_settings.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/db/warrior_monitor_settings.py)  
**Location:** `apply_monitor_settings`, L64-95

**Current Code (L93-95):**
```python
    if "move_stop_to_breakeven_after_scale" in settings:
        monitor_settings_obj.move_stop_to_breakeven_after_scale = settings["move_stop_to_breakeven_after_scale"]
    
    print(f"[Warrior Monitor Settings] Applied: enable_scaling={monitor_settings_obj.enable_scaling}")
```

**Approach:** Add before the print statement:
```python
    if "enable_partial_then_ride" in settings:
        monitor_settings_obj.enable_partial_then_ride = settings["enable_partial_then_ride"]
```

---

## D. Wiring Checklist

- [ ] Config flag `enable_partial_then_ride: bool = True` added to `WarriorMonitorSettings` (`warrior_types.py`)
- [ ] `_check_base_hit_target` candle trail hit path (L749-764) converted to partial when flag is ON
- [ ] `_check_base_hit_target` flat fallback path (L786-800) converted to partial when flag is ON
- [ ] After partial: `position.partial_taken = True`
- [ ] After partial: `position.shares -= shares_to_exit`
- [ ] After partial: `position.exit_mode_override = "home_run"` (mode switch)
- [ ] After partial: `position.candle_trail_stop = None` (clear stale trail)
- [ ] After partial: `position.current_stop = position.entry_price` (breakeven stop)
- [ ] After partial: `trade_event_service.log_warrior_breakeven(...)` called
- [ ] After partial: `monitor.partials_triggered += 1`
- [ ] Signal uses `WarriorExitReason.PARTIAL_EXIT` (not `PROFIT_TARGET`)
- [ ] Persistence: `enable_partial_then_ride` in `get_monitor_settings_dict` (`warrior_monitor_settings.py`)
- [ ] Persistence: `enable_partial_then_ride` in `apply_monitor_settings` (`warrior_monitor_settings.py`)
- [ ] Full exit path preserved as fallback when `enable_partial_then_ride=False` or `partial_taken=True`

---

## E. Risk Assessment

### What Could Break

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Shares tracking after partial** | LOW | `handle_exit` already handles `PARTIAL_EXIT` correctly — it skips `_mark_pending_exit` (L1032), skips position removal (L1143), and logs via `log_warrior_partial_exit` (L1076). Template from `_check_home_run_exit` proves this works. |
| **Position state persists across ticks** | LOW | `_check_all_positions` iterates `list(self._positions.items())` (L561). Position object is mutable and shared — changes to `shares`, `partial_taken`, `exit_mode_override` persist until next eval cycle. Verified by existing `_check_home_run_exit` partial behavior. |
| **Home run mode takes over after partial** | LOW | `get_effective_exit_mode` returns `exit_mode_override` first (L52-53). After setting `position.exit_mode_override = "home_run"`, the dispatch at L998-1003 routes to `_check_home_run_exit`. This function will then trail at 20% below high and use `current_stop` (now set to breakeven). |
| **Second partial in home_run mode** | NONE | After our partial, `position.partial_taken = True`. The home_run partial guard at L853 (`if not position.partial_taken`) will skip. Only the trailing stop (L822-850) will be active. |
| **Re-entry callback triggered** | LOW | `handle_exit` only calls `_on_profit_exit` for `PROFIT_TARGET` reason (L1156-1158), NOT for `PARTIAL_EXIT`. So partial exit won't trigger re-entry. Full exit of remainder (via home_run trail stop hit with `PROFIT_TARGET` reason) WILL trigger re-entry correctly. |
| **Batch testing regression** | MEDIUM | Toggle default is `True`. To A/B test, run batch with `True` vs `False`. All existing test cases should see different (better) P&L on winners. |

### What to Test

1. **Basic partial flow:** Position enters base_hit mode, candle trail activates at +15¢, trail stop hit → 50% partial exits, remainder switches to home_run mode
2. **Flat fallback partial:** No candle data → flat +18¢ hit → 50% partial, remainder switches
3. **Toggle OFF:** `enable_partial_then_ride=False` → current 100% exit behavior preserved
4. **Already-partialed position:** If `partial_taken=True` when base_hit trail fires → full exit of remaining shares
5. **Mode switch verification:** After partial, next `evaluate_position` call routes to `_check_home_run_exit` instead of `_check_base_hit_target`
6. **Batch regression:** Run full 29-case batch test with flag ON vs OFF, compare total P&L

### Verification Commands

```powershell
# Import check (no syntax errors)
python -c "from nexus2.domain.automation.warrior_monitor_exit import _check_base_hit_target; print('OK')"

# Config flag check
python -c "from nexus2.domain.automation.warrior_types import WarriorMonitorSettings; s = WarriorMonitorSettings(); print(f'enable_partial_then_ride={s.enable_partial_then_ride}')"

# Settings persistence check
python -c "from nexus2.db.warrior_monitor_settings import get_monitor_settings_dict; from nexus2.domain.automation.warrior_types import WarriorMonitorSettings; d = get_monitor_settings_dict(WarriorMonitorSettings()); print('partial_then_ride' in str(d))"

# Unit tests
python -m pytest nexus2/tests/unit/automation/test_warrior_monitor.py -v --tb=short

# Batch test (A/B comparison)
python -m nexus2.adapters.simulation.batch_runner
```

---

## F. Open Question Answers (from Handoff)

### Q1: What happens when `position.shares` is decremented after partial?

**Answer:** `handle_exit()` at L1017-1189 uses `signal.shares_to_exit` for the actual sell order (L1037: `result = await monitor._execute_exit(signal)`). The signal contains the pre-calculated `shares_to_exit` value. After the signal is returned, `handle_exit` checks `signal.reason != WarriorExitReason.PARTIAL_EXIT` at L1032 and L1143 — for partials, it skips both `_mark_pending_exit` and `remove_position`. The position remains in `self._positions` with the decremented `shares` value.

**Evidence:** L1032: `if signal.reason != WarriorExitReason.PARTIAL_EXIT:` and L1143: `if signal.reason != WarriorExitReason.PARTIAL_EXIT:`

### Q2: Does `position.shares -= shares_to_exit` work across monitor evaluation cycles?

**Answer:** Yes. `_check_all_positions` at L561 iterates `list(self._positions.items())`. The position objects are Python dataclass instances stored in `self._positions` dict — mutations to `position.shares` persist in memory across cycles. This is already proven by `_check_home_run_exit` at L866 which does exactly the same thing.

**Evidence:** L561: `for position_id, position in list(self._positions.items()):`

### Q3: Should `candle_trail_stop` be reset to None when switching to home_run?

**Answer:** Yes, for hygiene. `_check_home_run_exit` does NOT read `candle_trail_stop` — it uses `position.current_stop` and `position.high_since_entry`. So there's no functional interference, but clearing it prevents confusion if the position were to somehow switch back to base_hit mode (which shouldn't happen, but defensive coding).

### Q4: Does `warrior_settings.json` persistence need updating?

**Answer:** No. `warrior_settings.json` (via `warrior_settings.py`) persists **engine config** (`WarriorEngineConfig`), not monitor settings. Monitor settings are persisted separately via `warrior_monitor_settings.json` (in `warrior_monitor_settings.py`). The new flag belongs on `WarriorMonitorSettings`, so only `warrior_monitor_settings.py` needs updating (Changes #6 and #7).

**Evidence:** `get_config_dict` at `warrior_settings.py:133-154` serializes engine fields (max_positions, risk_per_trade, etc.). `get_monitor_settings_dict` at `warrior_monitor_settings.py:98-118` serializes monitor fields (mental_stop_cents, enable_scaling, etc.).

### Q5: Are there tests in `test_warrior_monitor.py` that need updating?

**Answer:** The test file has 72 test items. The `TestProfitTarget` class (L208-281) tests home_run mode partials. There are no tests specifically for `_check_base_hit_target`. The implementer should add new test cases for the partial-then-ride path. Existing tests should continue to pass because they use `home_run` mode or test other exit conditions.

### Q6: What happens with trade_event_service logging?

**Answer:** The implementer must add `trade_event_service.log_warrior_breakeven(...)` call after the partial, same as `_check_home_run_exit` does at L873. The `handle_exit` function already handles `PARTIAL_EXIT` logging correctly at L1075-1083 via `trade_event_service.log_warrior_partial_exit(...)`.
