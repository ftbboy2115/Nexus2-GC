# Handoff: Backend Specialist — Scanner Settings Persistence

**Date:** 2026-02-22
**From:** Coordinator
**To:** Backend Specialist (`@agent-backend-specialist.md`)

---

## Objective

Verify and fix scanner settings persistence so that RVOL changes via the API survive server restarts.

## Context

- The scanner architecture spec is at `nexus2/reports/2026-02-21/spec_dual_scanner_architecture.md` (Section 2.3)
- `WarriorScanSettings` (in `warrior_scanner_service.py`, lines 86-168) has `min_rvol = Decimal("2.0")` as default
- `PUT /warrior/scanner/settings` updates `min_rvol` at runtime (warrior_routes.py, lines 797-815)
- **Open question:** Does the PUT endpoint persist changes to disk, or are they lost on restart?

## Tasks

### 1. Verify Persistence (Required)

Test whether scanner settings persist:
1. Call `GET /warrior/scanner/settings` — note current `min_rvol`
2. Call `PUT /warrior/scanner/settings` with `{ "min_rvol": 1.5 }`
3. Check how the engine stores this — does it write to `warrior_settings.py` / a JSON config / or only in-memory?
4. If in-memory only, this is a gap that needs fixing

### 2. Wire Persistence if Missing (Conditional)

If settings don't persist:
- Check how `warrior_settings.py` handles engine config persistence (the existing pattern)
- Add scanner settings to the same persistence mechanism
- Ensure `min_rvol` (and other scanner settings) survive restarts

### 3. Do NOT Change Default

- The default `min_rvol` stays at `2.0` 
- We are only making it configurable + persistent, not changing behavior

## Deliverable

- Any modified files committed
- Status report: `nexus2/reports/2026-02-22/backend_status_scanner_persistence.md`
  - Must include: evidence of persistence test (commands run + output)
  - Must include: list of files modified (if any)
