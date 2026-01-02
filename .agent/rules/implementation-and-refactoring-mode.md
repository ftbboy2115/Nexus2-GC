---
trigger: always_on
---

You are operating in IMPLEMENTATION & REFACTORING MODE for the [PROJECT_NAME] Nexus rewrite.

In this mode:
- You assume architecture and API contracts are already defined.
- You focus on:
  - Backend implementation (FastAPI, domain modules, migrations)
  - Frontend implementation (Next.js, React, TypeScript)
  - Writing and updating tests
  - Safe refactoring
  - Enforcing KK-style trading logic where applicable

KK-STYLE IMPLEMENTATION REQUIREMENTS
- All trading logic must follow:
  - KK-style scanner criteria (EP, volume expansion, RS strength, tightness, trend alignment)
  - KK-style setup definitions (EP, breakouts, flags, HTF)
  - KK-style stop hierarchy:
    - Tactical stop = opening range low or flag low
    - Setup invalidation = EP candle low
    - ATR ≤ 1.0 for valid trades
  - KK-style risk logic:
    - Position sizing based on tactical stop
    - Fixed-dollar risk per trade
    - No wide stops, no averaging down
  - KK-style trade management:
    - Add only on strength
    - No adds on weakness
    - Hard stops only
    - SIM and LIVE must remain strictly separated

For any incoming request:
1. Validate that architecture and contracts are clear.
2. Propose a step-by-step implementation or refactor plan.
3. Implement code in clean, modular, production-ready chunks.
4. Include or update:
   - Unit tests
   - Integration tests
   - Migrations
   - Documentation for complex KK-style logic
5. Perform a self-review:
   - Validate correctness and invariants
   - Ensure KK-style rules are followed
   - Ensure observability (logs, metrics)

Your goal in this mode is to produce clean, correct, KK-aligned, production-ready code.