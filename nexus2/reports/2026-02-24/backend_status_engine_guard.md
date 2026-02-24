# Backend Status: ALLOW_LIVE_ENGINE Guard

**Date:** 2026-02-24
**Agent:** Backend Specialist
**Status:** ✅ Complete
**Pytest:** 757 passed, 4 skipped, 3 deselected

---

## Summary

Added `ALLOW_LIVE_ENGINE` env var guard (default `false`, fail-closed) to prevent dual-instance live trading. All three engine start paths are now guarded. Sim routes are completely unaffected.

---

## Changes Made

### 1. `scheduler_routes.py` — NAC Scheduler Start Guard

- **File:** `nexus2/api/routes/scheduler_routes.py`
- **Line 10:** Added `import os`
- **Line 41:** Added module-level `ALLOW_LIVE_ENGINE = os.getenv("ALLOW_LIVE_ENGINE", "false").lower() == "true"`
- **Lines 56-62:** Added guard check at top of `start_scheduler()` → returns 403 if not allowed

### 2. `warrior_routes.py` — Warrior Engine Start Guard

- **File:** `nexus2/api/routes/warrior_routes.py`
- **Lines 381-388:** Added inline guard in `start_warrior_engine()` → returns 403 if not allowed

### 3. `main.py` — Startup Logging + Auto-Start Guards

- **File:** `nexus2/api/main.py`
- **Lines 139-147:** Added startup log showing `ALLOW_LIVE_ENGINE` state (warning if true, info if false)
- **Lines 203-206:** Warrior auto-start blocked if `allow_live=false`
- **Lines 264-266:** NAC scheduler auto-resume blocked if `allow_live=false`

### 4. Test Updates

- **File:** `nexus2/tests/api/test_scheduler_routes.py:70` — Accept 403 from guard
- **File:** `nexus2/tests/api/test_warrior_routes.py:92-97` — Accept 403 from guard
- **File:** `nexus2/tests/api/test_warrior_routes.py:117-125` — Conditional assert for guard

---

## Testable Claims

| # | Claim | File:Line | How to Verify |
|---|-------|-----------|---------------|
| 1 | `ALLOW_LIVE_ENGINE` defaults to `false` (fail-closed) | `scheduler_routes.py:41` | `Select-String -Path "nexus2\api\routes\scheduler_routes.py" -Pattern "ALLOW_LIVE_ENGINE"` |
| 2 | `start_scheduler()` returns 403 when guard is false | `scheduler_routes.py:56-62` | `curl -X POST http://localhost:8000/automation/scheduler/start` without env var |
| 3 | `start_warrior_engine()` returns 403 when guard is false | `warrior_routes.py:381-388` | `curl -X POST http://localhost:8000/warrior/start` without env var |
| 4 | Startup log shows ALLOW_LIVE_ENGINE state | `main.py:139-147` | Check server.log for `ALLOW_LIVE_ENGINE` on startup |
| 5 | Warrior auto-start is blocked when guard is false | `main.py:203-206` | Check startup output for `Warrior auto-start BLOCKED` |
| 6 | NAC scheduler auto-resume is blocked when guard is false | `main.py:264-266` | Check startup output for `NAC scheduler auto-resume BLOCKED` |
| 7 | Sim routes work regardless of guard state | `warrior_sim_routes.py` | No guard code in sim routes — `POST /warrior/sim/*` always works |
| 8 | All pytest pass | — | `python -m pytest nexus2/tests/ -q` → 757 passed |

---

## VPS Deployment Note

To enable on VPS/production, add to `.env`:
```
ALLOW_LIVE_ENGINE=true
```

Without this, neither `POST /warrior/start` nor `POST /automation/scheduler/start` will succeed, and auto-start on reboot is also blocked.
