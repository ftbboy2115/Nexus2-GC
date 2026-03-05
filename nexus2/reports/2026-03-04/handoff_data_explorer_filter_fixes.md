# Data Explorer Multi-Select Filter Fixes

## Problem

Multi-select filters in the Data Explorer are broken across multiple tabs. When a user unchecks values in a filter dropdown, the frontend sends the **remaining selected values** as comma-separated query params. But most backend endpoints use equality checks (`== value`) instead of `IN` clause, so they treat `"ENTRY_TRIGGERED,EXIT_STOP"` as a single string literal — matching nothing.

**User-reported symptoms:**
1. Trade Events: Excluding any `event_type` shows no entries
2. Trade Events: Unchecking "already holding" from `reason` doesn't filter

---

## Root Cause (Verified)

### How filtering works

1. **Frontend** (`data-explorer.tsx:288-293`): Iterates `filters` state → sends each column's selected values as comma-separated query params: `?event_type=ENTRY_TRIGGERED,EXIT_STOP`
2. **Backend**: Each tab endpoint receives these as `Optional[str]` params and must split + filter

### The bug: inconsistent backend handling

| Endpoint | Filter Method | Multi-select? |
|----------|--------------|---------------|
| `warrior-scans` | `apply_generic_filters()` | ✅ Yes — splits commas, uses `IN` |
| `catalyst-audits` | `apply_generic_filters()` | ✅ Yes |
| `ai-comparisons` | `apply_generic_filters()` | ✅ Yes |
| **trade-events** | **Manual `== event_type`** | ❌ **Broken** |
| **warrior-trades** | **Manual `== status`, etc.** | ❌ **Broken** |
| **nac-trades** | **Manual `== status`, etc.** | ❌ **Broken** |
| **quote-audits** | **Manual `== symbol`, etc.** | ❌ **Broken** |
| **validation-log** | **Manual `== symbol`, etc.** | ❌ **Broken** |
| `nac-scans` (scan-history) | Manual Python list filter | ❌ **Broken** |

### Additional bug: missing `reason` param on trade-events

The trade-events endpoint (`data_routes.py:752-766`) only declares: `strategy`, `symbol`, `event_type`, `date_from`, `date_to`, `time_from`, `time_to`, `created_at`.

**There is no `reason` parameter.** When the frontend sends `reason=...`, FastAPI silently ignores it.

---

## Proposed Fix (Backend Only)

### Strategy

Migrate all manual equality checks to use the existing `apply_generic_filters()` function (already working for warrior-scans, catalyst-audits, ai-comparisons). This function handles:
- Single values: `"US"` → `col = 'US'`
- Multi-select: `"US,CN"` → `col IN ('US', 'CN')`
- NULL: `"(empty)"` → `col IS NULL`
- Range: `">=5"` → `col >= 5`

### Changes per endpoint

#### 1. Trade Events (`get_trade_events`, line 752)
- **Problem**: In-memory Python filtering, not SQLAlchemy
- **Fix**: Convert `event_type` filter to support comma-separated: split + `in` check
- **Add**: `reason` as a new `Optional[str]` query parameter with same comma-split logic
- Since this endpoint uses in-memory Python dicts (not SQLAlchemy), create a helper like:
  ```python
  def _apply_multi_select(entries, column, filter_value):
      if not filter_value: return entries
      value_set = {v.strip() for v in filter_value.split(',')}
      has_empty = '(empty)' in value_set
      value_set.discard('(empty)')
      return [e for e in entries if str(e.get(column, '') or '') in value_set 
              or (has_empty and not e.get(column))]
  ```

#### 2. Warrior Trades (`get_warrior_trades`, line 876)
- **Problem**: Lines 907-952 use manual `== value` for: `status`, `symbol`, `exit_reason`, `trigger_type`, `quote_source`, `exit_mode`, `stop_method`, `is_sim`, `partial_taken`
- **Fix**: Replace with `apply_generic_filters()` for string columns. Keep boolean handling for `is_sim`, `partial_taken`.

#### 3. NAC Trades (`get_nac_trades`, line 125)
- **Problem**: Lines 161-179 use manual `== value` for: `status`, `symbol`, `exit_reason`, `setup_type`
- **Fix**: Replace with `apply_generic_filters()`

#### 4. Quote Audits (`get_quote_audits`, line 1047)
- **Problem**: Lines 1079-1095 use manual `== value` for: `symbol`, `time_window`, `selected_source`
- **Fix**: Replace with `apply_generic_filters()`

#### 5. Validation Log (`get_validation_log`, line 1168)
- **Problem**: Lines 1198-1208 use manual `== value` for: `symbol`, `entry_trigger`, `target_hit`
- **Fix**: Replace with `apply_generic_filters()` for string columns, keep boolean for `target_hit`

#### 6. NAC Scans / Scan History (`get_scan_history`, line 232)
- **Problem**: In-memory Python filtering, same issue as trade-events
- **Fix**: Use the same `_apply_multi_select` helper for `symbol`, `source`, `catalyst`

---

## Open Questions

1. Should `symbol` filtering still `upper()` the value? `apply_generic_filters` doesn't do case normalization. May need case-insensitive handling.
2. Boolean columns (`is_sim`, `partial_taken`, `target_hit`, `high_divergence`) need special handling — `apply_generic_filters` treats everything as strings. Keep manual boolean logic for these.

---

## Verification Plan

### Automated Tests
- Existing tests at `nexus2/tests/api/test_data_routes.py` — run with:
  ```powershell
  cd nexus2; python -m pytest tests/api/test_data_routes.py -v
  ```
- Add new test cases for multi-select filtering (comma-separated values) on each endpoint

### Manual Browser Verification
1. Navigate to Data Explorer → Trade Events tab
2. Click filter dropdown on `event_type` column
3. Uncheck one value (e.g., leave 3 of 4 types checked)
4. Verify table shows only the checked event types
5. Repeat for `reason` column
6. Test same behavior on Warrior Trades, NAC Trades, Quote Audits, Validation Log tabs

---

## Files to Modify

| File | Type | Description |
|------|------|-------------|
| `nexus2/api/routes/data_routes.py` | MODIFY | Fix all 6 endpoints to support multi-select |
| `nexus2/tests/api/test_data_routes.py` | MODIFY | Add multi-select filter tests |
