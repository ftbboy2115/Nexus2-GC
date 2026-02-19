> **Rule version:** 2026-02-19T07:01:00

---
trigger: always_on
---

## Trading Logic & Safety Review Mode

When in this mode, enforce strict adherence to documented trading methodology across all logic: scanner, setup, entry, stop, risk, position sizing, trade management.

> [!CAUTION]
> All trading rules must come from `.agent/strategies/`. Do NOT invent thresholds or rules.

### Review Checklist
For any trading-related request:

1. **Identify strategy** — Which strategy file applies? (Warrior, KK, Algo)
2. **Validate against methodology** — Does the logic match documented rules?
3. **Check stop hierarchy** — Correct stop type, correct sizing basis?
4. **Verify risk logic** — Position sizing from tactical stop, ATR constraints met?
5. **Assess trade management** — Adds on strength only? Hard stops? No averaging down?
6. **Check SIM vs LIVE** — Strictly separated?

### Failure Modes to Watch
- Incorrect stops or oversized positions
- Invalid setups passing filters
- Extended stocks not disqualified
- SIM/LIVE contamination

### Approval Gate
Do not approve or finalize any trading logic until:
- All strategy-documented rules are satisfied
- All invariants hold
- Tests exist and cover edge cases

Goal: Ensure all trading logic is safe, correct, and aligned with the documented strategy.