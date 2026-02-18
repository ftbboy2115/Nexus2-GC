---
trigger: always_on
---

## Implementation & Refactoring Mode

When in this mode, architecture and API contracts are assumed to be already defined.

Focus areas:
- Backend implementation (FastAPI, domain modules, migrations)
- Frontend implementation (Next.js, React, TypeScript)
- Writing and updating tests
- Safe refactoring
- Enforcing trading logic per the relevant strategy (see `.agent/strategies/`)

### Process
1. Validate that architecture and contracts are clear.
2. Propose a step-by-step implementation or refactor plan.
3. Implement code in clean, modular, production-ready chunks.
4. Include or update: unit tests, integration tests, migrations, documentation.
5. Perform a self-review: correctness, invariants, observability (logs, metrics).

Goal: Produce clean, correct, strategy-aligned, production-ready code.