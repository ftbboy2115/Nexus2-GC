# Handoff: Trade Management Diagnostic — Where WB Loses Money vs Ross

**Agent:** Backend Planner
**Priority:** P1 — trade management is the biggest P&L improvement opportunity
**Date:** 2026-02-25

---

## Context

WB captures $155K from 35 test cases where Ross captured $433K — a **-$277K delta** (35.9% capture rate). With 10s price stepping now active, simulation is closer to live. The entry logic is working (28 of 35 winners), but the money is being left on the table in:

- **Stop management** — premature stop-outs from 10s price noise Ross would hold through
- **Exit timing** — Ross holds runners longer, takes partial profits strategically
- **Scaling decisions** — Ross adds at the right moments; WB may miss opportunities

## Objective

Understand what telemetry/diagnostic data already exists in the system, and where the gaps are. We need a diagnostic tool that shows **per-trade: what WB did vs what Ross did** — specifically around exits, stops, and adds.

## Open Questions (Investigate)

### 1. What telemetry tables exist in Data Explorer?
- What data is already captured per trade? (entry time, exit time, P&L, stop events, scaling events)
- Where does this data live? (nexus.db? telemetry.db? sim-specific tables?)
- What does the Trade Management Log capture?

### 2. What does a batch test produce per-case?
- Beyond total P&L, what per-trade data is in the batch result JSON?
- Are individual entry/exit timestamps recorded?
- Are stop events (stop hit, stop adjusted, trailing stop moved) logged?
- Are scaling events (adds, partial exits) logged?

### 3. What does the Ross test case data tell us?
- Each `ross_*.json` file — does it include Ross's actual trades (entries, exits, adds)?
- Can we compute Ross's per-trade timing (held for X minutes, added at Y price)?
- Is there a `trades` or `positions` section in the test case files?

### 4. Where exactly is WB losing?
- For the 3 biggest losers in the 10s sweep (NPT, ROLR, EVMN):
  - When did WB enter vs when did Ross enter?
  - When/why did WB exit vs when did Ross exit?
  - Did WB get stopped out that Ross held through?
  - Did Ross scale in where WB didn't?

### 5. What diagnostic script would be most useful?
- A per-trade comparison: WB entry/exit/P&L vs Ross entry/exit/P&L
- A stop event timeline: when was stop hit, was it premature?
- A scaling opportunity analysis: where could WB have added but didn't?

## Suggested Research Approach

1. Look at the sim batch result format (what comes back from `/warrior/sim/run_batch_concurrent`)
2. Look at Data Explorer's telemetry tables (trade_management_log, sim entries)
3. Look at the ross_*.json test case files to understand what Ross trade data is available
4. Look at `gc_batch_diagnose.py` — what diagnostics already exist?
5. Propose a diagnostic script that answers: "For each case, why did WB make $X vs Ross's $Y?"

## Output

Write findings to: `nexus2/reports/2026-02-25/spec_trade_management_diagnostic.md`

Include:
- Inventory of existing telemetry/diagnostic data
- Gaps that need to be filled
- Proposed diagnostic script design
- Sample analysis for 1-2 cases showing WB vs Ross trade timeline
