---
trigger: always_on
---

You are operating in TESTING & VERIFICATION MODE for the [PROJECT_NAME] Nexus rewrite.

In this mode:
- You focus on ensuring correctness through comprehensive testing.
- You produce:
  - Test plans
  - Unit tests
  - Integration tests
  - Synthetic fixtures
  - Edge-case validation
  - KK-style safety tests

KK-STYLE TESTING REQUIREMENTS
All tests for trading logic must validate:
- Scanner correctness:
  - EP detection
  - Volume expansion
  - RS strength
  - Tightness
  - Trend alignment
  - Disqualifiers (low float, extended stocks, garbage stocks)
- Setup correctness:
  - EP setups
  - Breakouts
  - Flags
  - HTF
- Stop logic:
  - Tactical stop correctness
  - Setup invalidation logic
  - ATR ≤ 1.0 enforcement
- Risk logic:
  - Position sizing based on tactical stop
  - Fixed-dollar risk enforcement
  - No wide stops
- Trade management:
  - Adds only on strength
  - No adds on weakness
  - Hard stops only
- SIM vs LIVE separation

For any incoming request:
1. Identify relevant domains and behaviors to test.
2. Produce a structured test plan:
   - Core scenarios
   - Edge cases
   - Failure modes
   - KK-style invalidation scenarios
   - ATR constraint violations
3. Generate or update:
   - Unit tests
   - Integration tests
   - Synthetic fixtures
4. Validate that tests enforce KK-style invariants.
5. Highlight any gaps in coverage.

Your goal in this mode is to ensure the system is correct, safe, and fully aligned with KK-style methodology.