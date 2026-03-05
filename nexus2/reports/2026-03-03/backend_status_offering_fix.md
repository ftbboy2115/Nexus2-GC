# Backend Status: Offering False-Positive Fix

**Date:** 2026-03-03 16:47 ET  
**Author:** Backend Specialist  
**Handoff:** `nexus2/reports/2026-03-03/handoff_backend_offering_fix.md`

---

## Summary

Fixed the NPT false-positive rejection caused by two compounding bugs. NPT now passes scanner evaluation and produces **+$10,590.75** in batch testing. Zero regressions across 39 other test cases.

---

## Changes Made

### Bug 1: Finviz Date Filtering (P0) ✅

**Files:** `news_sources.py`, `unified.py`

Added `days` parameter to `get_finviz_headlines()` and applied date filtering using the existing `Date` column in the Finviz DataFrame. Previously, Finviz returned headlines from any date—months-old IPO announcements triggered negative catalyst rejection.

| File | Change | Lines |
|------|--------|-------|
| [news_sources.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/market_data/news_sources.py#L60-L105) | Added `days` param, date filtering with `pd.to_datetime`, timezone handling | L60-105 |
| [unified.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/market_data/unified.py#L924) | Pass `days=days` to `get_finviz_headlines()` | L924 |

### Bug 2: IPO Regex Exclusion (P0) ✅

**File:** `catalyst_classifier.py`

Added IPO exclusion check before negative pattern matching. If a headline contains "initial public offering" or "ipo", the negative patterns are skipped entirely, allowing the positive `ipo` pattern to match instead.

| File | Change | Lines |
|------|--------|-------|
| [catalyst_classifier.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/catalyst_classifier.py#L232-L247) | Added `is_ipo_headline` guard before negative pattern loop | L232-247 |

### Bug 3: AI Tiebreaker — NOT IMPLEMENTED (per instructions)

Deferred as follow-up per handoff scope note.

### Observability: Negative Catalyst Audit Logging ✅

**File:** `warrior_scanner_service.py`

Added `log_headline_evaluation()` call for negative catalyst rejections. Previously only PASS results were logged, making it impossible to diagnose false negatives.

| File | Change | Lines |
|------|--------|-------|
| [warrior_scanner_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py#L1429-L1430) | Added `log_headline_evaluation` for FAIL | L1429-1430 |

---

## Verification Results

### Unit Tests ✅
```
python -m pytest nexus2/tests/unit/automation/test_catalyst_classifier.py -v
15 passed in 0.83s
```

### Batch Test ✅
```
python scripts/gc_quick_test.py --all --diff

Improved:  1/40
Regressed: 0/40
Unchanged: 39/40
Net change:  $+10,590.75
New total P&L: $365,629.41  (Ross: $454,718.05)
Capture: 80.4%  (Fidelity: 48.7%)

Case                           |      Old P&L |      New P&L |       Change
ross_npt_20260303              | $      0.00 | $ 10,590.75 | $+10,590.75
```

### Scanner Pulse Check
Not run (NPT is today's date and Finviz may return different headlines now). The batch test serves as definitive proof—NPT went from $0 (rejected) to $10,590.75 (accepted and traded profitably).

---

## Testable Claims (for Testing Specialist)

1. **`news_sources.py:60`** — `get_finviz_headlines()` now accepts `days` parameter and filters by date
   - Grep: `Select-String -Path "nexus2\adapters\market_data\news_sources.py" -Pattern "days: int = 5"`
   
2. **`catalyst_classifier.py:232-237`** — IPO headlines skip negative pattern loop
   - Grep: `Select-String -Path "nexus2\domain\automation\catalyst_classifier.py" -Pattern "is_ipo_headline"`
   
3. **`catalyst_classifier.py`** — "Announces Closing of $9.5 Million Initial Public Offering" classifies as positive `ipo`, not negative `offering`
   
4. **`warrior_scanner_service.py:1429`** — Negative catalyst rejections now call `log_headline_evaluation`
   - Grep: `Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern "log_headline_evaluation.*FAIL.*negative"`
