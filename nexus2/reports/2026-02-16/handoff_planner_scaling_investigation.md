# Handoff: Backend Planner — Scaling Logic Investigation

**Date:** 2026-02-16  
**From:** Coordinator  
**To:** Backend Planner (`@agent-backend-planner.md`)

---

## Context

We assumed the bot had no scaling/add-on logic — **this is wrong.** Full scaling logic exists:

- **`warrior_monitor_scale.py`** — Contains `check_scale_opportunity()` and `execute_scale_in()`
- **`warrior_types.py`** — Config fields: `max_scale_count=2`, `scale_size_pct=50`, `min_rvol_for_scale=2.0`, `allow_scale_below_entry=True`
- **`warrior_types.py`** — Position tracking: `scale_count=0`, `last_scale_attempt=None`

**The problem:** In batch testing (29 cases), NO scaling ever occurs. Every trade shows a single entry with no adds. This means the scaling logic exists but is never triggered.

---

## Your Task: Investigate Why Scaling Doesn't Fire

### 1. Map the Scale Opportunity Detection

Read `warrior_monitor_scale.py` thoroughly and document:
- What conditions must be met for `check_scale_opportunity` to return a signal?
- What are all the guard conditions (max_scale_count, cooldown, stop buffer, recovery grace, pullback zone, RVOL)?
- Which guards are most likely blocking in simulation?

### 2. Find Where Scaling Is Called

Search the codebase to find where `check_scale_opportunity` is called:
- Is it called in the monitor loop?
- Is it called in the sim engine?
- Is it **wired at all** in the simulation path vs only in live trading?

> [!CAUTION]  
> This is the most likely root cause — the scaling logic may exist but never be called in simulation mode.

### 3. Analyze the Scale Conditions vs Test Cases

For our best winners (ROLR, NPT, BATL 1/27):
- Would the RVOL condition (2x) be met?
- Would the pullback zone condition be met?
- Would the stop buffer condition block it?
- Is the cooldown timer realistic for simulation?

### 4. Propose a Fix

If scaling is not wired in sim, propose how to wire it.  
If scaling guards are too strict, identify which guards to relax.  
If scaling is wired but blocked, explain exactly why.

---

## Expected Deliverable

Write findings to:  
`nexus2/reports/2026-02-16/investigation_scaling_not_triggering.md`

Include:
- A. Full scale opportunity logic mapped (all guards + conditions)
- B. Where `check_scale_opportunity` is called (or NOT called)
- C. Root cause analysis
- D. Proposed fix
