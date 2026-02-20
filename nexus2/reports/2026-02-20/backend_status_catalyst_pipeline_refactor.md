# Backend Status: Catalyst Pipeline Refactor

**Date:** 2026-02-20
**File:** `nexus2/domain/scanner/warrior_scanner_service.py`
**Result:** ✅ ALL CHANGES COMPLETE

---

## Changes Implemented

### Change 1: `always_run_ai_comparison` setting
- **Line:** 148 (after `enable_multi_model_comparison`)
- **What:** Added `always_run_ai_comparison: bool = True` to `WarriorScanSettings`
- **Purpose:** Kill switch for parallel AI comparison if rate limits become a problem

### Change 2: Calendar check moved to TOP of `_evaluate_catalyst_pillar`
- **Lines:** 1317-1347 (was at L1403-1415 as fallback)
- **What:**
  - Calendar (`has_recent_earnings`) now runs FIRST, before regex
  - Removed `if not ctx.has_catalyst:` guard — calendar always runs unconditionally
  - Added `CatalystAudit` DB write for calendar resolutions with `source="calendar"`, `confidence="calendar"`
- **Effect:** Calendar-resolved symbols now appear in Data Explorer's Catalyst Audits tab

### Change 3: Removed AI short-circuit in `_run_multi_model_catalyst_validation`
- **3a** (L1446): Removed HeadlineCache early `return` — cached symbols continue processing new headlines for comparison data
- **3b** (L1453): Changed gate from `not ctx.has_catalyst` to `(not ctx.has_catalyst or s.always_run_ai_comparison)` — AI runs even when regex/calendar already resolved
- **3c** (L1499): Removed `break` after first valid headline — all headlines (up to 3) now processed for comparison data

### Import added
- **Line 35:** Added `CatalystAudit` to the import from `nexus2.db.telemetry_db`

---

## DO NOT TOUCH (confirmed untouched)
- `_run_legacy_ai_fallback` — no changes
- `ai_catalyst_validator.py` — no changes
- `telemetry_db.py` — no changes
- Former runner logic — kept as-is

---

## Verification

| Check | Result |
|-------|--------|
| Import check | ✅ `python -c "from nexus2.domain.scanner.warrior_scanner_service import WarriorScannerService; print('OK')"` → OK |
| Test suite | ✅ 757 passed, 4 skipped, 3 deselected in 115.94s |

---

## Testable Claims

| # | Claim | File:Line | Grep Pattern |
|---|-------|-----------|--------------|
| 1 | `always_run_ai_comparison` setting exists | `warrior_scanner_service.py:148` | `always_run_ai_comparison` |
| 2 | Calendar check is first in `_evaluate_catalyst_pillar` | `warrior_scanner_service.py:1317` | `has_recent_earnings` |
| 3 | CatalystAudit DB write for calendar | `warrior_scanner_service.py:1331-1341` | `db.add(CatalystAudit(` |
| 4 | HeadlineCache no longer has early return | `warrior_scanner_service.py:1446` | `No early return` |
| 5 | Main gate uses `always_run_ai_comparison` | `warrior_scanner_service.py:1453` | `s.always_run_ai_comparison` |
| 6 | No `break` after first valid headline | `warrior_scanner_service.py:1499` | `No break` |
