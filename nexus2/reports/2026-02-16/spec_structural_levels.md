# Technical Spec: Fix 3 — Structural Profit Levels

**Date:** 2026-02-16  
**Author:** Backend Planner  
**For:** Backend Specialist  
**Status:** DRAFT — Pending review

---

## Summary

Replace the flat +18¢ fallback profit target with **structural price levels** (whole dollars, half-dollars) that align with how Ross Cameron actually takes profits. Ross frequently exits at round numbers like $5.00, $5.50, $6.00 — these act as psychological resistance/support where sellers congregate.

### Current State
- **Fix 1 (partial-then-ride): ENABLED** — +97% P&L improvement
- **Fix 2 (proportional trail): REJECTED** — -10% P&L, disabled
- Fix 3 will be tested **with Fix 1 enabled**

---

## A. Structural Level Analysis Across Test Cases

Entry prices extracted from `warrior_setups.yaml` with projected structural level targets at **$0.50 increments** (whole + half dollars):

| Test Case | Entry $ | Next $0.50 Level | Distance (¢) | Skip? (< 10¢) | Final Target | Current Flat +18¢ |
|-----------|---------|-------------------|---------------|----------------|-------------|-------------------|
| CMCT $4.65 | 4.65 | $5.00 | 35¢ | No | **$5.00** | $4.83 |
| OPTX $3.50 | 3.50 | $3.50 | 0¢ | **Yes** → $4.00 | **$4.00** | $3.68 |
| ACON $8.30 | 8.30 | $8.50 | 20¢ | No | **$8.50** | $8.48 |
| FLYX $6.20 | 6.20 | $6.50 | 30¢ | No | **$6.50** | $6.38 |
| LCFY $7.50 | 7.50 | $7.50 | 0¢ | **Yes** → $8.00 | **$8.00** | $7.68 |
| PAVM $12.31 | 12.31 | $12.50 | 19¢ | No | **$12.50** | $12.49 |
| ROLR $15.00 | 15.00 | $15.00 | 0¢ | **Yes** → $15.50 | **$15.50** | $15.18 |
| BNKK $5.00 | 5.00 | $5.00 | 0¢ | **Yes** → $5.50 | **$5.50** | $5.18 |
| TNMG $5.00 | 5.00 | $5.00 | 0¢ | **Yes** → $5.50 | **$5.50** | $5.18 |
| GWAV $3.00 | 3.00 | $3.00 | 0¢ | **Yes** → $3.50 | **$3.50** | $3.18 |
| VERO $3.00 | 3.00 | $3.00 | 0¢ | **Yes** → $3.50 | **$3.50** | $3.18 |
| GRI $5.97 | 5.97 | $6.00 | 3¢ | **Yes** → $6.50 | **$6.50** | $6.15 |
| LRHC $5.30 | 5.30 | $5.50 | 20¢ | No | **$5.50** | $5.48 |
| HIND $5.00 | 5.00 | $5.00 | 0¢ | **Yes** → $5.50 | **$5.50** | $5.18 |
| DCX $4.60 | 4.60 | $5.00 | 40¢ | No | **$5.00** | $4.78 |
| NPT $10.00 | 10.00 | $10.00 | 0¢ | **Yes** → $10.50 | **$10.50** | $10.18 |
| BNAI $33.81 | 33.81 | $34.00 | 19¢ | No | **$34.00** | $33.99 |
| RNAZ $12.00 | 12.00 | $12.00 | 0¢ | **Yes** → $12.50 | **$12.50** | $12.18 |
| RVSN $5.50 | 5.50 | $5.50 | 0¢ | **Yes** → $6.00 | **$6.00** | $5.68 |
| FLYE $6.32 | 6.32 | $6.50 | 18¢ | No | **$6.50** | $6.50 |
| RDIB $15.00 | 15.00 | $15.00 | 0¢ | **Yes** → $15.50 | **$15.50** | $15.18 |
| MNTS $8.00 | 8.00 | $8.00 | 0¢ | **Yes** → $8.50 | **$8.50** | $8.18 |
| SXTC $4.50 | 4.50 | $4.50 | 0¢ | **Yes** → $5.00 | **$5.00** | $4.68 |
| UOKA $4.00 | 4.00 | $4.00 | 0¢ | **Yes** → $4.50 | **$4.50** | $4.18 |
| EVMN $36.00 | 36.00 | $36.00 | 0¢ | **Yes** → $36.50 | **$36.50** | $36.18 |
| VELO $16.00 | 16.00 | $16.00 | 0¢ | **Yes** → $16.50 | **$16.50** | $16.18 |
| PRFX $4.15 | 4.15 | $4.50 | 35¢ | No | **$4.50** | $4.33 |
| PMI $2.50 | 2.50 | $2.50 | 0¢ | **Yes** → $3.00 | **$3.00** | $2.68 |
| ONCO $2.40 | 2.40 | $2.50 | 10¢ | No | **$2.50** | $2.58 |
| MLEC $7.90 | 7.90 | $8.00 | 10¢ | No | **$8.00** | $8.08 |

