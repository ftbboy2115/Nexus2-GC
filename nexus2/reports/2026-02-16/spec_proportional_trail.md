# Technical Spec: Fix 2 — Price-Proportional Trail Activation

**Date:** 2026-02-16  
**Author:** Backend Planner  
**For:** Backend Specialist  
**Handoff:** [handoff_planner_fix2.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-02-16/handoff_planner_fix2.md)

---

## Summary

Replace the fixed +15¢ candle trail activation threshold with a price-proportional formula: `max(15, entry_price_dollars * 3)` in cents. This ensures the trail activates at ~3% of entry price with a 15¢ floor, preventing premature trail activation on higher-priced stocks.

The flat +18¢ fallback target should **also** be made proportional using the same approach: `max(18, entry_price_dollars * 3.5)` in cents.

---

## A. Price Analysis Across 38 Test Cases

| Symbol | Entry $ | Fixed 15¢ | 3% (cents) | max() | % of Price | Change? |
|--------|---------|-----------|------------|-------|------------|---------|
| CMCT | 4.65 | 15 | 14.0 | **15** | 3.23% | No |
| OPTX | 3.50 | 15 | 10.5 | **15** | 4.29% | No |
| ACON | 8.30 | 15 | 24.9 | **25** | 3.00% | ✅ +10¢ |
| FLYX | 6.20 | 15 | 18.6 | **19** | 3.00% | ✅ +4¢ |
| ELAB | 10.55 | 15 | 31.7 | **32** | 3.00% | ✅ +17¢ |
| LCFY | 7.50 | 15 | 22.5 | **22** | 3.00% | ✅ +7¢ |
| PAVM | 12.31 | 15 | 36.9 | **37** | 3.00% | ✅ +22¢ |
| ROLR | 15.00 | 15 | 45.0 | **45** | 3.00% | ✅ +30¢ |
| NPT | 10.00 | 15 | 30.0 | **30** | 3.00% | ✅ +15¢ |
| BNAI | 33.81 | 15 | 101.4 | **101** | 3.00% | ✅ +86¢ |
| RNAZ | 12.00 | 15 | 36.0 | **36** | 3.00% | ✅ +21¢ |
| EVMN | 36.00 | 15 | 108.0 | **108** | 3.00% | ✅ +93¢ |
| VELO | 16.00 | 15 | 48.0 | **48** | 3.00% | ✅ +33¢ |
| RDIB | 15.00 | 15 | 45.0 | **45** | 3.00% | ✅ +30¢ |
| GWAV | 3.00 | 15 | 9.0 | **15** | 5.00% | No |
| VERO | 3.00 | 15 | 9.0 | **15** | 5.00% | No |
| HIND | 5.00 | 15 | 15.0 | **15** | 3.00% | No |
| PMI | 2.50 | 15 | 7.5 | **15** | 6.00% | No |

**Impact:** 20 of 38 cases (53%) would see a higher threshold. No cases see a *lower* threshold (floor guarantees this). Stocks ≥$5.01 are affected.

---

## B. Open Question Decisions

### Q1: Why 3%?
- At 3%, the crossover point is exactly $5.00 (15¢ / 0.03 = $5.00)
- Stocks ≤$5 keep the familiar 15¢ behavior (unchanged for ~half the test suite)
- Stocks at $10-15 get 30-45¢ activation — prevents premature trail on a 1.5% blip
- The highest case (EVMN at $36) gets $1.08 activation — ~3% = still reasonable

### Q2: Should the flat fallback (+18¢) also be proportional?
**Yes.** Same price-insensitivity problem. Formula: `max(18, entry_price * 3.5)` cents.
- Uses 3.5% (slightly higher than trail activation at 3%) to maintain `fallback > activation`
- $3 stock: 18¢ fallback (unchanged), $10 stock: 35¢ fallback, $15 stock: 52¢ fallback

### Q3: Interaction with candle trail lookback?
**No change needed.** The 2-bar lookback is independent — it defines *what* the trail level is. The activation threshold defines *when* tracing begins. Higher activation just delays start, but 2-bar low still works correctly once active.

### Q5: Config toggle approach?
**Add a new percentage field alongside the existing fixed field.** Keep `base_hit_trail_activation_cents` as the floor minimum. Add `trail_activation_pct: float = 3.0`. At runtime compute: `max(fixed_floor, pct * entry)`. Setting `trail_activation_pct = 0.0` disables proportional behavior (A/B test toggle).

Same pattern for the fallback: add `base_hit_profit_pct: float = 3.5`.

### Q6: Monitor settings persistence?
**Yes, needs updates** to both `get_monitor_settings_dict` and `apply_monitor_settings`.

