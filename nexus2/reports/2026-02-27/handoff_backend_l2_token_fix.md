# Handoff: Backend Specialist — L2 Token Bridge Fix

## Bug
L2 streamer gets `401 Unauthorized` from Schwab API (`/trader/v1/userPreference`) despite valid tokens.

## Verified Facts

**Tokens are valid** (verified on VPS at 16:28 ET):
- Access token expiry: `2026-02-27T16:33:26` (was valid at connection time 16:25)
- Refresh token obtained: `2026-02-22T21:04:55` (5 days ago, within 7-day window)

**Error log** (from VPS `server.log`):
```
16:25:51.222 | INFO  | [L2] Created schwab-py async client
16:25:51.513 | ERROR | [L2] Failed to start streamer: Client error '401 Unauthorized' for url 'https://api.schwabapi.com/trader/v1/userPreference'
```

**Existing REST adapter works fine** with these same tokens — only the L2 streamer fails.

## Root Cause Hypothesis
The `_build_schwab_py_token()` method in `schwab_l2_streamer.py` bridges from Nexus token format to schwab-py format. schwab-py's `client_from_access_functions` likely expects additional fields beyond just `access_token` and `refresh_token`:
- `token_type` (should be `"Bearer"`)
- `scope` (should be `"api"`)
- `expires_in` (seconds)
- `expires_at` (epoch timestamp)

## Open Questions — Investigate
1. Read `schwab_l2_streamer.py:_build_schwab_py_token()` — what fields does it currently set?
2. Read `schwab/auth.py:client_from_access_functions` — what does it expect?
3. Compare with what the existing `schwab_adapter.py` does for auth (it uses raw httpx, not schwab-py)
4. Check if schwab-py tries to refresh the token and the refresh is what fails (vs the initial access)

## Fix
Update `_build_schwab_py_token()` to include all required fields. Test by running:
```bash
ssh root@100.113.178.7 "cd ~/Nexus2 && .venv/bin/python -c 'import asyncio; from nexus2.adapters.market_data.schwab_l2_streamer import SchwabL2Streamer; s=SchwabL2Streamer(); asyncio.run(s.start()); print(s.is_connected)'"
```

## Important
- Use `C:\Dev\Nexus` for search tools
- After fixing, commit and push, then redeploy: `ssh root@100.113.178.7 "cd ~/Nexus2 && git pull && systemctl restart nexus2"`
- The Schwab access token refreshes every 30 min — so test promptly after fixing
