# Backend Status: Sim-Aware Time Refactor

**Agent:** Backend Specialist  
**Date:** 2026-02-28  
**Status:** ✅ Complete

---

## Summary

Centralized sim-clock-aware time into `sim_aware_now_utc()` and `sim_aware_now_et()` in `time_utils.py`. Refactored `warrior_monitor_exit.py` to use these instead of the scattered `_get_sim_aware_now_utc(monitor)` helper and raw `now_utc()` / `datetime.now()` calls. Also fixed 2 remaining `now_utc()` sites at L1505/L1534 that the previous exit clock fix missed.

---

## Files Modified

### `nexus2/utils/time_utils.py`
- Added `sim_aware_now_utc()` — returns sim clock time via `_sim_clock_ctx` ContextVar if set, else real UTC
- Added `sim_aware_now_et()` — same but returns Eastern Time

### `nexus2/domain/automation/warrior_monitor_exit.py`
- Removed `_get_sim_aware_now_utc(monitor)` helper (L34-48)
- Replaced 3 `_get_sim_aware_now_utc(monitor)` calls with `sim_aware_now_utc()` (spread grace, candle-under-candle grace, topping tail grace)
- Replaced 5m bucket if/else sim-clock block with `sim_aware_now_et()` (was 7 lines → 1 line)
- Replaced `now_utc()` at L1505 (recently_exited timestamp) with `sim_aware_now_utc()`
- Replaced `now_utc()` at L1534 (exit_time in on_profit_exit) with `sim_aware_now_utc()`
- Updated import: `now_utc` → `sim_aware_now_utc, sim_aware_now_et`

### NOT Modified (intentional)
- `_check_after_hours_exit` L207/L218: `datetime.now(ET)` — these are live-mode fallbacks in a multi-priority sim-clock block with its own handling

---

## Testable Claims

| # | Claim | Verification |
|---|-------|-------------|
| 1 | `sim_aware_now_utc()` exists in `time_utils.py` and uses `_sim_clock_ctx` ContextVar | `Select-String -Path nexus2\utils\time_utils.py -Pattern "sim_aware_now_utc"` |
| 2 | `sim_aware_now_et()` exists in `time_utils.py` and returns ET | `Select-String -Path nexus2\utils\time_utils.py -Pattern "sim_aware_now_et"` |
| 3 | No standalone `now_utc()` calls remain in `warrior_monitor_exit.py` | `Select-String -Path nexus2\domain\automation\warrior_monitor_exit.py -Pattern "(?<![a-z_])now_utc\(\)"` → 0 matches |
| 4 | `_get_sim_aware_now_utc` helper is fully removed | `Select-String -Path nexus2\domain\automation\warrior_monitor_exit.py -Pattern "_get_sim_aware_now_utc"` → 0 matches |
| 5 | `datetime.now(` only appears in `_check_after_hours_exit` (intentional live-mode fallbacks) | `Select-String -Path nexus2\domain\automation\warrior_monitor_exit.py -Pattern "datetime\.now\("` → 2 matches at L207/L218 |
| 6 | All 844 tests pass | `python -m pytest nexus2/tests/ -x -q` → 844 passed |
| 7 | No impact on live trading: `sim_aware_now_utc()` falls back to `now_utc()` when ContextVar is unset | Code inspection: `time_utils.py` L58-76 |

---

## Verification Results

```
pytest: 844 passed, 4 skipped, 3 deselected in 137.25s
now_utc() standalone:    0 matches ✅
_get_sim_aware_now_utc:  0 matches ✅
datetime.now(:           2 matches (L207/L218 — intentional) ✅
```