---

## C. Change Surface Enumeration

| # | File | Change | Location | Template |
|---|------|--------|----------|----------|
| 1 | `warrior_types.py` | Add `trail_activation_pct` field | Line 128 | Existing float fields pattern |
| 2 | `warrior_types.py` | Add `base_hit_profit_pct` field | Line 123 | Same |
| 3 | `warrior_monitor_exit.py` | Compute proportional trail activation | Line 708 | — |
| 4 | `warrior_monitor_exit.py` | Compute proportional flat fallback | Line 824 | — |
| 5 | `warrior_monitor_settings.py` | Add fields to `get_monitor_settings_dict` | Line 100-121 | Existing pattern |
| 6 | `warrior_monitor_settings.py` | Add fields to `apply_monitor_settings` | Line 64-97 | Existing pattern |

---

## D. Detailed Change Specifications

### Change Point #1: Add `trail_activation_pct` to WarriorMonitorSettings

**File:** [warrior_types.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_types.py)  
**Location:** `WarriorMonitorSettings`, after line 128  
**Current Code (lines 125-128):**
```python
    # Base Hit Candle Trail (Phase A — Ross Cameron candle-low trailing)
    base_hit_candle_trail_enabled: bool = True  # Enable candle-low trailing for base_hit
    base_hit_trail_activation_cents: Decimal = Decimal("15")  # Start trailing after +15¢ (was 10¢)
    candle_trail_lookback_bars: int = 2  # Trail = lowest low of last N completed candles (was 1)
```
**Approach:** Add `trail_activation_pct: float = 3.0` after line 128. This field controls the percentage used in the proportional calculation. When set to `0.0`, only the fixed floor is used (effectively disabling proportional mode).

---

### Change Point #2: Add `base_hit_profit_pct` to WarriorMonitorSettings

**File:** [warrior_types.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_types.py)  
**Location:** `WarriorMonitorSettings`, after line 122  
**Current Code (lines 121-123):**
```python
    # Base Hit Mode Settings
    base_hit_profit_cents: Decimal = Decimal("18")  # Take profit at +18¢ (Ross's typical)
    base_hit_stop_cents: Decimal = Decimal("15")  # Mental stop at -15¢
```
**Approach:** Add `base_hit_profit_pct: float = 3.5` after line 122. This field controls the percentage for the flat fallback target.

---

### Change Point #3: Compute proportional trail activation

**File:** [warrior_monitor_exit.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py)  
**Location:** `_check_base_hit_target()`, line 708  
**Current Code (lines 707-711):**
```python
    if s.base_hit_candle_trail_enabled and monitor._get_intraday_candles:
        activation_cents = s.base_hit_trail_activation_cents
        
        # Step 1: Check if trail should activate
        if position.candle_trail_stop is None and profit_cents >= activation_cents:
```
**Approach:** Replace line 708 with proportional computation:
```python
        # Price-proportional trail activation: max(fixed_floor, pct% of entry price in cents)
        pct = getattr(s, 'trail_activation_pct', 3.0)
        if pct > 0:
            proportional_cents = Decimal(str(float(position.entry_price) * pct))
            activation_cents = max(s.base_hit_trail_activation_cents, proportional_cents)
        else:
            activation_cents = s.base_hit_trail_activation_cents
```
**Why `getattr`:** Defensive — protects against older settings objects that don't have the new field (e.g. loaded from pre-existing JSON without the key).

---

### Change Point #4: Compute proportional flat fallback

**File:** [warrior_monitor_exit.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py)  
**Location:** `_check_base_hit_target()`, line 824  
**Current Code (lines 823-830):**
```python
    # ---- FALLBACK: Flat +18¢ target (when trail disabled or no bars) ----
    target_price = position.entry_price + s.base_hit_profit_cents / 100
    
    logger.info(
        f"[Warrior] {position.symbol}: BASE HIT check (flat fallback) - "
        f"current=${current_price:.2f}, target=${target_price:.2f}, "
        f"entry=${position.entry_price:.2f}, +{s.base_hit_profit_cents}¢"
    )
```
**Approach:** Replace line 824 with proportional computation:
```python
    # Price-proportional flat fallback: max(fixed_floor, pct% of entry price)
    profit_pct = getattr(s, 'base_hit_profit_pct', 3.5)
    if profit_pct > 0:
        proportional_profit_cents = Decimal(str(float(position.entry_price) * profit_pct))
        effective_profit_cents = max(s.base_hit_profit_cents, proportional_profit_cents)
    else:
        effective_profit_cents = s.base_hit_profit_cents
    target_price = position.entry_price + effective_profit_cents / 100
```
**Also update the log message** to show `effective_profit_cents` instead of `s.base_hit_profit_cents`.

