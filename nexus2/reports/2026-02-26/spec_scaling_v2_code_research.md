# Technical Spec: Scaling v2 — Code Research (Phase 1)

**Date:** 2026-02-26  
**Agent:** Backend Planner  
**Scope:** READ ONLY — map existing code, identify change points, write spec  
**Source:** `plan_scaling_v2.md`, `research_ross_add_methodology.md`

---

## A. Existing Pattern Analysis

### Current Scaling Architecture

| Component | Function | File | Lines | Purpose |
|-----------|----------|------|-------|---------|
| Pullback Scale Check | `check_scale_opportunity()` | `warrior_monitor_scale.py` | 31–156 | Detects pullback-based scale opportunities |
| Momentum Add Check | `check_momentum_add()` | `warrior_monitor_scale.py` | 164–254 | Detects price-level-based momentum adds |
| Scale Execution | `execute_scale_in()` | `warrior_monitor_scale.py` | 262–467 | Submits order, updates position state, PSM |
| Monitor Tick Loop | `_check_all_positions()` | `warrior_monitor.py` | 539–609 | Calls scaling checks when no exit signal |
| Structural Level Calc | `_compute_structural_target()` | `warrior_monitor_exit.py` | 695–730 | Computes next $X.00/$X.50 level above price |
| Settings | `WarriorMonitorSettings` | `warrior_types.py` | 99–122 | All scaling config fields |
| Position State | `WarriorPosition` | `warrior_types.py` | 210–216 | Scale tracking fields |
| MACD Gate (entry only) | `_check_macd_gate()` | `warrior_entry_guards.py` | 174–240 | Blocks entries on negative MACD |
| Technical Service | `get_technical_service()` | `indicators/technical_service.py` | 252+ | Provides MACD snapshot from candle data |

### The "Accidental" Scaling Behavior

**Finding:** The current pullback zone check at line 133 of `warrior_monitor_scale.py` always evaluates to `True`.

**File:** `warrior_monitor_scale.py`:131-133  
**Code:**
```python
# Original (broken) logic: always True when allow_scale_below_entry=True
is_pullback_zone = current_price <= position.entry_price or s.allow_scale_below_entry
```

**Why it's always True:** `allow_scale_below_entry` defaults to `True` in settings (line 111 of `warrior_types.py`), so the `or` short-circuits — price doesn't matter.

**Net effect:** Combined with `last_scale_attempt=None` initially (cooldown guard skipped on first check), this produces **exactly one scale per trade** on the first eligible bar, effectively making every position 1.5x size.

**Documentation:** Lines 100-106 of `warrior_types.py` contain a detailed comment explaining this.

### The "Improved" Scaling (enable_improved_scaling=True)

When `enable_improved_scaling=True`, lines 115-130 implement a proper pullback zone:
```python
# Pullback zone = within 50% of entry-to-support range
pullback_threshold = entry_price - (support_distance * 0.5)
is_pullback_zone = current_price <= pullback_threshold and current_price > support
```

**Why it's disabled:** This is too strict — barely triggers. The plan previously noted this produces results "barely better than no scaling."

### Momentum Add System (Currently Disabled)

`check_momentum_add()` (lines 164-254) is a separate, fully-wired system:
- Enabled via `enable_momentum_adds: bool = False` (line 119)
- Triggers when price moves `momentum_add_interval` ($1.00 default) above last add
- Uses separate `momentum_add_count` / `max_momentum_adds` counters
- Shares the same `execute_scale_in()` execution path

This is the **closest template** for level-break scaling but uses fixed-dollar intervals instead of structural levels.

---

## B. Change Surface Enumeration

| # | File | Change | Location | Template |
|---|------|--------|----------|----------|
| 1 | `warrior_monitor_scale.py` | Replace `check_scale_opportunity()` with level-break logic | Lines 31–156 | `check_momentum_add()` pattern |
| 2 | `warrior_monitor_scale.py` | Add MACD gate to both scale checks | New code in scale checks | `_check_macd_gate()` from `warrior_entry_guards.py` |
| 3 | `warrior_monitor_scale.py` | Add structural level detection helper | New function | `_compute_structural_target()` from `warrior_monitor_exit.py` |
| 4 | `warrior_types.py` | Add new scaling v2 settings fields | Lines 99–122 | Existing momentum add fields pattern |
| 5 | `warrior_types.py` | Add level tracking fields to `WarriorPosition` | Lines 210–216 | `last_momentum_add_price` pattern |
| 6 | `warrior_monitor_exit.py` | Add structural-level profit-taking trigger | After line 687 or modify `_check_base_hit_target` | `_check_profit_target()` pattern |
| 7 | `warrior_monitor.py` | Wire new scaling v2 check in monitor tick loop | Lines 577–607 | Existing scaling wiring |

