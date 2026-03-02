# Backend Status: Live Re-Entry Cooldown Fix

**Agent:** Backend Specialist  
**Date:** 2026-03-02  
**Issue:** #1 from `research_profitability_blockers.md`

---

## Summary

Implemented a configurable live-mode re-entry cooldown to prevent revenge trading. The old 120-second cooldown was only a fill race-condition guard — now live mode has a proper 10-minute cooldown matching the sim-mode default.

## Changes Made

| # | File | Change |
|---|------|--------|
| 1 | `warrior_types.py` | Added `live_reentry_cooldown_minutes: int = 10` to `WarriorMonitorSettings` (line 155) |
| 2 | `warrior_entry_guards.py` | Replaced `_recovery_cooldown_seconds` (120s) check with `settings.live_reentry_cooldown_minutes` (10 min). Log message now shows minutes instead of seconds. |
| 3 | `warrior_monitor_settings.py` | Added load/save/serialize for `live_reentry_cooldown_minutes` in `apply_monitor_settings()` and `get_monitor_settings_dict()` |
| 4 | `warrior_routes.py` | Added `live_reentry_cooldown_minutes` to `WarriorMonitorSettingsRequest` model (1-60 range), GET `/monitor/settings` response, and PUT `/monitor/settings` handler |

## Design Notes

- **No batch test impact:** Sim mode already has its own 10-minute cooldown (`_reentry_cooldown_minutes`). This change only affects live mode.
- **Backward compatible:** The `_recovery_cooldown_seconds = 120` attribute on `WarriorMonitor` is untouched (no references to it remain in entry guards, but it's kept for any future use).
- **API-tunable:** Can be adjusted at runtime via `PUT /warrior/monitor/settings` with `{"live_reentry_cooldown_minutes": N}` (1-60 range).
- **Persisted:** Setting survives restarts via `warrior_monitor_settings.json`.

## Verification

```
python -m pytest nexus2/tests/ -x --tb=short -q
845 passed, 4 skipped, 3 deselected in 351.63s
```

All tests pass. No regressions.

## Impact on Today's Trades

If this had been in place today:
- **BATL re-entry** (60 min gap): Would still have been allowed (60 > 10). The BATL re-entry was a quality issue, not a cooldown issue.
- **CISS re-entry** (2 min gap): **Would have been BLOCKED** (2 < 10). This saves $1,923.
