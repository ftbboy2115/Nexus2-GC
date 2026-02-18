# Technical Spec: Test Failure Fixes

**Author:** Backend Planner  
**Date:** 2026-02-18  
**For:** Backend Specialist  
**Scope:** 4 issues causing 7 test failures across `warrior_routes.py`, `telemetry_db.py`, and `test_warrior_integration.py`

---

## A. Existing Pattern Analysis

| Pattern | Function | File | Lines | Key Details |
|---------|----------|------|-------|-------------|
| Scanner settings serialization | `get_warrior_scanner_settings()` | `warrior_routes.py` | 764–782 | Returns `dict` of `WarriorScanSettings` fields |
| DB init | `init_telemetry_db()` | `telemetry_db.py` | 195–198 | Uses `create_all()` — creates tables only, won't add columns to existing tables |
| Integration test assertions | `test_scanner_settings_defaults()` | `test_warrior_integration.py` | 22–35 | Asserts `WarriorScanSettings` defaults |
| Monitor position creation | `_create_new_position()` | `warrior_monitor.py` | 374–468 | Uses `base_hit_stop_cents` (15¢) in default `base_hit` mode |

---

## B. Change Surface Enumeration

| # | File | Change | Location | Template |
|---|------|--------|----------|----------|
| 1 | `warrior_routes.py` | Remove `min_dollar_volume` line | Line 781 | N/A — line removal |
| 2 | `telemetry_db.py` | Add `ALTER TABLE` migration in `init_telemetry_db()` | Lines 195–198 | SQLite `PRAGMA table_info` + `ALTER TABLE ADD COLUMN` |
| 3 | `test_warrior_integration.py` | Update `max_price` assertion | Line 34 | Unit test at `test_warrior_scanner.py:47` |
| 4 | `test_warrior_integration.py` | Update `mental_stop` assertion + comment | Lines 127–128 | Calculation from `_create_new_position()` |

---

## C. Detailed Change Specifications

### Change Point #1: Remove `min_dollar_volume` from Warrior scanner settings endpoint

**What:** Remove reference to a field that only exists on NACbot's `ScannerSettings`, not on `WarriorScanSettings`

**File:** [warrior_routes.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_routes.py)

**Location:** `get_warrior_scanner_settings()`, line 781

**Current Code:**
```python
    return {
        "max_float": s.max_float,
        "ideal_float": s.ideal_float,
        "min_rvol": float(s.min_rvol),
        "ideal_rvol": float(s.ideal_rvol),
        "min_gap": float(s.min_gap),
        "ideal_gap": float(s.ideal_gap),
        "min_price": float(s.min_price),
        "max_price": float(s.max_price),
        "require_catalyst": s.require_catalyst,
        "exclude_chinese_stocks": s.exclude_chinese_stocks,
        "min_dollar_volume": float(s.min_dollar_volume),  # ← REMOVE THIS LINE
    }
```

**Approach:** Delete line 781 entirely. `WarriorScanSettings` (defined at `warrior_scanner_service.py:85-167`) has **no `min_dollar_volume` field**. This field exists only on the NACbot's `ScannerSettings` at `scanner_settings.py:35`. Zero references to `dollar_volume` exist in `warrior_scanner_service.py` (verified via `grep_search`).

**Verified with:** `grep_search("dollar_volume", "nexus2/domain/scanner/warrior_scanner_service.py")` → 0 matches

> [!NOTE]
> Warrior uses Ross Cameron's 5 Pillars (float, RVOL, catalyst, price, gap) — dollar volume is not one of them.

---

### Change Point #2: Add SQLite column migration for telemetry DB

**What:** Add `ALTER TABLE ADD COLUMN` migration so existing `telemetry.db` files get the new extended columns

**File:** [telemetry_db.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/db/telemetry_db.py)

**Location:** `init_telemetry_db()`, lines 195–202

