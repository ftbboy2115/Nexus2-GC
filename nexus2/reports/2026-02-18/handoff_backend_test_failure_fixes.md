# Handoff: Backend Planner — Test Failure Analysis & Fix Spec

@agent-backend-planner.md

## Context

A testing agent identified 7 test failures across the Warrior subsystem. The coordinator has independently verified all 7 root causes against the actual code. Your task is to research the code, confirm the findings, and write a technical spec for the Backend Specialist to implement fixes.

Write the spec to: `nexus2/reports/2026-02-18/spec_test_failure_fixes.md`

---

## Verified Facts

### Fact 1: `min_dollar_volume` AttributeError (2 test failures)

**File:** [warrior_routes.py:781](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_routes.py#L781)
**Code:**
```python
"min_dollar_volume": float(s.min_dollar_volume),
```

**Problem:** `s` is a `WarriorScanSettings` instance (defined at [warrior_scanner_service.py:86-167](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py#L86-L167)). `WarriorScanSettings` has **no** `min_dollar_volume` field. That field exists only on the NACbot's `scanner_settings.py:35` (`Decimal("5_000_000")`).

**Impact:** Any call to `GET /warrior/scanner/settings` raises `AttributeError`. This breaks the frontend scanner settings panel.

**Fix direction:** Either remove the line (Warrior scanner doesn't use dollar volume filtering) or add the field to `WarriorScanSettings` if it should be a Warrior filter. Research whether any Warrior scan logic uses dollar volume.

**Coordinator evidence:** `Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern "min_dollar_volume"` returns 0 matches. The field only appears in `scanner_settings.py` (NACbot) and `scanner_engine.py` (NACbot engine).

---

### Fact 2: `warrior_scan_results.price` column missing (3 test failures)

**File:** [telemetry_db.py:55](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/db/telemetry_db.py#L55)
**Code:**
```python
# Extended telemetry columns (Feb 2026)
price = Column(Float, nullable=True)  # Last price at scan time
```

**Problem:** The `price` column (and other extended columns: `country`, `ema_200`, `room_to_ema_pct`, `is_etb`, `name`) were added to the SQLAlchemy model but SQLite does **not** auto-migrate existing `.db` files. Older `telemetry.db` files created before these columns were added will raise `OperationalError: no such column: warrior_scan_results.price` when the scanner writes results.

**Impact:** Scanner telemetry writes fail silently (caught by `except` at `warrior_scanner_service.py:564`), so `Data Explorer > Warrior Scans` shows no `price` column data for old DBs, and fresh deployments that already have the column work fine.

**Fix direction:** Add an `ALTER TABLE` migration or use SQLAlchemy's `create_all()` column-add detection.

**Open question:** Does `create_all()` at `telemetry_db.py:197` already handle adding new columns to existing tables? (Typically it does NOT for SQLite — it only creates tables that don't exist yet.)

---

### Fact 3: Stale `max_price` test assertion (1 test failure)

**File:** [test_warrior_integration.py:34](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/tests/integration/test_warrior_integration.py#L34)
**Code:**
```python
assert settings.max_price == Decimal("20.0")
```

**Actual default:** `WarriorScanSettings.max_price = Decimal("40.0")` at [warrior_scanner_service.py:120](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py#L120).

**Confirmation:** The unit test at `test_warrior_scanner.py:47` already correctly asserts `Decimal("40.0")`. Only the integration test is stale.

**Fix:** Update test assertion to `Decimal("40.0")`.

---

### Fact 4: Stale `mental_stop` test assertion (1 test failure)

**File:** [test_warrior_integration.py:128](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/tests/integration/test_warrior_integration.py#L128)
**Code:**
```python
# Mental stop should be entry - 50 cents (updated default)
assert positions[0].mental_stop == Decimal("4.50")
```

**Actual behavior:** `WarriorMonitorSettings.session_exit_mode` defaults to `"base_hit"` ([warrior_types.py:127](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_types.py#L127)). In `base_hit` mode, `_create_new_position` (warrior_monitor.py:408) uses `base_hit_stop_cents = Decimal("15")` ([warrior_types.py:132](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_types.py#L132)). So:

```
mental_stop = entry_price - base_hit_stop_cents / 100
mental_stop = Decimal("5.00") - Decimal("15") / 100
mental_stop = Decimal("5.00") - Decimal("0.15")
mental_stop = Decimal("4.85")
```

**Additionally:** The test calls `add_position` without `support_level`, so no technical stop is computed. With `use_candle_low_stop` enabled (default), the code falls through to `current_stop = mental_stop` at line 428.

**Fix:** Update test assertion to `Decimal("4.85")` and update the comment to reference `base_hit` mode.

---

## Open Questions (For Backend Planner to Investigate)

1. **Should Warrior have `min_dollar_volume`?** Is there any Warrior-specific use case for dollar volume filtering, or is this purely a NACbot field that was incorrectly referenced? (Hint: coordinator found zero references in `warrior_scanner_service.py`.)

2. **SQLite migration strategy for telemetry.db:** What's the best approach? Options include:
   - *(a)* `ALTER TABLE ADD COLUMN` at init time (checking if column exists first)
   - *(b)* Delete old `telemetry.db` and recreate (acceptable for telemetry data)
   - *(c)* Use Alembic for telemetry DB (overkill?)
   
   Check whether any other tables in `telemetry.db` have the same issue (`catalyst_audits`, `ai_comparisons`).

3. **Are there other stale tests?** Run `python -m pytest nexus2/tests/ -v --no-header` and identify all current failures. The testing agent found 7 but there may be more.

---

## Scope

The spec should cover:

| # | Issue | Type | Files Touched |
|---|-------|------|---------------|
| 1 | `min_dollar_volume` AttributeError | Code bug | `warrior_routes.py` |
| 2 | `price` column missing in old DBs | Schema migration | `telemetry_db.py` |
| 3 | `max_price` test stale | Test fix | `test_warrior_integration.py` |
| 4 | `mental_stop` test stale | Test fix | `test_warrior_integration.py` |

## Verification

After spec is written, the Backend Specialist should:
1. Apply all fixes
2. Run `cd nexus2; python -m pytest tests/ -v --no-header`
3. Confirm `GET /warrior/scanner/settings` returns valid JSON (no AttributeError)
4. Confirm telemetry writes succeed for fresh and pre-existing DBs
