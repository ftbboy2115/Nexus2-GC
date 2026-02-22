# Handoff: Frontend Specialist — RVOL Slider

**Date:** 2026-02-22
**From:** Coordinator
**To:** Frontend Specialist (`@agent-frontend-specialist.md`)

---

## Objective

Add an RVOL threshold slider/input to the Warrior dashboard's Scanner Settings card.

## Context

- The backend API already supports RVOL configuration:
  - `GET /warrior/scanner/settings` — returns current `min_rvol`
  - `PUT /warrior/scanner/settings` — accepts `{ "min_rvol": 1.5 }` (Optional[float])
- The scanner architecture spec is at `nexus2/reports/2026-02-21/spec_dual_scanner_architecture.md` (Section 2.3 for RVOL details)
- **Default value: 2.0x** — do NOT change the default
- Ross Cameron's published ideal is 5x, but he trades momentum plays with lower RVOL

## Implementation

1. Find the Scanner Settings card in `warrior.tsx` (or the relevant settings component)
2. Add an RVOL input control (slider or number input with step 0.1, range 0.5–10.0)
3. Label: "Min Relative Volume"
4. Tooltip: "Minimum RVOL threshold for scanner candidates. Ross's ideal is 5x. Lower values (1.5x) catch news-driven momentum with less volume confirmation. Default: 2.0x"
5. Wire to `PUT /warrior/scanner/settings` on change
6. Load current value from `GET /warrior/scanner/settings` on mount

## Design Guidelines

- Match the existing UI pattern of other scanner settings controls (check what's already there)
- Use the existing color scheme and component library
- Include the current value display next to the slider (e.g., "2.0x")

## Deliverable

- Modified frontend files
- Status report: `nexus2/reports/2026-02-22/frontend_status_rvol_slider.md`
