---
trigger: always_on
---

## Testing & Verification Mode

When in this mode, focus on ensuring correctness through comprehensive testing.

Outputs:
- Test plans, unit tests, integration tests
- Synthetic fixtures and edge-case validation
- Strategy-specific safety tests

For trading logic tests, reference the relevant strategy file in `.agent/strategies/` to validate against documented methodology.

### Process
1. Identify relevant domains and behaviors to test.
2. Produce a structured test plan: core scenarios, edge cases, failure modes, strategy invalidation scenarios.
3. Generate or update: unit tests, integration tests, synthetic fixtures.
4. Validate that tests enforce strategy invariants.
5. Highlight any gaps in coverage.

Goal: Ensure the system is correct, safe, and fully aligned with documented strategy methodology.