**Current Code:**
```python
def init_telemetry_db():
    """Initialize Telemetry database tables."""
    TelemetryBase.metadata.create_all(bind=telemetry_engine)
    print(f"[Telemetry DB] Initialized at {TELEMETRY_DB_PATH}")


# Auto-initialize on import
init_telemetry_db()
```

**Problem:** `create_all()` creates missing **tables** but does NOT add missing **columns** to existing tables. When `telemetry.db` was created before the extended columns (`price`, `country`, `ema_200`, etc.) were added at lines 54-61, any INSERT referencing those columns raises `OperationalError: no such column`.

**Approach:** After `create_all()`, query `PRAGMA table_info(warrior_scan_results)` to get existing column names, then `ALTER TABLE warrior_scan_results ADD COLUMN <name> <type>` for any missing columns.

The columns to migrate for `warrior_scan_results` are:

| Column | SQLAlchemy Type | SQLite Type |
|--------|----------------|-------------|
| `price` | `Float` | `REAL` |
| `country` | `String(10)` | `VARCHAR(10)` |
| `ema_200` | `Float` | `REAL` |
| `room_to_ema_pct` | `Float` | `REAL` |
| `is_etb` | `String(5)` | `VARCHAR(5)` |
| `name` | `String(100)` | `VARCHAR(100)` |

**Template approach (pattern for implementer):**

```python
def _migrate_telemetry_columns():
    """Add missing columns to existing telemetry tables (SQLite migration)."""
    import sqlite3
    conn = sqlite3.connect(str(TELEMETRY_DB_PATH))
    cursor = conn.cursor()
    
    # Define expected columns and their SQLite types
    expected_columns = {
        "warrior_scan_results": {
            "price": "REAL",
            "country": "VARCHAR(10)",
            "ema_200": "REAL",
            "room_to_ema_pct": "REAL",
            "is_etb": "VARCHAR(5)",
            "name": "VARCHAR(100)",
        }
    }
    
    for table, columns in expected_columns.items():
        # Get existing columns
        cursor.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in cursor.fetchall()}
        
        # Add missing columns
        for col_name, col_type in columns.items():
            if col_name not in existing:
                try:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
                    print(f"[Telemetry DB] Added column {table}.{col_name}")
                except Exception as e:
                    print(f"[Telemetry DB] Column migration failed for {table}.{col_name}: {e}")
    
    conn.commit()
    conn.close()
```

Call `_migrate_telemetry_columns()` **after** `create_all()` inside `init_telemetry_db()`.

> [!IMPORTANT]
> Check if `catalyst_audits` and `ai_comparisons` tables also have migration issues. Looking at the model definitions (`telemetry_db.py:116-173`), these tables have **no extended columns** — they only have their original columns. No migration needed for them.

---

### Change Point #3: Update `max_price` test assertion

**What:** Fix stale assertion that expects `Decimal("20.0")` instead of the current default `Decimal("40.0")`

**File:** [test_warrior_integration.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/tests/integration/test_warrior_integration.py)

**Location:** `TestWarriorScannerIntegration.test_scanner_settings_defaults()`, line 34

**Current Code:**
```python
assert settings.max_price == Decimal("20.0")
```