---

## C. Detailed Change Specifications

### Change Point #1: Replace Pullback Scale with Level-Break Logic

**What:** Replace the broken `check_scale_opportunity()` with Ross Cameron level-break scaling.

**File:** `warrior_monitor_scale.py`  
**Location:** `check_scale_opportunity()`, lines 31–156  
**Current Code (key section, lines 112-156):**
```python
# Check if this is a pullback opportunity
if s.enable_improved_scaling:
    # Pullback zone = within 50% of entry-to-support range
    support_distance = position.entry_price - support
    if support_distance > 0:
        pullback_threshold = position.entry_price - (support_distance * Decimal("0.5"))
        is_pullback_zone = current_price <= pullback_threshold and current_price > support
    else:
        is_pullback_zone = False
else:
    # Original (broken) logic: always True when allow_scale_below_entry=True
    is_pullback_zone = current_price <= position.entry_price or s.allow_scale_below_entry

if not is_pullback_zone:
    return None

# Calculate scale size
add_shares = int(position.original_shares * s.scale_size_pct / 100)
```

**Approach:** Replace the entire pullback zone logic with structural level-break detection:
1. Compute the next structural level above the last add price (or entry price if no adds yet)
2. Check if `current_price >= next_level` (level broken)
3. Optionally verify level holds: price stays above for N seconds/ticks (future enhancement)
4. Use `_compute_structural_target()` (from exit module) or a local copy
5. Track `last_level_break_price` on the position for progressive level tracking

**Template:** `check_momentum_add()` (same file, lines 164-254) — follows the same pattern of reference price tracking + interval checking, but uses structural levels instead of fixed dollar intervals.

**Key difference from momentum adds:** Level-break scaling fires on **specific structural levels** ($X.00, $X.50) rather than every $1.00 move. The `_compute_structural_target()` function already solves this.

---

### Change Point #2: Add MACD Gate to Scaling

**What:** Block all scale-ins when MACD is negative (Ross: "MACD is negative. I don't think this is going to happen.").

**File:** `warrior_monitor_scale.py`  
**Location:** Early in both `check_scale_opportunity()` and `check_momentum_add()`  
**Current Code:** No MACD check exists in scaling.

**Approach:** Add a MACD check similar to `_check_macd_gate()` in `warrior_entry_guards.py`:
1. Fetch candles via `monitor._get_intraday_candles(symbol, "1min", limit=50)`
2. Call `get_technical_service().get_snapshot(symbol, candle_dicts, current_price)`
3. Check `snapshot.macd_histogram >= tolerance` (tolerance from settings, e.g., `-0.02`)
4. If MACD is too negative, return `None` (block the add)

**Template:** `_check_macd_gate()` from `warrior_entry_guards.py` (lines 174-240), adapted to scaling context.

**Important difference:** Entry guards access bars via `engine._get_intraday_bars`, but scaling uses `monitor._get_intraday_candles`. The monitor already has this callback wired (line 66 of `warrior_monitor.py`).

**Performance consideration:** This adds a candle fetch + indicator calculation per scale check tick. Should only fire when other conditions pass (price at level). Consider making MACD gate the LAST check, not first, to avoid unnecessary API calls.

---

### Change Point #3: Structural Level Detection Helper

**What:** Create a helper that computes structural levels relative to a reference price.

**File:** `warrior_monitor_scale.py` (new function)  
**Template:** `_compute_structural_target()` from `warrior_monitor_exit.py` (lines 695-730):

```python
def _compute_structural_target(
    entry_price: Decimal,
    increment: float = 0.50,
    min_distance_cents: int = 10,
) -> Decimal:
    import math
    inc = Decimal(str(increment))
    min_dist = Decimal(str(min_distance_cents)) / 100
    next_level = Decimal(str(math.ceil(float(entry_price) / increment) * increment))
    if next_level <= entry_price:
        next_level += inc
    if (next_level - entry_price) < min_dist:
        next_level += inc
    return next_level
```

**Approach:** Either:
- **Option A:** Import and reuse from `warrior_monitor_exit.py` (avoid duplication)
- **Option B:** Copy to `warrior_monitor_scale.py` (avoid circular dependency risk)

**Recommendation:** Option A — the function is a pure utility with no dependencies. Import as:
```python
from nexus2.domain.automation.warrior_monitor_exit import _compute_structural_target
```
No circular dependency risk since `warrior_monitor_exit.py` doesn't import `warrior_monitor_scale.py`.

---

### Change Point #4: New Scaling v2 Settings

