# Backend Status: `catalyst_source` Column

**Date:** 2026-02-20
**Status:** ✅ Complete
**Tests:** 757 passed, 4 skipped, 3 deselected, 0 failures

---

## Changes Made

### `telemetry_db.py`

| # | Change | Line |
|---|--------|------|
| 1 | Added `catalyst_source = Column(String(20), nullable=True)` to `WarriorScanResult` | After `catalyst_type` (line 53) |
| 2 | Added `"catalyst_source": self.catalyst_source` to `to_dict()` | After `catalyst_type` entry (line 75) |
| 3 | Added `"catalyst_source": "VARCHAR(20)"` to migration dict | In `_migrate_telemetry_columns` (line 215) |

### `warrior_scanner_service.py`

| # | Change | Line | Source Value |
|---|--------|------|-------------|
| 4 | Added `catalyst_source: Optional[str] = None` to `EvaluationContext` | After `catalyst_date` (line 456) | — |
| 5 | Set `ctx.catalyst_source = "regex"` in `_evaluate_catalyst_pillar` | Classifier match path (line 1336) | `"regex"` |
| 6 | Set `ctx.catalyst_source = "calendar"` in `_evaluate_catalyst_pillar` | Earnings calendar path (line 1410) | `"calendar"` |
| 7 | Set `ctx.catalyst_source = "former_runner"` in `_evaluate_catalyst_pillar` | Former runner path (line 1420) | `"former_runner"` |
| 8 | Set `ctx.catalyst_source = "ai"` in `_run_multi_model_catalyst_validation` | Cached headline hit (line 1443) | `"ai"` |
| 9 | Set `ctx.catalyst_source = "ai"` in `_run_multi_model_catalyst_validation` | Fresh AI validation (line 1498) | `"ai"` |
| 10 | Pass `catalyst_source=ctx.catalyst_source if ctx else None` in `_write_scan_result_to_db` | DB write (line 579) | — |

---

## Testable Claims

| # | Claim | Verify With |
|---|-------|-------------|
| 1 | `WarriorScanResult` model has `catalyst_source` column | `Select-String -Path "nexus2\db\telemetry_db.py" -Pattern "catalyst_source"` |
| 2 | `to_dict()` includes `catalyst_source` | Same search, line ~75 |
| 3 | Migration dict includes `catalyst_source` | Same search, line ~215 |
| 4 | `EvaluationContext` has `catalyst_source` field | `Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern "catalyst_source"` |
| 5 | Regex path sets `catalyst_source = "regex"` | Same search |
| 6 | Calendar path sets `catalyst_source = "calendar"` | Same search |
| 7 | Former runner path sets `catalyst_source = "former_runner"` | Same search |
| 8 | AI cache path sets `catalyst_source = "ai"` | Same search |
| 9 | Fresh AI path sets `catalyst_source = "ai"` | Same search |
| 10 | DB write passes `catalyst_source` | Same search |

---

## VPS Migration Required

```bash
sqlite3 ~/Nexus2/data/telemetry.db "ALTER TABLE warrior_scan_results ADD COLUMN catalyst_source VARCHAR(20);"
```