### Key Observations

1. **Many entries ARE on structural levels** (exactly $5.00, $3.00, etc.) — the "skip to next" rule is essential
2. **$0.50 increments provide meaningful targets** — average distance is 35-50¢, well above the current flat 18¢
3. **Minimum distance threshold of 10¢** catches close-to-level entries like GRI $5.97 → $6.00 (3¢) — too close
4. **Higher-priced stocks benefit most** — BNAI $33.81 → $34.00 (19¢) is actually closer than the current 18¢ fallback, which is fine because it's a structural level

### Risk: Structural Levels Are Further Away

In 22/29 cases, the structural target is **further** than the flat +18¢ target. This means:
- Trades must run further before the base_hit exit fires
- With Fix 1 enabled, the partial exit happens later but at a more meaningful level
- The candle trail (primary exit) is unaffected — structural levels ONLY replace the flat fallback

> [!IMPORTANT]
> The structural level **only affects the flat fallback path** (lines 829-911). The candle trail (lines 707-827) is the primary exit mechanism and remains unchanged. Since the candle trail activates at +15¢ and trails candle lows, it handles most exits. The fallback only fires when bars are unavailable or the trail isn't enabled.

---

## B. Design Decisions

### B1. Level Granularity: $0.50 Increments (Whole + Half Dollars)

**Recommended: Option A — $0.50 increments**

Ross most commonly references whole and half-dollar levels. Quarter-dollar levels ($0.25) are too granular for base_hit targets.

### B2. Minimum Distance: 10¢

If the next structural level is less than 10¢ away, skip to the one after. This prevents trivially close targets like entry $4.97 → $5.00 (3¢).

### B3. Scope: Flat Fallback Only

The structural level replaces **only the flat fallback target calculation** (lines 829-837). It does NOT affect:
- Trail activation threshold (stays at +15¢ / proportional)
- Candle trail logic (unchanged)
- Home run mode (unchanged)

### B4. Config Toggle for A/B Testing

Two new config fields:
- `enable_structural_levels: bool = True` — A/B toggle
- `structural_level_increment: float = 0.50` — Level spacing ($0.50 = whole + half, $0.25 = quarters, $1.00 = whole only)
- `structural_level_min_distance_cents: int = 10` — Minimum distance to next level

### B5. Interaction with Fix 1 (Partial-Then-Ride)

No special handling needed. Fix 1's partial-then-ride logic reads `target_price` (line 845). The structural level simply provides a better `target_price`. The remainder still switches to `home_run` mode as before.

---

## C. Change Surface Enumeration

| # | File | Change | Location | Template |
|---|------|--------|----------|----------|
| 1 | `warrior_types.py` | Add 3 config fields to `WarriorMonitorSettings` | Lines 121-130 (base_hit section) | Existing `enable_partial_then_ride` pattern |
| 2 | `warrior_monitor_exit.py` | Add `_compute_structural_target` helper function | New function, insert before `_check_base_hit_target` (line ~685) | Pure function, no template needed |
| 3 | `warrior_monitor_exit.py` | Replace flat fallback target calculation | Lines 829-837 | Replace fixed formula with structural level call |
| 4 | `warrior_monitor_settings.py` | Add fields to `get_monitor_settings_dict` | Lines 104-127 | Existing pattern at lines 124-126 |
| 5 | `warrior_monitor_settings.py` | Add fields to `apply_monitor_settings` | Lines 64-101 | Existing pattern at lines 94-99 |

---

## D. Detailed Change Specifications

### Change #1: Config Fields in `WarriorMonitorSettings`

**File:** `nexus2/domain/automation/warrior_types.py`  
**Location:** Lines 121-130 (Base Hit Mode Settings section)  
**Verified with:** `view_file` lines 58-141