**What:** Add configuration fields to `WarriorMonitorSettings` for level-break scaling.

**File:** `warrior_types.py`  
**Location:** Lines 99-122 (scaling section)

**Current scaling fields:**
```python
enable_scaling: bool = True
max_scale_count: int = 4
scale_size_pct: int = 50
min_rvol_for_scale: float = 2.0
allow_scale_below_entry: bool = True
move_stop_to_breakeven_after_scale: bool = False
enable_improved_scaling: bool = False
```

**New/modified fields to add:**
```python
# Scaling v2: Ross Cameron Level-Break Methodology
enable_level_break_scaling: bool = True  # Replace accidental scaling with level-break
level_break_increment: float = 0.50      # $0.50 = whole + half dollars
level_break_min_distance_cents: int = 10  # Skip levels closer than 10¢ from last add
level_break_macd_gate: bool = True        # Block adds when MACD negative
level_break_macd_tolerance: float = -0.02 # Histogram threshold (matches entry gate)
```

**Approach:** Add alongside existing fields. Keep `enable_scaling` as the master switch, and use `enable_level_break_scaling` to choose between old (accidental) and new (level-break) behavior. This enables A/B testing.

**Fields to potentially deprecate (not remove yet):**
- `allow_scale_below_entry` — no longer relevant with level-break
- `enable_improved_scaling` — superseded by level-break
- `min_rvol_for_scale` — unused in current code (never checked despite documentation)

---

### Change Point #5: Position Level Tracking Fields

**What:** Add fields to `WarriorPosition` to track level-break state.

**File:** `warrior_types.py`  
**Location:** Lines 210-216 (scaling tracking section)

**Current fields:**
```python
scale_count: int = 0
original_shares: int = 0
last_scale_attempt: Optional[datetime] = None
last_momentum_add_price: Optional[Decimal] = None
momentum_add_count: int = 0
recovered_at: Optional[datetime] = None
```

**New field to add:**
```python
last_level_break_price: Optional[Decimal] = None  # Track the level price of last scale-in
```

**Purpose:** `_compute_structural_target` uses this as the reference price to find the NEXT level. Without it, the bot would re-trigger on the same level repeatedly.

---

### Change Point #6: Structural Level Profit-Taking

**What:** Take partial profit at structural levels ($X.00, $X.50).

**File:** `warrior_monitor_exit.py`  
**Location:** This is already partially implemented via `enable_structural_levels` (lines 915-928) in `_check_base_hit_target()`:

```python
if getattr(s, 'enable_structural_levels', False):
    target_price = _compute_structural_target(
        entry_price=position.entry_price,
        increment=getattr(s, 'structural_level_increment', 0.50),
        min_distance_cents=getattr(s, 'structural_level_min_distance_cents', 10),
    )
```

**However:** This is currently the FALLBACK path (only fires when candle trail is disabled/unavailable). The candle trail at lines 754-912 takes priority and returns before reaching structural levels.

**Approach — Two options:**

1. **Option A (simpler):** Enable `enable_structural_levels=True` in settings so when the candle trail IS NOT active, the structural level is used as the exit target instead of flat +18¢. This requires NO code changes, just a setting toggle.

2. **Option B (full implementation):** Add structural-level partial exits as a SEPARATE check that fires alongside (not instead of) the candle trail. This would create a new function like `_check_structural_level_partial()` that:
   - Computes the next structural level above entry
   - If price reaches it, takes a partial and raises the stop
   - Tracks "levels taken profit at" on the position

**Recommendation:** Start with Option A (toggle existing setting). If P&L improves, consider Option B for the take-profit→add-back cycle in a follow-up phase.

> [!IMPORTANT]  
> The take-profit→add-back cycle (research doc Section 6) is the CORE of Ross's methodology. However, it requires *coordination* between the exit module (partial at level) and the scaling module (add back after level holds). This creates a cross-module interaction that is more complex than just modifying scaling. Consider implementing this as a separate sub-phase or follow-up.

---

### Change Point #7: Monitor Tick Loop Wiring

**What:** Wire the new level-break scaling check in the monitor tick loop.

**File:** `warrior_monitor.py`  
**Location:** `_check_all_positions()`, lines 577-607

**Current wiring:**
```python
# Check pullback scaling first
if self.settings.enable_scaling:
    scale_signal = await self._check_scale_opportunity(
        position, Decimal(str(current_price))
    )

# Momentum add check (independent trigger, same execution path)
if not scale_signal and self.settings.enable_momentum_adds:
    from nexus2.domain.automation.warrior_monitor_scale import check_momentum_add
    scale_signal = await check_momentum_add(
        self, position, Decimal(str(current_price))
    )
```

