# Audit Validator Handoff: VCIG EMA + Health Metrics Claims

**Date:** 2026-03-04 11:48 ET  
**From:** Coordinator  
**To:** Audit Validator  
**Source:** `nexus2/reports/2026-03-04/research_vcig_ema_health.md`  
**Output:** `nexus2/reports/2026-03-04/validation_vcig_ema_health.md`

---

## Claims to Verify

### Claim 1: Bar Reversal Bug
**Planner says:** `_get_200_ema` (line 1195-1196 in warrior_scanner_service.py) assumes Polygon bars are newest-first and reverses them, but Polygon returns `sort: "asc"` (oldest-first). The reversal computes EMA backward.

**Verify:**
- Does the code reverse bars at that line?
- What sort order does Polygon actually return? Check the adapter call.
- Would this produce an absurdly high EMA for VCIG?

### Claim 2: Health Metrics Are Display-Only
**Planner says:** `compute_position_health` is ONLY called from the `/positions/health` API endpoint. The entry engine never checks health metrics.

**Verify:**
- Search for all callers of `compute_position_health`
- Search for any reference to `position_health`, `health`, `room_to_ema` in the entry path
- Is there ANY health check before entry?

### Claim 3: No Sanity Checks on EMA
**Planner says:** Zero validation on EMA values anywhere in the pipeline.

**Verify:**
- Search for any bounds checking on `ema_200` values
- Is there any `if ema > X` or ratio check?

### Claim 4: Scanner Gate Passes Absurd EMA
**Planner says:** `_check_200_ema` paradoxically PASSES a $665K EMA because -99.998% room is interpreted as "lots of room below the ceiling."

**Verify:**
- Read the `_check_200_ema` function logic
- Confirm that -99.998% room_to_ema would pass the gate
- What is the actual threshold check?
