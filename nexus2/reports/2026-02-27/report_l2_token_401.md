# L2 Token Bridge 401 — Root Cause Report

**Date:** 2026-02-27  
**Status:** Root cause identified — requires Schwab portal action

## Root Cause

The Schwab developer app **only has Market Data API access**, not Trader API access. schwab-py's streaming setup calls `GET /trader/v1/userPreference`, which requires Trader API permissions.

### Evidence

Direct test on VPS with the same access token:

| Endpoint | Status | API Product |
|---|---|---|
| `GET /marketdata/v1/quotes` | **200 OK** ✅ | Market Data |
| `GET /trader/v1/accounts/accountNumbers` | **401** ❌ | Trader |
| `GET /trader/v1/userPreference` | **401** ❌ | Trader |

- Token refresh works fine (POST to `/v1/oauth/token` → 200)
- Fresh tokens ALSO get 401 from Trader endpoints
- Market Data endpoints work perfectly with the same token

## Required Action

> [!IMPORTANT]
> Enable **Trader API** access on the Schwab developer app at [developer.schwab.com](https://developer.schwab.com).

1. Log into the Schwab developer portal
2. Navigate to your app configuration
3. Enable the **"Trader API — Individual"** product (in addition to Market Data)
4. Wait for approval (may take a few days)
5. Once approved, L2 streaming should work with the existing code

## Code Improvements Made (3 commits)

While investigating, several robustness improvements were committed:

1. **Diagnostic logging** in `_build_schwab_py_token()` — logs masked token, expiry, and creation timestamp
2. **Pre-flight token check** (`_preflight_check()`) — validates token via `get_account_numbers()` before streaming setup, with clear error messages
3. **Forced token refresh** (`_force_token_refresh()`) — when pre-flight gets 401, forces authlib to refresh by setting `expires_at=1` (set to 1, not 0, because `not 0` is `True` in Python which silently skips the refresh)
4. **Retry logic** in `start()` — retries once on 401 auth errors with fresh token
5. **Token write-back** — refreshed tokens are written to disk in Nexus format for the REST adapter

These improvements will be useful once Trader API access is enabled — the pre-flight check will catch token issues early and the forced refresh handles the case where the REST adapter races ahead.

## Commits

- `c58c95b` — Pre-flight check + retry logic + diagnostic logging
- `5e60f69` — Forced token refresh on 401
- `b277689` — Fix `expires_at=0` Python falsiness bug