**Current Code (lines 121-130):**
```python
    # Base Hit Mode Settings
    base_hit_profit_cents: Decimal = Decimal("18")  # Take profit at +18¢ (Ross's typical)
    base_hit_profit_pct: float = 0.0  # Fix 2: REJECTED — net negative alone and combined with Fix 1
    base_hit_stop_cents: Decimal = Decimal("15")  # Mental stop at -15¢
    
    # Base Hit Candle Trail (Phase A — Ross Cameron candle-low trailing)
    base_hit_candle_trail_enabled: bool = True  # Enable candle-low trailing for base_hit
    base_hit_trail_activation_cents: Decimal = Decimal("15")  # Start trailing after +15¢ (was 10¢)
    trail_activation_pct: float = 0.0  # Fix 2: REJECTED — net negative alone and combined with Fix 1
    candle_trail_lookback_bars: int = 2  # Trail = lowest low of last N completed candles (was 1)
```

**Approach:** Add 3 new fields after `base_hit_stop_cents` (line 124):
```python
    # Structural Profit Levels (Fix 3: A/B testable)
    # When enabled, replaces flat +18¢ fallback with next structural price level
    # Ross Cameron exits at whole/half dollar levels ($5, $5.50, $6, etc.)
    enable_structural_levels: bool = True  # Fix 3: Use structural levels for fallback target
    structural_level_increment: float = 0.50  # $0.50 = whole + half dollars
    structural_level_min_distance_cents: int = 10  # Skip levels closer than 10¢
```

---

### Change #2: New `_compute_structural_target` Helper Function

**File:** `nexus2/domain/automation/warrior_monitor_exit.py`  
**Location:** Insert as new function BEFORE `_check_base_hit_target` (before line 686)  
**Template:** Pure function, no external dependencies

**Approach:** Create a function that computes the next structural price level above `entry_price`:
```python
def _compute_structural_target(
    entry_price: Decimal,
    increment: float = 0.50,
    min_distance_cents: int = 10,
) -> Decimal:
    """
    Compute the next structural price level above entry_price.
    
    Ross Cameron exits at structural levels: $5.00, $5.50, $6.00, etc.
    If the nearest level is too close (< min_distance_cents), skip to the next one.
    
    Args:
        entry_price: Position entry price
        increment: Level spacing (0.50 = whole + half dollars, 1.00 = whole only)
        min_distance_cents: Minimum distance in cents to the target level
    
    Returns:
        The next valid structural price level above entry_price.
    """
    inc = Decimal(str(increment))
    min_dist = Decimal(str(min_distance_cents)) / 100  # Convert cents to dollars
    
    # Compute the next level above entry_price
    # Example: entry $4.65, inc $0.50 → ceil(4.65 / 0.50) * 0.50 = ceil(9.3) * 0.50 = 10 * 0.50 = $5.00
    import math
    next_level = Decimal(str(math.ceil(float(entry_price) / increment) * increment))
    
    # If entry is exactly on a level (e.g., $5.00), next_level == entry, so move up
    if next_level <= entry_price:
        next_level += inc
    
    # If too close, skip to the next level
    if (next_level - entry_price) < min_dist:
        next_level += inc
    
    return next_level
```

**This is a pure function** — easy to unit test independently.

---

### Change #3: Replace Flat Fallback Target Calculation

**File:** `nexus2/domain/automation/warrior_monitor_exit.py`  
**Location:** Lines 829-843 (FALLBACK section inside `_check_base_hit_target`)  
**Verified with:** `view_file` lines 829-843

**Current Code (lines 829-843):**
```python
    # ---- FALLBACK: Flat target (when trail disabled or no bars) ----
    # Price-proportional flat fallback: max(fixed_floor, pct% of entry price)
    profit_pct = getattr(s, 'base_hit_profit_pct', 3.5)
    if profit_pct > 0:
        proportional_profit_cents = Decimal(str(float(position.entry_price) * profit_pct))
        effective_profit_cents = max(s.base_hit_profit_cents, proportional_profit_cents)
    else:
        effective_profit_cents = s.base_hit_profit_cents
    target_price = position.entry_price + effective_profit_cents / 100
    
    logger.info(
        f"[Warrior] {position.symbol}: BASE HIT check (flat fallback) - "
        f"current=${current_price:.2f}, target=${target_price:.2f}, "
        f"entry=${position.entry_price:.2f}, +{float(effective_profit_cents):.0f}¢"
    )
```

