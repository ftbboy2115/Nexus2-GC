# Handoff: Backend Planner — Early Rejection Logging Gap

**Date:** 2026-02-21
**From:** Coordinator
**To:** Backend Planner (`@agent-backend-planner.md`)
**Priority:** MEDIUM

---

## Objective

Research the entry trigger flow and spec where to add logging for early-stage rejections that currently aren't captured.

---

## Context

We just implemented guard block logging (commit `97edda1`). Guard blocks are now persisted to the `trade_events` DB via `log_warrior_guard_block()`. However, when running batch simulations, **early rejections are missing** — guard blocks only appear AFTER the first entry, not before.

**Why:** The guards (`check_entry_guards`) are only called when a pattern trigger fires AND scores above `MIN_SCORE_THRESHOLD`. For most of the simulated trading day, no trigger fires at all (price hasn't broken PMH, no pattern detected), so `check_entry_guards` is never called.

**The gap:** These pre-trigger decisions are not logged anywhere queryable:
- "Price below PMH, no pattern detected" — silent loop iteration
- "Pattern triggered but score below threshold" — `logger.info` only (line ~613-617 of `warrior_engine_entry.py`)
- "No candidates found this cycle" — silent

---

## Verified Facts

- Guard blocks are captured: `trade_event_service.py` → `log_warrior_guard_block()` → DB ✅
- Guard blocks only fire inside `enter_position()` which is called from `check_entry_triggers()` 
- `check_entry_triggers()` is in `warrior_engine_entry.py` (~lines 334-620)
- Below-threshold rejections are at lines ~613-617 (`logger.info` only, no DB write)

---

## Open Questions (Investigate These)

1. **What are ALL the decision points** in `check_entry_triggers()` where a "no entry" decision is made? Enumerate every path that results in NOT entering.
2. **What's the volume?** In a typical sim run (e.g., BATL with 960 bars), how many times would these decision points fire? Would logging every "no trigger" be too noisy?
3. **Where should logging be added?** Which decision points are valuable for analysis vs. noise?
4. **What event type should be used?** New constant like `TRIGGER_REJECTION`? Or reuse `GUARD_BLOCK` with a different guard name?
5. **Performance impact:** Would DB writes on every cycle slow down batch runs significantly? Should we throttle (e.g., only log first occurrence per symbol)?

---

## Suggested Approach

1. Trace ALL paths through `check_entry_triggers()` that result in "no entry"
2. Categorize them by value: HIGH (analyst wants to see this), MEDIUM, LOW (noise)
3. Propose which ones to log and with what event type/structure
4. Estimate DB write volume per typical sim run
5. Propose throttling strategy if volume is excessive

---

## Deliverable

Write a technical spec to: `nexus2/reports/2026-02-21/spec_early_rejection_logging.md`

The spec should include:
1. **Decision Point Inventory** — every "no entry" path with line numbers
2. **Categorization** — which are worth logging (HIGH/MEDIUM/LOW)
3. **Proposed Schema** — event type, metadata structure, throttling
4. **Volume Estimate** — expected DB writes per sim run
5. **Implementation Sketch** — which files to modify and how
