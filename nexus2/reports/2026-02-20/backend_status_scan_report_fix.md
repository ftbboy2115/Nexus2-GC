# Backend Status: Scan Report Format String Fix

**Date:** 2026-02-20
**Test:** `TestScannerSummaryReport.test_full_scan_report`
**File:** `nexus2/tests/test_scanner_validation.py`

## Root Cause

A YAML test case had `ross_pnl:` with no value, which Python's YAML parser loads as `None`. The code used `tc.get('ross_pnl', 0)` — but `dict.get()` only returns the default when the key is **missing**. Since the key existed with value `None`, the default `0` was never used, and the `:,.0f` format specifier raised `TypeError: unsupported format string passed to NoneType.__format__`.

## Fix

Changed 3 occurrences of `tc.get('ross_pnl', 0)` → `(tc.get('ross_pnl') or 0)` which coalesces both missing keys and explicit `None` values to `0`.

| Line | Context |
|------|---------|
| 285  | `test_known_winners_pass` print statement |
| 527  | `test_full_scan_report` passed section |
| 540  | `test_full_scan_report` failed section |

## Verification

```
python -m pytest nexus2/tests/ -x -q
757 passed, 4 skipped, 3 deselected in 163.38s
```

All tests pass. No regressions.
