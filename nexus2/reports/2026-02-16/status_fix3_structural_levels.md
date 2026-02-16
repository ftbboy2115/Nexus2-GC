# Status: Fix 3 — Structural Profit Levels

**Date:** 2026-02-16  
**Agent:** Backend Specialist  
**Status:** ✅ COMPLETE

---

## Changes Made

### 1. `warrior_types.py` — 3 new config fields
- `enable_structural_levels: bool = True` — A/B toggle
- `structural_level_increment: float = 0.50` — Level spacing
- `structural_level_min_distance_cents: int = 10` — Skip levels closer than 10¢

### 2. `warrior_monitor_exit.py` — New helper + fallback replacement
- Added `_compute_structural_target()` pure function (before `_check_base_hit_target`)
- Replaced flat +18¢ fallback with structural level computation when enabled
- Original flat fallback preserved in `else` branch for A/B testing
- Updated all 3 trigger description strings to use `target_desc` variable

### 3. `warrior_monitor_settings.py` — Persistence
- Added 3 fields to `get_monitor_settings_dict()`
- Added 3 fields to `apply_monitor_settings()`

---

## Verification Results

| Check | Result | Output |
|-------|--------|--------|
| `_compute_structural_target(4.65)` | ✅ | `5.0` (35¢ away) |
| `_compute_structural_target(5.00)` | ✅ | `5.5` (on level → skip) |
| `_compute_structural_target(4.97)` | ✅ | `5.5` (3¢ < 10¢ min → skip) |
| Config defaults | ✅ | `structural=True, inc=0.5, min=10` |
| Persistence round-trip | ✅ | `True True True` |
| Unit tests | ✅ | 36 passed in 4.18s |

---

## A/B Testing

Set `enable_structural_levels=False` to revert to flat +18¢ fallback. The `else` branch is an exact copy of the original code.
