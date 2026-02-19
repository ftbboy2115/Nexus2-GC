> **Rule version:** 2026-02-19T07:01:00

---
trigger: always_on
---

## Architecture & Planning Mode

When in this mode, focus on architecture and planning — NOT implementation code (except small illustrative snippets).

Focus areas:
- Domain modeling and bounded contexts
- Module boundaries and responsibilities
- Sequence and data-flow diagrams
- API contract design
- Identifying invariants and constraints
- Ensuring trading architecture aligns with the relevant strategy (see `.agent/strategies/`)

Architecture must cleanly separate: Scanner logic, Setup detection, Risk engine, Order lifecycle, SIM vs LIVE.

### Process
1. Restate the task and identify affected bounded contexts.
2. Ask clarifying questions to avoid assumptions.
3. Propose 2–3 architectural options with pros/cons and a recommendation.
4. Produce: architecture sketch, sequence diagrams, data-flow diagrams, API contracts.
5. Confirm alignment with relevant strategy methodology.
6. Request approval from Clay before implementation begins.