**Actual default:** `max_price: Decimal = Decimal("40.0")` at [warrior_scanner_service.py:120](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py#L120)

**Verified with:** `view_file` of `warrior_scanner_service.py` line 120 shows `max_price: Decimal = Decimal("40.0")  # Editable in settings`

**Fix:**
```python
assert settings.max_price == Decimal("40.0")
```

---

### Change Point #4: Update `mental_stop` test assertion

**What:** Fix stale assertion that expects `Decimal("4.50")` instead of the correct `Decimal("4.85")` (base_hit mode with 15¢ stop)

**File:** [test_warrior_integration.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/tests/integration/test_warrior_integration.py)

**Location:** `TestWarriorMonitorIntegration.test_monitor_position_tracking()`, lines 127–128

**Current Code:**
```python
# Mental stop should be entry - 50 cents (updated default)
assert positions[0].mental_stop == Decimal("4.50")
```

**Root cause chain:**
1. `add_position()` is called without `support_level` → at [warrior_monitor.py:255–264](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor.py#L255-L264), defaults to `support_level=None`
2. No existing position → calls `_create_new_position()` at line 285
3. `session_exit_mode` defaults to `"base_hit"` → at [warrior_types.py:127](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_types.py#L127)
4. In `base_hit` mode → at [warrior_monitor.py:408-409](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor.py#L408-L409):
   ```python
   if exit_mode == "base_hit":
       mental_stop = entry_price - s.base_hit_stop_cents / 100
   ```
5. `base_hit_stop_cents = Decimal("15")` → at [warrior_types.py:132](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_types.py#L132)
6. Calculation: `Decimal("5.00") - Decimal("15") / 100 = Decimal("5.00") - Decimal("0.15") = Decimal("4.85")`
7. No `support_level` → `use_candle_low_stop` falls through to `current_stop = mental_stop` at line 428

**Fix:**
```python
# Mental stop should be entry - 15 cents (base_hit mode default)
assert positions[0].mental_stop == Decimal("4.85")
```

---

## D. Wiring Checklist

- [ ] Remove `"min_dollar_volume"` line from `warrior_routes.py:781`
- [ ] Add `_migrate_telemetry_columns()` function to `telemetry_db.py`
- [ ] Call migration function after `create_all()` in `init_telemetry_db()`
- [ ] Update `test_warrior_integration.py:34` — `max_price` assertion from `"20.0"` to `"40.0"`
- [ ] Update `test_warrior_integration.py:127-128` — `mental_stop` assertion from `"4.50"` to `"4.85"` and comment from "50 cents" to "15 cents (base_hit mode)"
- [ ] Run full test suite: `cd nexus2; python -m pytest tests/ -v --no-header`
- [ ] Verify `GET /warrior/scanner/settings` returns valid JSON (no AttributeError)
- [ ] Verify telemetry writes succeed for pre-existing DB (test with old `telemetry.db`)

---

## E. Risk Assessment

### What could go wrong
1. **SQLite migration edge case:** If `telemetry.db` table doesn't exist at all, `PRAGMA table_info` returns empty. This is fine — `create_all()` creates the table WITH the new columns, so the migration loop simply finds no missing columns.
2. **Column type mismatch:** `ALTER TABLE ADD COLUMN` in SQLite always adds nullable columns. All extended columns are `nullable=True`, so this is safe. No default values needed.
3. **Concurrent access:** `init_telemetry_db()` runs at import time (line 202). If multiple processes import simultaneously, the `ALTER TABLE` might fail on the second process. Each `ALTER TABLE` is wrapped in a try/except, so this is safe.

### What existing behavior might break
- **Nothing.** All 4 changes are either line removals, migration additions, or test assertion updates. No production logic is altered.

### What to test after implementation
1. Run `python -m pytest nexus2/tests/ -v --no-header` — all 7 previously-failing tests should pass
2. Delete `data/telemetry.db` → restart → verify it gets created with all columns
3. Create a "pre-migration" DB (table without extended columns) → restart → verify columns are added
4. Hit `GET /warrior/scanner/settings` → verify response has no `min_dollar_volume` key and no error

---

## F. Additional Findings

### No other stale tests discovered during investigation

The 4 issues account for all 7 known test failures:
- **Issue 1** (`min_dollar_volume`): 2 failures (any test that calls `get_warrior_scanner_settings()`)
- **Issue 2** (`price` column): 3 failures (tests that trigger scanner telemetry writes)
- **Issue 3** (`max_price`): 1 failure
- **Issue 4** (`mental_stop`): 1 failure

The full test suite should be run after fixes to catch any additional failures not identified in the original testing agent report.