**Approach:** Wrap the target calculation in a structural-level check:
```python
    # ---- FALLBACK: Flat target (when trail disabled or no bars) ----
    if getattr(s, 'enable_structural_levels', False):
        # Fix 3: Structural profit levels — target next whole/half dollar
        target_price = _compute_structural_target(
            entry_price=position.entry_price,
            increment=getattr(s, 'structural_level_increment', 0.50),
            min_distance_cents=getattr(s, 'structural_level_min_distance_cents', 10),
        )
        effective_profit_cents = (target_price - position.entry_price) * 100
        logger.info(
            f"[Warrior] {position.symbol}: BASE HIT check (structural level) - "
            f"current=${current_price:.2f}, target=${target_price:.2f}, "
            f"entry=${position.entry_price:.2f}, +{float(effective_profit_cents):.0f}¢ "
            f"(next ${getattr(s, 'structural_level_increment', 0.50)} level)"
        )
    else:
        # Original flat fallback: price-proportional or fixed cents
        profit_pct = getattr(s, 'base_hit_profit_pct', 3.5)
        if profit_pct > 0:
            proportional_profit_cents = Decimal(str(float(position.entry_price) * profit_pct))
            effective_profit_cents = max(s.base_hit_profit_cents, proportional_profit_cents)
        else:
            effective_profit_cents = s.base_hit_profit_cents
        target_price = position.entry_price + effective_profit_cents / 100
        
        logger.info(
            f"[Warrior] {position.symbol}: BASE HIT check (flat fallback) - "
            f"current=${current_price:.2f}, target=${target_price:.2f}, "
            f"entry=${position.entry_price:.2f}, +{float(effective_profit_cents):.0f}¢"
        )
```

**Note:** The existing log messages in lines 858-861 and 898-900 reference `s.base_hit_profit_cents` in the trigger description. These should also be updated to say "structural level" when enabled. Specifically:

- **Line 860:** `f"(+{s.base_hit_profit_cents}¢ target)"` → should use `f"(${target_price} structural)" if structural else f"(+{s.base_hit_profit_cents}¢ target)"`
- **Line 893:** `f"Base hit +{s.base_hit_profit_cents}¢ flat target → partial exit..."` → same  
- **Line 910:** `f"Base hit +{s.base_hit_profit_cents}¢ flat target hit (candle trail unavailable)"` → same

**Approach for trigger descriptions:** Add a variable before the exit blocks:
```python
    if getattr(s, 'enable_structural_levels', False):
        target_desc = f"${target_price:.2f} structural level"
    else:
        target_desc = f"+{s.base_hit_profit_cents}¢ flat target"
```

Then use `target_desc` in all three trigger description strings (lines 860, 893, 910).

---

### Change #4: Persistence — `get_monitor_settings_dict`

**File:** `nexus2/db/warrior_monitor_settings.py`  
**Location:** Lines 104-127 (`get_monitor_settings_dict` function)  
**Verified with:** `view_file` lines 104-127

**Current Code (last 3 entries, lines 124-127):**
```python
        "enable_partial_then_ride": monitor_settings_obj.enable_partial_then_ride,
        "trail_activation_pct": monitor_settings_obj.trail_activation_pct,
        "base_hit_profit_pct": monitor_settings_obj.base_hit_profit_pct,
    }
```

**Approach:** Add 3 new entries before the closing `}`:
```python
        "enable_partial_then_ride": monitor_settings_obj.enable_partial_then_ride,
        "trail_activation_pct": monitor_settings_obj.trail_activation_pct,
        "base_hit_profit_pct": monitor_settings_obj.base_hit_profit_pct,
        # Fix 3: Structural profit levels
        "enable_structural_levels": monitor_settings_obj.enable_structural_levels,
        "structural_level_increment": monitor_settings_obj.structural_level_increment,
        "structural_level_min_distance_cents": monitor_settings_obj.structural_level_min_distance_cents,
    }
```

---

### Change #5: Persistence — `apply_monitor_settings`

**File:** `nexus2/db/warrior_monitor_settings.py`  
**Location:** Lines 64-101 (`apply_monitor_settings` function)  
**Verified with:** `view_file` lines 94-101

**Current Code (last entries, lines 96-101):**
```python
    if "trail_activation_pct" in settings:
        monitor_settings_obj.trail_activation_pct = settings["trail_activation_pct"]
    if "base_hit_profit_pct" in settings:
        monitor_settings_obj.base_hit_profit_pct = settings["base_hit_profit_pct"]
    
    print(f"[Warrior Monitor Settings] Applied: enable_scaling={monitor_settings_obj.enable_scaling}")
```

