# Handoff: Momentum Scaling Implementation + A/B Test Script

**Date:** 2026-02-24
**From:** Coordinator
**To:** Backend Specialist
**Priority:** HIGH — addresses #1 P&L gap (NPT $63K)

---

## Context

The Warrior bot captures 37.2% of Ross's P&L ($161K vs $433K). NPT diagnosis shows the bot enters correctly ($7.72 ≈ Ross's $7.50) but never adds on momentum — Ross added at $10, $11, $12, $15, $20s for $81K total.

**Current scaling is accidental**: With `enable_improved_scaling=False` (default), the pullback zone check at `warrior_monitor_scale.py:133` is always True, producing exactly 1 scale per case (+50% shares on first eligible bar). This "accident" adds +38% P&L. Neither current mode adds shares when price goes UP.

---

## Verified Facts

**Scaling settings** — `warrior_types.py:99-170`:
```python
enable_scaling: bool = True          # ON by default
max_scale_count: int = 2             # max 2 adds
scale_size_pct: int = 50             # 50% of original per add
enable_improved_scaling: bool = False # "improved" mode OFF (accidental mode is +38% P&L)
```
Verified via: `Select-String -Path "nexus2\domain\automation\warrior_types.py" -Pattern "scale|scaling"`

**Scale detection** — `warrior_monitor_scale.py:31-155` (`check_scale_opportunity()`):
- Line 49: `if not s.enable_scaling: return None` — gating
- Line 115-136: pullback zone logic — requires price to DROP 50% toward support
- Line 77-82: 60s cooldown (skipped in sim when improved=True)
- Line 139: `add_shares = int(position.original_shares * s.scale_size_pct / 100)`

**Scale execution** — `warrior_monitor_scale.py:163-359` (`execute_scale_in()`):
- Submits limit buy order
- Updates weighted avg entry price
- Updates scale_count, shares

**Monitor integration** — `warrior_monitor.py:579`:
```python
should_check_scale = current_price and self.settings.enable_scaling
```

**WarriorPosition** includes: `scale_count`, `last_scale_attempt`, `original_shares`, `high_since_entry`

---

## Task 1: Add Momentum Scaling Settings

**File:** `nexus2/domain/automation/warrior_types.py`

Add after line 112 (below `move_stop_to_breakeven_after_scale`):

```python
# Momentum Scaling (add on strength — Ross adds at $10, $11, $12 etc.)
enable_momentum_adds: bool = False      # A/B testable: add shares on breakout continuation
momentum_add_interval: float = 1.00     # Min price move above last add/entry before triggering ($1)
momentum_add_size_pct: int = 50         # Size of each momentum add (% of original position)
max_momentum_adds: int = 3              # Max momentum adds per position
```

Add to `WarriorPosition` dataclass (after `last_scale_attempt`):

```python
last_momentum_add_price: Optional[Decimal] = None  # Track price of last momentum add
momentum_add_count: int = 0                         # Number of momentum adds taken
```

---

## Task 2: Implement `check_momentum_add()` Function

**File:** `nexus2/domain/automation/warrior_monitor_scale.py`

Add a NEW function `check_momentum_add()` after `check_scale_opportunity()` (after line 155). This is the core logic:

**Trigger criteria (Ross Cameron breakout continuation):**
1. `s.enable_momentum_adds` is True
2. Position is green: `current_price > position.entry_price`
3. `position.momentum_add_count < s.max_momentum_adds`
4. Price has moved up at least `s.momentum_add_interval` since last add price (or entry price if no adds yet)
5. Position not pending exit
6. Similar safety checks as `check_scale_opportunity()` (no pending exit, stop buffer)

**Track last add price:**
- On first momentum add: compare `current_price` vs `position.entry_price`
- On subsequent adds: compare `current_price` vs `position.last_momentum_add_price`
- Trigger when `current_price >= reference_price + momentum_add_interval`

**Return format:** Same dict format as `check_scale_opportunity()` so `execute_scale_in()` can handle both:
```python
return {
    "position_id": position.position_id,
    "symbol": position.symbol,
    "add_shares": add_shares,
    "price": float(current_price),
    "support": float(support),
    "scale_count": position.scale_count + 1,
    "trigger": "momentum",  # NEW: distinguish from "pullback"
}
```

**Calculate add_shares:**
```python
add_shares = int(position.original_shares * s.momentum_add_size_pct / 100)
```

---

## Task 3: Integrate in Monitor Loop

**File:** `nexus2/domain/automation/warrior_monitor.py`

Find the scale check near line 579. After the existing `check_scale_opportunity()` call, add:

```python
# Momentum add check (independent trigger, same execution path)
if not scale_signal and self.settings.enable_momentum_adds:
    from nexus2.domain.automation.warrior_monitor_scale import check_momentum_add
    scale_signal = await check_momentum_add(self, position, current_price)
```

This reuses `execute_scale_in()` for execution — the only change needed there is updating `last_momentum_add_price` and `momentum_add_count` after a successful momentum add. Add to `execute_scale_in()`:

```python
# After successful scale, update momentum tracking
if scale_signal.get("trigger") == "momentum":
    position.last_momentum_add_price = price
    position.momentum_add_count += 1
```

---

## Task 4: A/B Test Script

**File:** `scripts/ab_test_scaling.py` (NEW)

Create a script that runs 5 variants back-to-back:

| Variant | Settings Override |
|---------|------------------|
| `no_scale` | `enable_scaling=False, enable_momentum_adds=False` |
| `baseline` | `enable_scaling=True, enable_improved_scaling=False, enable_momentum_adds=False` (current) |
| `momentum_only` | `enable_scaling=False, enable_momentum_adds=True` |
| `pullback_only` | `enable_scaling=True, enable_improved_scaling=True, enable_momentum_adds=False` |
| `combined` | `enable_scaling=True, enable_improved_scaling=True, enable_momentum_adds=True` |

**For each variant:**
1. `PUT http://127.0.0.1:8000/warrior/monitor/settings` with overrides
2. `POST http://127.0.0.1:8000/warrior/sim/run_batch_concurrent` (full batch)
3. Collect results
4. Restore original settings

**Output:** Comparison table showing per-variant totals:
```
Variant         | Bot P&L    | Capture | Delta vs Baseline | Runtime
----------------|------------|---------|-------------------|--------
no_scale        | $X         | X%      | $X                | Xs
baseline        | $161,116   | 37.2%   | —                 | 34s
momentum_only   | $X         | X%      | $X                | Xs
pullback_only   | $X         | X%      | $X                | Xs
combined        | $X         | X%      | $X                | Xs
```

Also output per-case regressions (any case where variant P&L < baseline P&L).

**Use `http://127.0.0.1:8000`** (NOT `localhost` — IPv6 issue on Windows).

---

## Open Questions (For Agent to Investigate)

1. Does `execute_scale_in()` update `max_scale_count` properly when both pullback AND momentum adds are used? They share `position.scale_count` — should momentum adds have their own counter?
2. Should momentum adds share the same `max_scale_count` limit or use `max_momentum_adds` independently?
3. The 60s cooldown (line 77-82) — should it apply to momentum adds in sim mode?

---

## Verification

1. Run `pytest nexus2/tests/` — must pass with no new failures
2. Run the A/B test script and verify all 5 variants complete
3. Write output to `nexus2/reports/2026-02-24/backend_status_momentum_scaling.md`
