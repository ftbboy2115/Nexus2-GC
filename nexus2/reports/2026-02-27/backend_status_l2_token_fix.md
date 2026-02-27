# Backend Status: L2 Token Bridge Fix

**Date:** 2026-02-27  
**Agent:** Backend Specialist  
**Task:** Fix L2 token bridge 401 Unauthorized error  
**Reference:** `handoff_backend_l2_token_fix.md`  
**Status:** ✅ COMPLETE

## Root Cause

The Schwab developer app only had **Market Data Production** API access. L2 streaming requires **Trader API** (specifically `GET /trader/v1/userPreference`), which was not enabled.

**Evidence:** Direct HTTP test with same access token:
- `GET /marketdata/v1/quotes` → 200 ✅
- `GET /trader/v1/accountNumbers` → 401 ❌
- `GET /trader/v1/userPreference` → 401 ❌

**Resolution:** Enabled "Accounts and Trading Production" on Schwab developer portal + re-authenticated. All endpoints now return 200.

## Code Changes (3 commits)

### Commit `c58c95b` — Pre-flight + retry + diagnostics
- **File:** `nexus2/adapters/market_data/schwab_l2_streamer.py`
- Added diagnostic logging to `_build_schwab_py_token()` (masked token, expiry, creation_ts)
- Added `_preflight_check()` — validates token via `/trader/v1/accounts/accountNumbers`
- Added retry logic in `start()` — retries once on 401

### Commit `5e60f69` — Forced token refresh
- Added `_force_token_refresh()` — forces authlib refresh when pre-flight gets 401
- Handles case where REST adapter refreshes token but on-disk copy is stale

### Commit `b277689` — expires_at falsiness bug
- Fixed `expires_at=0` → `expires_at=1` (Python `not 0` is `True`, silently skipping refresh)

## Testable Claims

1. Pre-flight check calls `get_account_numbers()` before streaming setup
2. On pre-flight 401, `_force_token_refresh()` sets `expires_at=1` and calls `ensure_active_token()`
3. `start()` retries once on 401 auth errors before failing
4. Diagnostic logging shows masked access token, expires_in, expiry_str, and creation_ts
5. `_token_write_func` writes refreshed tokens in Nexus format preserving `refresh_token_obtained`

## Verification

Tested on VPS (`root@100.113.178.7`):
```
[L2] Pre-flight token check passed
[L2] StreamClient connected and logged in
[L2] Streamer started successfully (attempt 1)
[L2] Subscribed to 1 symbols: ['AAPL'] (total: 1)
```
Received 4 NASDAQ_BOOK messages with real bid/ask data (AAPL @ ~$263.76).