**Approach:** The existing wiring is sufficient. `check_scale_opportunity()` is already called here — we're replacing its *internals*, not its call site. The `enable_scaling` master switch still controls whether scaling is active.

**The only change needed:** If using a new settings flag (`enable_level_break_scaling`), add a routing check:
```python
if self.settings.enable_scaling:
    if self.settings.enable_level_break_scaling:
        # New level-break scaling
        scale_signal = await self._check_level_break_scale(...)
    else:
        # Legacy accidental scaling
        scale_signal = await self._check_scale_opportunity(...)
```

Alternatively, keep the same function name and use the flag internally — cleaner, fewer changes.

---

## D. Wiring Checklist

The implementer should check off each item:

- [ ] `enable_level_break_scaling` field added to `WarriorMonitorSettings`
- [ ] `level_break_increment` field added to `WarriorMonitorSettings`
- [ ] `level_break_min_distance_cents` field added to `WarriorMonitorSettings`
- [ ] `level_break_macd_gate` field added to `WarriorMonitorSettings`
- [ ] `level_break_macd_tolerance` field added to `WarriorMonitorSettings`
- [ ] `last_level_break_price` field added to `WarriorPosition`
- [ ] `check_scale_opportunity()` rewritten with level-break logic
- [ ] MACD gate added (using `get_technical_service().get_snapshot()`)
- [ ] `_compute_structural_target` imported from `warrior_monitor_exit.py`
- [ ] Level tracking: `position.last_level_break_price` set after successful scale
- [ ] `enable_structural_levels` toggled to `True` (or new profit-take logic added)
- [ ] Monitor tick loop routes to new logic when `enable_level_break_scaling=True`
- [ ] Existing `enable_scaling` master switch still works
- [ ] Momentum adds remain independent (not affected by this change)
- [ ] Trace logging updated with level-break info

---

## E. Risk Assessment

### What Could Go Wrong

| Risk | Severity | Mitigation |
|------|----------|------------|
| Over-scaling: levels too close, multiple adds per bar | HIGH | `min_distance_cents=10` + `max_scale_count=4` cap |
| MACD fetch failure blocks all scaling | MEDIUM | Fail-open for scaling (unlike entries which fail-closed). Log warning but allow scale |
| Performance: fetching candles + computing MACD on every tick | MEDIUM | Only compute MACD AFTER level-break detected (not on every tick) |
| Regression: breaking existing +$3,681 accidental benefit | HIGH | A/B testable via `enable_level_break_scaling`. Run batch test with both |
| Momentum adds interaction | LOW | Independent system, separate counters, unaffected |
| Structural level exit + scaling conflict | MEDIUM | If exit takes profit at $7.00 AND scaling adds at $7.00, could create wash. Need ordering: exit check runs BEFORE scale check (already true in monitor loop) |

### What Existing Behavior Might Break

1. **Accidental 1-scale-per-case behavior** — This is intentionally being replaced. The A/B flag protects against regression.
2. **Candle trail interaction** — After a partial exit, the position switches to `home_run` mode. Scaling should NOT add back shares after partial (or should it? This is the take-profit→add-back question).

### What to Test After Implementation

1. **Batch test** (`gc_quick_test.py`) — Compare P&L against $359K baseline
2. **GRI case** — The flagship level-break case. Ross added at every $0.50/$1.00. Bot should show multiple scales at $6, $6.50, $7, $7.50, etc.
3. **ROLR case** — Ross used take-profit→add-back. Check if structural exits + level adds improve over accidental scaling.
4. **NPT case** — Already close ($68K vs $81K). Should not regress.
5. **MACD-negative cases** — Verify no scaling occurs when MACD is red (check BATL).

---

## F. Open Questions for Coordinator

1. **MACD gate fail-open vs fail-closed for scaling?** Entry guards fail-closed (no MACD = no trade). For scaling, should we fail-open (allow scale without MACD data) since the position is already open? **Recommendation:** Fail-open with WARNING log.

2. **Take-profit→add-back cycle scope:** The research doc calls this "the single most important pattern." Should this be part of Scaling v2 or a separate Scaling v3? It requires exit/scaling cross-module coordination. **Recommendation:** Separate follow-up — get level-break scaling working first, then add the cycle.

3. **`min_rvol_for_scale` — dead code?** It's documented in settings (line 110) but NEVER checked in the actual scaling code. Should the implementer add an RVOL check, or remove the setting?

4. **Structural level exits:** Enable `enable_structural_levels=True` now (simple toggle), or wait for a more sophisticated implementation? Enabling it changes the fallback target from +18¢ to the next $X.00/$X.50 level — this could affect P&L.
