# Issues Found During Endpoint Migration Testing

## Bug: Warrior Scan Results Table Missing `price` Column

- **Location**: `db/telemetry_db.py` (model) vs actual `telemetry.db` table
- **Expected**: `warrior_scan_results` table should have columns matching the ORM model, including `price`, `country`, `ema_200`, `room_to_ema_pct`, `is_etb`, `name`
- **Actual**: Table is missing the `price` column (and likely others added recently)
- **Strategy**: Warrior
- **Evidence**: 
  ```
  sqlite3.OperationalError: no such column: warrior_scan_results.price
  [SQL: INSERT INTO warrior_scan_results (..., price, ...) VALUES (...)]
  ```
- **Impact**: 
  - 2 test failures: `test_warrior_scan_history_returns_200`, `test_warrior_scan_history_pagination`
  - Live scanner cannot persist scan results to DB (ERROR logs on every scan)
- **Root Cause**: ORM model was updated with new columns but DB schema was not migrated
- **Recommendation**: Run Alembic migration or manually add missing columns to `telemetry.db`

---

*Found: Feb 6, 2026 10:34 AM ET by Testing Specialist*