**Approach:** Add 3 new entries before the print statement:
```python
    if "trail_activation_pct" in settings:
        monitor_settings_obj.trail_activation_pct = settings["trail_activation_pct"]
    if "base_hit_profit_pct" in settings:
        monitor_settings_obj.base_hit_profit_pct = settings["base_hit_profit_pct"]
    # Fix 3: Structural profit levels
    if "enable_structural_levels" in settings:
        monitor_settings_obj.enable_structural_levels = settings["enable_structural_levels"]
    if "structural_level_increment" in settings:
        monitor_settings_obj.structural_level_increment = settings["structural_level_increment"]
    if "structural_level_min_distance_cents" in settings:
        monitor_settings_obj.structural_level_min_distance_cents = settings["structural_level_min_distance_cents"]
    
    print(f"[Warrior Monitor Settings] Applied: enable_scaling={monitor_settings_obj.enable_scaling}")
```

---

## E. Wiring Checklist

- [ ] Config field `enable_structural_levels: bool = True` added to `WarriorMonitorSettings` (`warrior_types.py`)
- [ ] Config field `structural_level_increment: float = 0.50` added to `WarriorMonitorSettings` (`warrior_types.py`)
- [ ] Config field `structural_level_min_distance_cents: int = 10` added to `WarriorMonitorSettings` (`warrior_types.py`)
- [ ] Helper function `_compute_structural_target()` created in `warrior_monitor_exit.py`
- [ ] Flat fallback target replaced with structural level when `enable_structural_levels=True` (`warrior_monitor_exit.py` lines 829-837)
- [ ] Trigger description strings updated to reflect structural vs flat (`warrior_monitor_exit.py` lines 860, 893, 910)
- [ ] `get_monitor_settings_dict` updated with 3 new fields (`warrior_monitor_settings.py`)
- [ ] `apply_monitor_settings` updated with 3 new fields (`warrior_monitor_settings.py`)
- [ ] A/B test: run batch with `enable_structural_levels=True` vs `False` and compare P&L

---

## F. Risk Assessment

### What Could Go Wrong

1. **Larger targets = missed exits** — If the structural level is significantly further than 18¢ (e.g., 50¢), the fallback may never fire because the candle trail handles it first. This is actually FINE since the candle trail is the intended primary mechanism.

2. **Interaction with Fix 2 remnants** — Fix 2 (`base_hit_profit_pct`) is set to `0.0` (disabled). The structural level logic should take precedence when enabled, completely bypassing the Fix 2 proportional path. The `else` branch preserves the original path for when structural levels are disabled.

3. **Edge case: Very low-priced stocks** — Entry at $0.80: next level is $1.00 (20¢ away). This is reasonable. Entry at $1.00: skip → $1.50 (50¢). This is aggressive for a $1 stock but the candle trail would exit first anyway.

4. **math.ceil precision** — Using `float` division in `math.ceil` could have floating-point edge cases. For $4.50 / 0.50 = 9.0 → ceil = 9 → 9 * 0.50 = $4.50. Since $4.50 == entry, we correctly bump to $5.00. Test this edge case.

### What Existing Behavior Might Break

- **None.** When `enable_structural_levels=False`, behavior is identical to current (the else branch is exact copy of current code).
- **Fallback-only scope**: The candle trail (primary mechanism, lines 707-827) is completely untouched.

### What to Test After Implementation

1. **Unit test `_compute_structural_target`** with edge cases:
   - Entry exactly on a level ($5.00 → $5.50)
   - Entry just below a level ($4.97 → $5.00 is 3¢ < 10¢ → $5.50)
   - Entry mid-range ($4.65 → $5.00 is 35¢ ≥ 10¢ → $5.00)
   - Entry just above a level ($5.03 → $5.50 is 47¢ → $5.50)
   - Low-priced stock ($1.20 → $1.50 is 30¢ → $1.50)
   - High-priced stock ($33.81 → $34.00 is 19¢ → $34.00)

2. **Batch test with structural levels enabled** vs current baseline
   - Key metric: total P&L, win rate, average win size
   - Watch for: cases where structural level is so far the trade reverses before hitting it (the candle trail should prevent this)

3. **Verify persistence round-trip**:
   ```powershell
   python -c "from nexus2.db.warrior_monitor_settings import get_monitor_settings_dict; from nexus2.domain.automation.warrior_types import WarriorMonitorSettings; d = get_monitor_settings_dict(WarriorMonitorSettings()); print('enable_structural_levels' in str(d), 'structural_level_increment' in str(d), 'structural_level_min_distance_cents' in str(d))"
   ```
   Expected: `True True True`
