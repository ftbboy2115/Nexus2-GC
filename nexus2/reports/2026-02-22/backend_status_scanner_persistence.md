# Backend Status: Scanner Settings Persistence

**Date:** 2026-02-22
**Agent:** Backend Specialist
**Task:** Verify and fix scanner settings persistence across restarts

---

## Summary

**Finding:** Scanner settings (`min_rvol`, `max_price`, etc.) were stored **in-memory only**. The `PUT /warrior/scanner/settings` endpoint updated the singleton `WarriorScanSettings` object but never wrote to disk. All scanner setting changes were lost on server restart.

**Fix:** Added JSON-based persistence following the existing pattern used by engine config (`warrior_settings.py`) and monitor settings (`warrior_monitor_settings.py`).

---

## Root Cause

| Endpoint | Before Fix | After Fix |
|----------|-----------|-----------|
| `PUT /warrior/config` | ✅ Persists to `warrior_settings.json` (line 510-514) | No change |
| `PUT /warrior/monitor/settings` | ✅ Persists to `warrior_monitor_settings.json` (line 884-888) | No change |
| `PUT /warrior/scanner/settings` | ❌ **In-memory only** (line 797-815) | ✅ Persists to `warrior_scanner_settings.json` |

---

## Files Modified

### [NEW] `nexus2/db/warrior_scanner_settings.py`

Scanner settings persistence module (follows `warrior_monitor_settings.py` pattern):
- `save_scanner_settings(settings: dict) -> bool` — Serialize + write to `data/warrior_scanner_settings.json`
- `load_scanner_settings() -> Optional[dict]` — Read from JSON
- `apply_scanner_settings(scan_settings_obj, settings: dict)` — Apply dict to `WarriorScanSettings` dataclass
- `get_scanner_settings_dict(scan_settings_obj) -> dict` — Convert dataclass to serializable dict

**Persisted fields:** `max_float`, `ideal_float`, `min_rvol`, `ideal_rvol`, `min_gap`, `ideal_gap`, `min_price`, `max_price`, `require_catalyst`, `exclude_chinese_stocks`

### [MODIFY] `nexus2/api/routes/warrior_routes.py` (line 815-821)

Added persistence call after in-memory update in `PUT /warrior/scanner/settings`:
```python
# Persist scanner settings to disk (survive restarts)
try:
    from nexus2.db.warrior_scanner_settings import save_scanner_settings, get_scanner_settings_dict
    save_scanner_settings(get_scanner_settings_dict(scanner.settings))
except Exception as e:
    print(f"[Warrior] Failed to persist scanner settings: {e}")
```

### [MODIFY] `nexus2/domain/scanner/warrior_scanner_service.py` (line 1856-1865)

Added loading of persisted settings in `get_warrior_scanner_service()` singleton:
```python
# Load persisted scanner settings (survive restarts)
try:
    from nexus2.db.warrior_scanner_settings import load_scanner_settings, apply_scanner_settings
    saved = load_scanner_settings()
    if saved:
        apply_scanner_settings(_warrior_scanner_service.settings, saved)
        scan_logger.info(f"Loaded persisted scanner settings: min_rvol={_warrior_scanner_service.settings.min_rvol}")
except Exception as e:
    scan_logger.warning(f"Could not load persisted scanner settings: {e}")
```

---

## Verification

### 1. Import Check
```
Command: .venv\Scripts\python -c "from nexus2.db.warrior_scanner_settings import save_scanner_settings, load_scanner_settings, apply_scanner_settings, get_scanner_settings_dict; print('Import OK')"
Output: Import OK
```

### 2. Save/Load Cycle
```
Command: .venv\Scripts\python -c "from nexus2.db.warrior_scanner_settings import save_scanner_settings, load_scanner_settings; save_scanner_settings({'min_rvol': 1.5, ...}); loaded = load_scanner_settings(); ..."
Output:
  [Warrior Scanner Settings] Saved to ...data\warrior_scanner_settings.json
  Saved + Loaded: {'min_rvol': 1.5, 'max_price': 40.0, 'require_catalyst': True}
  Before apply: 2.0
  [Warrior Scanner Settings] Applied: min_rvol=1.5, max_price=40.0
  After apply: 1.5
```

### 3. Full Test Suite
```
Command: .venv\Scripts\python -m pytest nexus2/tests/ -x -q --tb=short
Output: 757 passed, 4 skipped, 3 deselected in 143.46s
```

### 4. Default Unchanged
The default `min_rvol` remains `2.0` in `WarriorScanSettings` (line 111). Only API-set overrides are persisted.

---

## Testable Claims for Validator

| # | Claim | Verification |
|---|-------|-------------|
| 1 | `warrior_scanner_settings.py` exists with save/load/apply/get_dict functions | `Select-String -Path "nexus2\db\warrior_scanner_settings.py" -Pattern "def "` |
| 2 | JSON file path is `data/warrior_scanner_settings.json` | `Select-String -Path "nexus2\db\warrior_scanner_settings.py" -Pattern "SCANNER_SETTINGS_FILE"` |
| 3 | `PUT /scanner/settings` calls `save_scanner_settings` | `Select-String -Path "nexus2\api\routes\warrior_routes.py" -Pattern "save_scanner_settings"` |
| 4 | Singleton loads persisted settings on first access | `Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern "load_scanner_settings"` |
| 5 | `min_rvol` default unchanged at `2.0` | `Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern 'min_rvol.*Decimal'` |
| 6 | All tests pass (757 passed) | `pytest nexus2/tests/ -x -q` |
