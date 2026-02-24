# Handoff: Add Live Engine Safety Guard

**Date:** 2026-02-24
**From:** Coordinator
**To:** Backend Specialist
**Priority:** P1 — Safety

---

## Context

Both VPS (production) and local (development) run the same Nexus server. If the Warrior Engine Control (scanner → entry → orders) starts on both instances simultaneously, duplicate orders would be sent to Alpaca. Sim/batch testing must still work locally.

---

## Task

Add an environment variable guard that prevents the live engine from starting unless explicitly enabled.

### Implementation

1. **Add to `.env.example` and document:**
```
ALLOW_LIVE_ENGINE=false  # Set to true only on VPS/production
```

2. **Guard the engine start endpoint** (find the POST route that starts the warrior engine — likely in `warrior_routes.py` or a scheduler route):
```python
import os

ALLOW_LIVE_ENGINE = os.getenv("ALLOW_LIVE_ENGINE", "false").lower() == "true"

# At the top of the engine start handler:
if not ALLOW_LIVE_ENGINE:
    raise HTTPException(
        status_code=403,
        detail="Live engine disabled on this instance. Set ALLOW_LIVE_ENGINE=true in .env to enable."
    )
```

3. **Do NOT guard sim routes** — `POST /warrior/sim/*` must remain unaffected.

4. **Log a warning on startup** if `ALLOW_LIVE_ENGINE=true` so it's visible in logs:
```python
if ALLOW_LIVE_ENGINE:
    logger.warning("⚠️ ALLOW_LIVE_ENGINE=true — this instance CAN start the live trading engine")
else:
    logger.info("ALLOW_LIVE_ENGINE=false — live engine start is disabled (sim still works)")
```

### Key Requirements
- **Fail-closed**: if env var is missing or unset, engine CANNOT start
- **Sim unaffected**: all `/warrior/sim/*` routes work regardless
- **Clear error message**: if someone tries to start engine locally, they see why it's blocked

---

## Verification

1. Without `ALLOW_LIVE_ENGINE` in `.env`: engine start returns 403
2. With `ALLOW_LIVE_ENGINE=false`: engine start returns 403
3. With `ALLOW_LIVE_ENGINE=true`: engine starts normally
4. Sim batch test works in all configurations
5. pytest passes

Write status to: `nexus2/reports/2026-02-24/backend_status_engine_guard.md`
