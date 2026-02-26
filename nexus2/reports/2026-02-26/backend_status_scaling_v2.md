# Backend Status: Scaling V2 Implementation

**Date:** 2026-02-26  
**Agent:** Backend Specialist  
**Status:** ✅ Complete — ready for validation

---

## Changes Made

### 1. `warrior_types.py` — Settings & Position Fields

**New settings** added to `WarriorMonitorSettings` (after line 112):
```python
enable_level_break_scaling: bool = True
level_break_increment: float = 0.50
level_break_min_distance_cents: int = 10
level_break_macd_gate: bool = True
level_break_macd_tolerance: float = -0.02
```

**Default changed:**
- `enable_structural_levels`: `False` → `True` (line ~157)

**New position field** added to `WarriorPosition` (after line 215):
```python
last_level_break_price: Optional[Decimal] = None
```

---

### 2. `warrior_monitor_scale.py` — Core Logic Replacement

**`check_scale_opportunity()`** (lines 31-60): Now routes between level-break and legacy:
- `enable_level_break_scaling=True` → `_check_level_break_scale()` (new)
- `enable_level_break_scaling=False` → `_check_legacy_scale()` (preserves accidental behavior)

**New functions:**
- `_check_level_break_scale()`: Computes next structural level via `_compute_structural_target`, checks if price has broken through, runs MACD gate
- `_check_scaling_macd_gate()`: Fail-closed MACD check adapted from entry guards. Uses `monitor._get_intraday_candles` + `get_technical_service().get_snapshot()`
- `_check_legacy_scale()`: Exact copy of original accidental logic for A/B testing

**Import added:** `from nexus2.domain.automation.warrior_monitor_exit import _compute_structural_target`

**`execute_scale_in()`**: Updated to track `position.last_level_break_price` when trigger is `"level_break"`

---

### 3. `warrior_monitor_settings.py` — Settings Persistence

Added all 5 new fields to both:
- `apply_monitor_settings()` — load from JSON
- `get_monitor_settings_dict()` — serialize to JSON

---

### 4. Test Fixes (Pre-existing)

Fixed 3 stale assertions for `partial_exit_fraction` (changed from 0.5 to 0.25 in a previous param sweep):
- `test_warrior_integration.py:99`
- `test_warrior_monitor.py:71`
- `test_warrior_monitor.py:263`

---

## Testable Claims

| # | Claim | File | Verification |
|---|-------|------|-------------|
| 1 | `enable_level_break_scaling` field exists on `WarriorMonitorSettings` | `warrior_types.py` | `grep "enable_level_break_scaling"` |
| 2 | `last_level_break_price` field exists on `WarriorPosition` | `warrior_types.py` | `grep "last_level_break_price"` |
| 3 | `check_scale_opportunity()` checks `enable_level_break_scaling` to route logic | `warrior_monitor_scale.py:56` | `grep "enable_level_break_scaling"` |
| 4 | MACD gate (`_check_scaling_macd_gate`) called inside level-break path | `warrior_monitor_scale.py` | `grep "_check_scaling_macd_gate"` |
| 5 | `_compute_structural_target` imported from `warrior_monitor_exit` | `warrior_monitor_scale.py:19` | `grep "from nexus2.domain.automation.warrior_monitor_exit import _compute_structural_target"` |
| 6 | `position.last_level_break_price` set after successful scale-in | `warrior_monitor_scale.py` | `grep "last_level_break_price = level_price"` |
| 7 | `enable_structural_levels` defaults to `True` | `warrior_types.py` | `grep "enable_structural_levels"` |
| 8 | All existing tests pass | — | `pytest nexus2/tests/ -x -q` → 757 passed |

---

## A/B Testing Ready

The implementation supports these batch test configurations via `monitor_overrides`:

| Test | Override | Expected |
|------|----------|----------|
| Baseline (accidental) | `{"enable_level_break_scaling": false}` | ~$359K |
| Level-break only | `{"enable_level_break_scaling": true, "enable_structural_levels": false}` | ? |
| Level-break + structural exits | `{"enable_level_break_scaling": true, "enable_structural_levels": true}` | ? |
| MACD gate off | `{"level_break_macd_gate": false}` | ? |

---

## What Was NOT Changed

- ❌ Momentum adds system — untouched, independent
- ❌ `warrior_monitor.py` — no wiring changes needed (internal routing via settings flag)
- ❌ `warrior_monitor_exit.py` — no code changes (just setting default toggle)
- ❌ `min_rvol_for_scale` — left as-is per Clay's decision
- ❌ Take-profit → add-back cycle — not this phase
