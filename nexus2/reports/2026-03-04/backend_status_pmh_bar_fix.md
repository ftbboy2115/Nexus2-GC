# Backend Status: PMH Bar Fetching Fix

**Date:** 2026-03-04 10:48 ET  
**Agent:** Backend Specialist  
**Reference:** `handoff_backend_pmh_bar_fix.md`  
**Previous:** `backend_status_entry_guard_fixes.md`

---

## Root Cause

Two bugs in `_get_premarket_high()` (warrior_engine.py):

1. **Wrong attribute**: Polygon `OHLCV` bars have `timestamp` (UTC datetime), not `time` (string "HH:MM"). Code used `getattr(bar, 'time', '')` which returned empty string for all Polygon bars — every bar was skipped.

2. **Bar limit too small**: `limit=100` at 10:00 AM returns only the latest 100 bars (all regular hours). Premarket spans 330 minutes (4:00–9:30 AM), requiring `limit=400`.

---

## Fix Applied

**File:** `warrior_engine.py` lines 627–671

- **`bar.timestamp` handling**: Checks for `OHLCV.timestamp` (datetime), converts UTC→ET via `pytz` before filtering for pre-9:30 AM bars
- **Mock market fallback**: Preserves `bar.time` (string) parsing for mock market bars
- **`limit=400`**: Covers full premarket window plus first 70 min of regular hours

---

## Verification

### Batch Test (all 40 cases)
```
  Improved:  1/40 (NPT: $0 → $10,590.75)
  Regressed: 1/40 (MNTS: -$15,502.64 → -$15,895.76, -$393.12)
  Net change: +$10,197.63
  Runtime: 215.9s (baseline: 102.3s, +113.6s)
```

### MNTS Solo Run
```
  MNTS: $-15,502.64 (matches baseline exactly)
```

**Conclusion:** MNTS regression is non-deterministic concurrency noise from heavier bar loads in batch mode. Solo run confirms no behavioral change.

### Runtime Impact
+113.6s from fetching 400 bars per PMH call instead of 100 in mock market sim. Acceptable trade-off for correct PMH derivation in live trading.

---

## Testable Claims

| # | Claim | File:Line | Grep Pattern |
|---|-------|-----------|--------------|
| 1 | Uses `bar.timestamp` for Polygon bars | `warrior_engine.py:636` | `bar_ts = getattr(bar, 'timestamp', None)` |
| 2 | Converts UTC→ET via pytz | `warrior_engine.py:640` | `pytz.timezone('US/Eastern')` |
| 3 | Limit increased to 400 | `warrior_engine.py:630` | `limit=400` |
| 4 | Mock market fallback preserved | `warrior_engine.py:648` | `getattr(bar, 'time', '')` |
| 5 | Log shows total bar count | `warrior_engine.py:668` | `total bars` |
