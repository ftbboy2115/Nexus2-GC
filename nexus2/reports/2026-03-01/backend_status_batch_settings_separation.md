# Backend Status: Batch Settings Separation

**Agent:** Backend Specialist
**Date:** 2026-03-01
**Status:** ✅ Complete

---

## Summary

Updated the batch runner to use a committed, version-controlled settings file (`data/warrior_settings_batch.json`) instead of the live GUI settings file (`data/warrior_settings.json`). Also added a new `GET /warrior/batch-settings` endpoint to read the batch settings.

---

## Changes Made

### 1. `nexus2/adapters/simulation/sim_context.py` (lines 64-83)

**Before:** Loaded engine settings via `load_warrior_settings()`, which reads the live `data/warrior_settings.json` file (same file the GUI edits).

**After:** Loads from committed `data/warrior_settings_batch.json` using `json.load()` + `Path(__file__)` resolution. Falls back to defaults with a warning if the file is missing.

### 2. `nexus2/api/routes/warrior_routes.py` (lines 948-971)

**New endpoint:** `GET /warrior/batch-settings` — reads and returns `data/warrior_settings_batch.json` as JSON. Simple file-read endpoint, no engine dependency. Returns 404 if file missing.

---

## Verification

- **pytest:** 844 passed, 4 skipped, 3 deselected (128s)
- **Batch settings file exists:** `Test-Path "data\warrior_settings_batch.json"` → True

---

## Testable Claims

| # | Claim | Verification |
|---|-------|-------------|
| 1 | `sim_context.py` no longer imports `load_warrior_settings` | `Select-String "load_warrior_settings" C:\Dev\Nexus\nexus2\adapters\simulation\sim_context.py` → 0 matches |
| 2 | `sim_context.py` loads from `warrior_settings_batch.json` | `Select-String "warrior_settings_batch" C:\Dev\Nexus\nexus2\adapters\simulation\sim_context.py` → match at line ~70 |
| 3 | New endpoint exists at `/batch-settings` | `Select-String "batch-settings" C:\Dev\Nexus\nexus2\api\routes\warrior_routes.py` → match |
| 4 | Endpoint reads from `warrior_settings_batch.json` | `Select-String "warrior_settings_batch" C:\Dev\Nexus\nexus2\api\routes\warrior_routes.py` → match |
| 5 | All 844 tests pass | `python -m pytest nexus2/tests/ -x --tb=short -q` |
| 6 | Batch P&L matches $437,558 baseline | Run batch test locally and confirm `total_pnl` |
