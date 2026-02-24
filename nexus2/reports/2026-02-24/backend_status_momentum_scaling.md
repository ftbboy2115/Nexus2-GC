# Backend Status: Momentum Scaling Implementation

**Date:** 2026-02-24
**Agent:** Backend Specialist
**Status:** ✅ COMPLETE — All 4 deliverables implemented, pytest passing (757 passed)

---

## Summary

Implemented momentum scaling for Warrior bot — Ross Cameron "add on strength" methodology. When NPT enters at $7.72, Ross adds at $10, $11, $12, $15, $20s for $81K total. The bot previously never added on upward momentum. This implementation adds independent momentum add detection alongside existing pullback scaling.

**Key design decision:** Momentum adds use **independent counters** (`momentum_add_count` / `max_momentum_adds`) from pullback scaling (`scale_count` / `max_scale_count`). Both systems share `execute_scale_in()` for execution but are independently A/B testable.

---

## Deliverables

### Task 1: Momentum Settings — `warrior_types.py`

**WarriorMonitorSettings** (after line 112):
```python
enable_momentum_adds: bool = False      # A/B testable
momentum_add_interval: float = 1.00     # $1 min move between adds
momentum_add_size_pct: int = 50         # 50% of original per add
max_momentum_adds: int = 3              # Max 3 momentum adds
```

**WarriorPosition** (after `last_scale_attempt`):
```python
last_momentum_add_price: Optional[Decimal] = None  # Track last add price
momentum_add_count: int = 0                         # Independent counter
```

**Testable claim:** `warrior_types.py` lines 115-118 contain momentum settings, lines 208-209 contain position fields.

---

### Task 2: `check_momentum_add()` — `warrior_monitor_scale.py`

New function at line 162-253. Trigger criteria:
1. `enable_momentum_adds` is True
2. Position is green (`current_price > entry_price`)
3. `momentum_add_count < max_momentum_adds`
4. Price moved up ≥ `momentum_add_interval` since last add (or entry if no adds)
5. Not pending exit
6. Price not too close to stop (≥1% buffer)
7. 60s cooldown (bypassed in sim mode)

Returns same dict format as `check_scale_opportunity()` with `"trigger": "momentum"`.

Also added `"trigger": "pullback"` to existing `check_scale_opportunity()` return dict (line 155).

**Testable claim:** `warrior_monitor_scale.py` contains `async def check_momentum_add` and returns dicts with `"trigger": "momentum"`.

---

### Task 3: Monitor Integration — `warrior_monitor.py` + `warrior_monitor_scale.py`

**Monitor loop** (`_check_all_positions`, lines 579-607):
- Updated `should_check_scale` to also trigger when `enable_momentum_adds` is True
- After existing pullback check, falls through to `check_momentum_add()` if no pullback signal
- Both trigger types reuse `execute_scale_in()`

**execute_scale_in** tracking (lines 358-365):
```python
if scale_signal.get("trigger") == "momentum":
    position.last_momentum_add_price = price
    position.momentum_add_count += 1
```

**Testable claim:** `warrior_monitor.py` line ~595 imports `check_momentum_add`. `warrior_monitor_scale.py` lines 358-365 update momentum tracking after execution.

---

### Task 4: A/B Test Script — `scripts/ab_test_scaling.py`

5-variant comparison script:

| Variant | Settings |
|---------|----------|
| `no_scale` | `enable_scaling=False, enable_momentum_adds=False` |
| `baseline` | `enable_scaling=True, enable_improved_scaling=False, enable_momentum_adds=False` |
| `momentum_only` | `enable_scaling=False, enable_momentum_adds=True` |
| `pullback_only` | `enable_scaling=True, enable_improved_scaling=True, enable_momentum_adds=False` |
| `combined` | `enable_scaling=True, enable_improved_scaling=True, enable_momentum_adds=True` |

Features:
- Saves/restores original settings (even on Ctrl+C)
- `--quick` flag for baseline + momentum_only only
- `--variants` flag for specific variants
- Outputs comparison table + per-case regression analysis
- Saves JSON report to `nexus2/reports/gc_diagnostics/ab_test_scaling_latest.json`
- Uses `http://127.0.0.1:8000` (not localhost — IPv6 fix)

---

### Bonus: API Layer — `warrior_routes.py`

Added to `WarriorMonitorSettingsRequest`, GET response, and PUT handler:
- `enable_improved_scaling` (was missing from API)
- `enable_momentum_adds`
- `momentum_add_interval`
- `momentum_add_size_pct`
- `max_momentum_adds`

Without this, the A/B test script couldn't toggle settings via the API.

---

## Open Questions Resolution

| Question | Resolution |
|----------|-----------|
| Should momentum adds share `scale_count`? | **No** — independent `momentum_add_count` with `max_momentum_adds` |
| Should they share `max_scale_count` limit? | **No** — independent limit for A/B testability |
| 60s cooldown in sim? | **Bypassed** in sim mode (same pattern as improved scaling) |

---

## Verification

- **pytest:** 757 passed, 4 skipped, 3 deselected, 0 failures ✅
- **No new test files created** (per Backend Specialist rules — Testing Specialist owns tests)

## Files Modified

| File | Change |
|------|--------|
| `nexus2/domain/automation/warrior_types.py` | +6 settings fields, +2 position fields |
| `nexus2/domain/automation/warrior_monitor_scale.py` | +`check_momentum_add()` function, +`trigger` key, +momentum tracking in execute |
| `nexus2/domain/automation/warrior_monitor.py` | Updated monitor loop to check momentum adds |
| `nexus2/api/routes/warrior_routes.py` | +5 API fields (request, response, handler) |
| `scripts/ab_test_scaling.py` | **NEW** — A/B test script |
