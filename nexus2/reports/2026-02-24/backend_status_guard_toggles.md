# Backend Status: Guard Toggles for GC Param Sweep

**Date:** 2026-02-24
**Agent:** Backend Specialist
**Status:** ✅ COMPLETE
**pytest:** 757 passed, 4 skipped, 3 deselected (103.91s)

---

## Summary

Made all three guard tuning fixes API-toggleable so GC can sweep combinations at runtime without code changes. Default values preserve current behavior.

---

## Deliverables

### 1. Re-added profit-check guard behind toggle

| File | Change |
|------|--------|
| `warrior_types.py:115` | Added `enable_profit_check_guard: bool = False` to `WarriorMonitorSettings` |
| `warrior_entry_guards.py:271-279` | Re-added 25% profit-check guard gated on `monitor.settings.enable_profit_check_guard` |

**Behavior:**
- `enable_profit_check_guard=False` (default) → guard disabled (current behavior)
- `enable_profit_check_guard=True` → blocks adds when unrealized P&L > 25% or past target

### 2. Exposed `macd_histogram_tolerance` via API

| File | Change |
|------|--------|
| `warrior_routes.py:88` | Added `macd_histogram_tolerance` to `WarriorEngineConfigRequest` |
| `warrior_routes.py:514-516` | PUT handler applies value to `engine.config.macd_histogram_tolerance` |
| `warrior_routes.py:538` | GET response includes `macd_histogram_tolerance` |

**Behavior:**
- `macd_histogram_tolerance=-0.02` (default) → allows slightly negative MACD (current behavior)
- `macd_histogram_tolerance=0` → restores original binary MACD blocking

### 3. Wired both fields to GET/PUT API endpoints

| Endpoint | Field | Location |
|----------|-------|----------|
| `GET /warrior/monitor/settings` | `enable_profit_check_guard` | `warrior_routes.py:862` |
| `PUT /warrior/monitor/settings` | `enable_profit_check_guard` | `warrior_routes.py:900` |
| `PUT /warrior/config` | `macd_histogram_tolerance` | `warrior_routes.py:514` |
| `GET /warrior/config` (response) | `macd_histogram_tolerance` | `warrior_routes.py:538` |

### 4. Persistence (save/load across restarts)

| File | Change |
|------|--------|
| `warrior_settings.py:155` | `macd_histogram_tolerance` added to `get_config_dict` |
| `warrior_settings.py:189` | `macd_histogram_tolerance` added to `apply_settings_to_config` |
| `warrior_monitor_settings.py:128-129` | `enable_profit_check_guard` added to `apply_monitor_settings` |
| `warrior_monitor_settings.py:170` | `enable_profit_check_guard` added to `get_monitor_settings_dict` |

---

## Testable Claims (for Validator)

| # | Claim | Verification |
|---|-------|-------------|
| 1 | `enable_profit_check_guard: bool = False` exists in `WarriorMonitorSettings` | `Select-String -Path "nexus2\domain\automation\warrior_types.py" -Pattern "enable_profit_check_guard"` |
| 2 | Guard code gated on `enable_profit_check_guard` in `_check_position_guards` | `Select-String -Path "nexus2\domain\automation\warrior_entry_guards.py" -Pattern "enable_profit_check_guard"` |
| 3 | `macd_histogram_tolerance` in `WarriorEngineConfigRequest` | `Select-String -Path "nexus2\api\routes\warrior_routes.py" -Pattern "macd_histogram_tolerance"` |
| 4 | `enable_profit_check_guard` in `WarriorMonitorSettingsRequest` | `Select-String -Path "nexus2\api\routes\warrior_routes.py" -Pattern "enable_profit_check_guard"` |
| 5 | Both fields persist via save/load functions | `Select-String -Path "nexus2\db\warrior_settings.py" -Pattern "macd_histogram_tolerance"` and `Select-String -Path "nexus2\db\warrior_monitor_settings.py" -Pattern "enable_profit_check_guard"` |
| 6 | pytest 757 passed | `pytest nexus2\tests\ -x -q` |

---

## Files Modified

1. `nexus2/domain/automation/warrior_types.py` — Added `enable_profit_check_guard` field
2. `nexus2/domain/automation/warrior_entry_guards.py` — Re-added gated 25% guard
3. `nexus2/api/routes/warrior_routes.py` — Added both fields to request models and handlers
4. `nexus2/db/warrior_settings.py` — Added `macd_histogram_tolerance` to persistence
5. `nexus2/db/warrior_monitor_settings.py` — Added `enable_profit_check_guard` to persistence
