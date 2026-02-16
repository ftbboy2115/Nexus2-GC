# Handoff: Backend Planner — Fix 2: Price-Proportional Trail Activation Spec

**Date:** 2026-02-16  
**From:** Coordinator  
**To:** Backend Planner (`@agent-backend-planner.md`)

---

## Context

The current candle trail activation threshold is a **fixed +15¢** (`base_hit_trail_activation_cents=15`). This works well for $3-5 stocks but is too tight for $8-15 stocks (15¢ on a $10 stock = 1.5% — trivially small, triggers too early).

This is **Fix 2** of 5 iterative A/B tests. Fix 1 (partial-then-ride) has been disabled for isolated testing.

### Completed Reports (READ FIRST)
1. `nexus2/reports/2026-02-16/audit_exit_logic_leakage.md` — Finding #5: fixed 15¢ cap
2. `nexus2/reports/2026-02-16/research_homerun_scaling_methodology.md` — Ross uses structural levels

---

## Verified Facts

1. **Trail activation at `warrior_types.py:127`**: `base_hit_trail_activation_cents: Decimal = Decimal("15")`
2. **Used at `warrior_monitor_exit.py:708`**: `activation_cents = s.base_hit_trail_activation_cents`
3. **Comparison at line 711**: `if position.candle_trail_stop is None and profit_cents >= activation_cents`
4. **Flat fallback at `warrior_types.py:122`**: `base_hit_profit_cents: Decimal = Decimal("18")` — also fixed

---

## Open Questions (INVESTIGATE FROM SCRATCH)

1. **What formula should replace the fixed 15¢?** The coordinator suggests `max(15, entry_price * 3)` (i.e., 3% of entry price in cents, minimum 15¢). But is 3% the right percentage? Check what values this produces across the test case price range.

2. **Should the flat fallback (+18¢) also be proportional?** Currently `base_hit_profit_cents=18` — should this also scale with price?

3. **How does this interact with the candle trail lookback?** Trail uses 2-bar low. If the activation threshold is higher, it takes longer to activate — does the 2-bar lookback still make sense?

4. **What are the entry prices across all 29 test cases?** Calculate what the proportional threshold would produce for each case to sanity-check.

5. **Config toggle approach**: Should this be a simple bool `enable_proportional_trail: bool = False`, or should it replace the `base_hit_trail_activation_cents` field with a `trail_activation_percent: float = 3.0` field?

6. **Does `warrior_monitor_settings.py` need updates for persistence?**

---

## Expected Deliverable

Write a technical spec to:  
`nexus2/reports/2026-02-16/spec_proportional_trail.md`

Include:
- A. Price analysis across all 29 test cases (what threshold each would get)
- B. Complete change surface enumeration
- C. Detailed change specs with current code at each change point
- D. Wiring checklist
- E. Risk assessment
