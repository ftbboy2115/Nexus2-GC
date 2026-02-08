# Wave 2 Test Report

**Date:** 2026-02-08  
**Author:** Testing Specialist (Antigravity)  
**Scope:** Automated tests for Wave 1 changes

---

## Summary

| Test Area | File | Tests | Result |
|-----------|------|-------|--------|
| ET→UTC Date Filters | `tests/api/test_data_routes.py` | 7 | ✅ 7 passed |
| Mock Market Notes | `tests/api/test_warrior_notes.py` | 9 | ✅ 9 passed |
| Scanner Caching | `tests/test_scanner_cache.py` | 6 | ✅ 6 passed |
| **Total** | | **22** | **✅ 22 passed** |

---

## Test Area 1: ET→UTC Date Filter Conversion

**Class:** `TestDateFilterETConversion` (added to existing `test_data_routes.py`)

| Test | Status |
|------|--------|
| `test_warrior_trades_date_filter_accepts_dates` | ✅ PASS |
| `test_nac_trades_date_filter_accepts_dates` | ✅ PASS |
| `test_quote_audits_date_filter_accepts_dates` | ✅ PASS |
| `test_warrior_trades_invalid_date_raises_error` | ✅ PASS |
| `test_warrior_trades_single_date_filter` | ✅ PASS |
| `test_nac_trades_single_date_filter` | ✅ PASS |
| `test_quote_audits_single_date_filter` | ✅ PASS |

---

## Test Area 2: Mock Market Notes Endpoints

**File:** `tests/api/test_warrior_notes.py` (new)

| Test | Status |
|------|--------|
| `test_get_notes_returns_200` | ✅ PASS |
| `test_get_notes_missing_case_returns_empty` | ✅ PASS |
| `test_put_notes_saves_and_retrieves` | ✅ PASS |
| `test_put_notes_overwrites_existing` | ✅ PASS |
| `test_global_notepad_roundtrip` | ✅ PASS |
| `test_put_test_case_notes_rejects_invalid_field` | ✅ PASS |
| `test_put_test_case_notes_rejects_missing_case` | ✅ PASS |
| `test_put_test_case_notes_accepts_notes_field` | ✅ PASS |
| `test_put_test_case_notes_accepts_description_field` | ✅ PASS |

---

## Test Area 3: Scanner Caching

**File:** `tests/test_scanner_cache.py` (new)

| Test | Status |
|------|--------|
| `test_cached_returns_fresh_value` | ✅ PASS |
| `test_cached_returns_cached_on_second_call` | ✅ PASS |
| `test_cached_expires_after_ttl` | ✅ PASS |
| `test_cached_different_keys_independent` | ✅ PASS |
| `test_cached_stores_none_values` | ✅ PASS |
| `test_cache_starts_empty` | ✅ PASS |

---

## Bug Found

### Invalid Date Parameter Handling

- **Location:** `nexus2/api/routes/data_routes.py` (lines ~910-920)
- **Severity:** Low
- **Expected:** Invalid `date_from`/`date_to` values (e.g., `not-a-date`) should return 400 or be ignored
- **Actual:** Unhandled `ValueError` from `strptime` causes 500 Internal Server Error
- **Strategy:** Warrior / all Data Explorer endpoints
- **Evidence:** `test_warrior_trades_invalid_date_raises_error` captures `ValueError`
- **Recommendation:** Wrap `strptime` calls in try/except, return 400 or skip the filter

---

## Run Commands

```powershell
# Scanner cache tests
python -m pytest nexus2/tests/test_scanner_cache.py -v --timeout=30

# Mock Market notes tests
python -m pytest nexus2/tests/api/test_warrior_notes.py -v --timeout=30

# Date filter tests
python -m pytest nexus2/tests/api/test_data_routes.py::TestDateFilterETConversion -v --timeout=30

# All Wave 2 tests
python -m pytest nexus2/tests/api/test_data_routes.py::TestDateFilterETConversion nexus2/tests/api/test_warrior_notes.py nexus2/tests/test_scanner_cache.py -v --timeout=30
```
