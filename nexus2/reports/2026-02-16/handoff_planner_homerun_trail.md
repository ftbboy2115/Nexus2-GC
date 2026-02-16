# Handoff: Backend Planner — Home Run Trail Audit & Improvement Spec

**Date:** 2026-02-16  
**From:** Coordinator  
**To:** Backend Planner (`@agent-backend-planner.md`)

---

## Context

Fix 1 (partial-then-ride) doubled our P&L by selling 50% at the base_hit target and switching the remaining 50% to `home_run` trailing mode via `exit_mode_override = "home_run"`.

**The problem:** The home_run trailing stop in `_check_home_run_exit` appears to exit the remainder too early, leaving significant P&L on the table. Even with Fix 1's ride, we're still capturing only ~26% of Ross's P&L at equivalent sizing.

Key examples (scaled to $2K risk for apples-to-apples):
- **ROLR**: $49K vs Ross's $85K (57.8% capture — not bad but room to improve)
- **NPT**: $14K vs Ross's $81K (17.1% — the home_run trail is exiting way too early)
- **GRI**: $4.3K vs Ross's $31.6K (13.5% — massive gap)

---

## Your Task: Deep Audit of `_check_home_run_exit`

### 1. Map the Current Logic (INVESTIGATE FROM SCRATCH)

Research the actual code in `nexus2/domain/automation/warrior_monitor_exit.py`:

- What trailing method does `_check_home_run_exit` use?
- What are the current trailing parameters? (R-multiple thresholds, partial targets, trail widths)
- How does it tighten the trail as the trade progresses?
- How does it interact with `home_run_partial_at_r` and the partial exit within home_run mode?
- When Fix 1 sends a position here (after the base_hit partial), does the home_run code treat it differently? Or does it not know it came from a partial?

### 2. Analyze Why It Exits Too Early

For the test cases where we have trades that reach home_run mode, why does the trail close the position when there's still significant upside?

Possible causes:
- Trail is too tight (candle-level trailing on a volatile stock)
- Trail tightens too quickly (moves to breakeven → tightens further)
- No awareness of the stock's momentum or R-multiple growth
- Partial exit within home_run fires too early or at wrong level

### 3. Research: How Does Ross Trail Home Runs?

Reference the existing research:
- `nexus2/reports/2026-02-16/research_homerun_scaling_methodology.md`

Key Ross behaviors to model:
- Holds through multi-dollar moves (not exiting on 10¢ pullbacks)
- Trails at structural levels or key intraday lows
- Uses wider trail on bigger moves (trail doesn't tighten as the stock runs)

### 4. Propose Improvements

Design a Fix 4 with A/B toggle. Possible approaches:
- **R-multiple-based trail width**: at 2R use 1R trail, at 4R use 2R trail (trail widens with profit)
- **Structural level trailing**: trail to the last whole/half dollar level instead of candle lows
- **Time-based trail widening**: first 5 min use tight trail, after 10 min use wider trail
- **Momentum-aware trail**: don't tighten if volume is expanding

---

## Expected Deliverable

Write a technical spec to:  
`nexus2/reports/2026-02-16/spec_homerun_trail_improvement.md`

Include:
- A. Current `_check_home_run_exit` logic mapped (all parameters, flow, decision points)
- B. Analysis of why the trail exits too early (with evidence from code)
- C. Proposed improvement with A/B toggle
- D. Change surface and detailed specs
- E. Risk assessment
