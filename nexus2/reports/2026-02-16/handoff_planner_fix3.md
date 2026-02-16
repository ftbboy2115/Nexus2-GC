# Handoff: Backend Planner — Fix 3: Structural Profit Levels Spec

**Date:** 2026-02-16  
**From:** Coordinator  
**To:** Backend Planner (`@agent-backend-planner.md`)

---

## Context

The current flat fallback profit target is a fixed +18¢ (`base_hit_profit_cents=18`). This is price-insensitive — $3 stocks and $15 stocks get the same target. More importantly, it doesn't align with how Ross Cameron actually takes profits: at **structural price levels** like whole dollars ($5, $6), half-dollars ($5.50), and quarter-dollars ($5.25).

This is **Fix 3** of 5 iterative A/B tests.

### Current State
- **Fix 1 (partial-then-ride): ENABLED** — +97% P&L improvement
- **Fix 2 (proportional trail): REJECTED** — -10% P&L, disabled
- Fix 3 will be tested **with Fix 1 enabled** (since it's proven)

### Background Reports (READ FIRST)
1. `nexus2/reports/2026-02-16/audit_exit_logic_leakage.md` — Finding about fixed targets
2. `nexus2/reports/2026-02-16/research_homerun_scaling_methodology.md` — Ross uses structural levels

---

## Verified Facts

1. **Flat fallback at `warrior_monitor_exit.py:~830`**: Currently computes `target_price = position.entry_price + effective_profit_cents / 100`
2. **The flat fallback is only used when candle trail is disabled or bars unavailable** (fallback path)
3. **The candle trail activation (not the fallback) is the primary profit-taking mechanism** — the fallback is secondary
4. **Fix 1's partial-then-ride fires on BOTH the trail stop hit AND the flat fallback** — both paths are active

---

## Open Questions (INVESTIGATE FROM SCRATCH)

1. **What structural levels should be used as profit targets?** 
   - Ross commonly exits at whole dollars ($5→$6), half-dollars ($5→$5.50), and sometimes quarters
   - The target should be the **next structural level above entry price**, not a fixed offset
   - Example: entry at $4.72 → next targets at $5.00 (28¢), $5.50 (78¢), $6.00 ($1.28)
   - Which level should be the base_hit target? The nearest one? Or should we require a minimum distance?

2. **Minimum distance requirement?** If entry is $4.97, the next whole dollar is only $0.03 away — that's too close. Should we skip to the next level if the distance is below some threshold (e.g., 10¢)?

3. **Which levels to use?** Options:
   - A) Whole + half only ($0.50 increments)
   - B) Whole + half + quarter ($0.25 increments)  
   - C) Just whole dollars ($1.00 increments)
   - Ross tends to use $0.50 increments most often

4. **Where does this logic live?** Currently `_check_base_hit_target` uses the flat fallback. Should the structural level replace:
   - Just the flat fallback target?
   - Also the trail activation threshold?
   - Or should it be a standalone check before the trail/fallback logic?

5. **Config toggle approach**: How to make this A/B testable?
   - `enable_structural_levels: bool = True`?
   - `structural_level_increment: float = 0.50`?

6. **Interaction with Fix 1**: When Fix 1 fires a partial exit at the structural level, the remainder switches to home_run trailing. Does the structural level need to be communicated to the home_run mode?

---

## Expected Deliverable

Write a technical spec to:  
`nexus2/reports/2026-02-16/spec_structural_levels.md`

Include:
- A. Analysis of what structural levels each test case would produce (like the Fix 2 price analysis)
- B. Complete change surface enumeration
- C. Detailed change specs
- D. Wiring checklist
- E. Risk assessment