---

### Change Point #5: Persistence — `get_monitor_settings_dict`

**File:** [warrior_monitor_settings.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/db/warrior_monitor_settings.py)  
**Location:** `get_monitor_settings_dict()`, lines 100-121  
**Current Code (line 117-118, last entries before closing brace):**
```python
        "move_stop_to_breakeven_after_scale": monitor_settings_obj.move_stop_to_breakeven_after_scale,
        "enable_partial_then_ride": monitor_settings_obj.enable_partial_then_ride,
```
**Approach:** Add after line 118:
```python
        "trail_activation_pct": monitor_settings_obj.trail_activation_pct,
        "base_hit_profit_pct": monitor_settings_obj.base_hit_profit_pct,
```

---

### Change Point #6: Persistence — `apply_monitor_settings`

**File:** [warrior_monitor_settings.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/db/warrior_monitor_settings.py)  
**Location:** `apply_monitor_settings()`, lines 64-97  
**Current Code (lines 94-96, last entries before log line):**
```python
    if "enable_partial_then_ride" in settings:
        monitor_settings_obj.enable_partial_then_ride = settings["enable_partial_then_ride"]
    
    print(f"[Warrior Monitor Settings] Applied: enable_scaling={monitor_settings_obj.enable_scaling}")
```
**Approach:** Add before the print statement:
```python
    if "trail_activation_pct" in settings:
        monitor_settings_obj.trail_activation_pct = settings["trail_activation_pct"]
    if "base_hit_profit_pct" in settings:
        monitor_settings_obj.base_hit_profit_pct = settings["base_hit_profit_pct"]
```

---

## E. Wiring Checklist

```
- [ ] Add `trail_activation_pct: float = 3.0` to WarriorMonitorSettings (warrior_types.py)
- [ ] Add `base_hit_profit_pct: float = 3.5` to WarriorMonitorSettings (warrior_types.py)
- [ ] Replace `activation_cents = s.base_hit_trail_activation_cents` with proportional calc (warrior_monitor_exit.py:708)
- [ ] Replace `target_price = position.entry_price + s.base_hit_profit_cents / 100` with proportional calc (warrior_monitor_exit.py:824)
- [ ] Update log message at line 827 to show effective_profit_cents
- [ ] Add both new fields to get_monitor_settings_dict() (warrior_monitor_settings.py)
- [ ] Add both new fields to apply_monitor_settings() (warrior_monitor_settings.py)
- [ ] Verify no other references to base_hit_trail_activation_cents need updating (confirmed: only line 708)
```

---

## F. Risk Assessment

### Low Risk
- **Backward compatibility preserved:** `max(fixed_floor, proportional)` means behavior is identical for stocks ≤$5.00. The floor is never lowered.
- **A/B testable:** Setting `trail_activation_pct = 0.0` reverts to fixed behavior.
- **No new dependencies:** Pure arithmetic, no new imports or services.

### Medium Risk
- **BNAI ($33.81) and EVMN ($36.00) get ~$1 activation thresholds.** This means the trail won't start until 3% above entry, which is correct behavior — but if the stock only moves 2.5% and reverses, the flat fallback at 3.5% would also not trigger. In that scenario, the position exits via candle-under-candle, topping tail, or stop — all of which still function. This is *desired* behavior: don't cap upside on a $34 stock at +15¢.
- **Existing settings JSON files** don't have the new fields. The `getattr` fallback in the exit code and the `if "key" in settings` guard in persistence handle this gracefully — no migration needed.

### What to Test After Implementation
1. **Batch test all 38 cases** — compare P&L before and after
2. **Spot-check:** GWAV ($3) should still activate at 15¢ (unchanged)
3. **Spot-check:** NPT ($10) should now activate at 30¢ instead of 15¢
4. **Spot-check:** BNAI ($33.81) should now activate at 101¢ instead of 15¢
5. **Verify flat fallback:** Disable candle trail, confirm proportional fallback works
6. **Verify `trail_activation_pct = 0.0`** reverts to fixed behavior (A/B toggle)

---

## G. Files NOT Changed (Verified)

| File | Why Not |
|------|---------|
| `warrior_monitor.py` | Delegates to `warrior_monitor_exit.py`, no trail logic |
| `warrior_engine_entry.py` | Entry logic, no exit trail references |
| `warrior_entry_patterns.py` | Pattern detection, no exit logic |
| `warrior_monitor_scale.py` | Scaling logic, independent of trail |
| Tests (`test_warrior_monitor.py`) | No existing candle trail tests to update |
