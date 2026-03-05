# Backend Status: Bar Timestamp Fix

**Date:** 2026-03-04  
**File:** `nexus2/api/routes/warrior_callbacks.py`  
**Tests:** 24 passed, 0 failed

---

## Changes Made

### Bar dataclass (line 271)
Added `timestamp: object = None` field to preserve OHLCV timestamps through conversion.

### 4 conversion paths updated
All OHLCV→Bar conversions now include `timestamp=getattr(b, 'timestamp', None)`:

| # | Path | Line |
|---|------|------|
| 1 | Sim (HistoricalBarLoader) | ~289 |
| 2 | Polygon (primary) | ~322 |
| 3 | Alpaca (secondary) | ~342 |
| 4 | FMP (tertiary) | ~359 |

---

## Testable Claims

| # | Claim | File | Verification |
|---|-------|------|-------------|
| 1 | `Bar` dataclass has `timestamp` field | `warrior_callbacks.py:271` | `Select-String -Path "nexus2\api\routes\warrior_callbacks.py" -Pattern "timestamp"` |
| 2 | Polygon conversion preserves timestamp | `warrior_callbacks.py:322` | Same search, check Polygon block |
| 3 | Sim conversion preserves timestamp | `warrior_callbacks.py:289` | Same search, check sim block |
| 4 | Alpaca conversion preserves timestamp | `warrior_callbacks.py:342` | Same search, check Alpaca block |
| 5 | FMP conversion preserves timestamp | `warrior_callbacks.py:359` | Same search, check FMP block |
| 6 | All 24 existing tests pass | — | `python -m pytest nexus2/tests/unit/automation/test_warrior_engine.py -x -q` |
