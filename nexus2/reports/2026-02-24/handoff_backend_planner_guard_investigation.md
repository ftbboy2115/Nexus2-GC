# Handoff: Guard Effectiveness Investigation

**Date:** 2026-02-24
**From:** Coordinator
**To:** Backend Planner
**Priority:** P1 — $222K P&L gap (11 cases), largest single issue

---

## Context

GC batch diagnosis found GUARDBLOCKED is the #1 P&L issue:
- **11 cases** affected, ~$222K total gap
- Guard accuracy: 62.2% (1374 correct blocks, 835 missed opportunities)
- Net guard impact: -$1,363 (guards barely net-positive)
- Key cases: PAVM ($44K), HIND ($41K), LRHC ($30K) — all GUARDBLOCKED + STOPHIT

**Infrastructure already exists** (built Feb 23):
- `skip_guards` parameter for A/B batch testing
- `guard_analysis` field in sim results with per-guard breakdown
- `gc_batch_diagnose.py` includes guard effectiveness output

---

## Verified Facts

**Guard functions** — `nexus2/domain/automation/warrior_entry_guards.py` (474 lines):
- `check_entry_guards()` — main entry point (L35-171), checks: top_x picks, min score, blacklist, fail limit, MACD gate, cooldowns
- `_check_macd_gate()` — blocks when MACD is negative (L174-226)
- `_check_position_guards()` — max scales, profit check, existing positions (L232-286)
- `_check_spread_filter()` — bid-ask spread check (L289-339)
- `validate_technicals()` — VWAP/EMA alignment (L347-473)

**A/B infrastructure** — `sim_context.py` + `warrior_sim_routes.py`:
- Run with guards: `POST /warrior/sim/run_batch_concurrent {"include_trades": true}`
- Run without guards: `POST /warrior/sim/run_batch_concurrent {"include_trades": true, "skip_guards": true}`

**Previous reports** (all in `nexus2/reports/2026-02-23/`):
- `spec_guard_effectiveness_analysis.md`
- `backend_status_guard_effectiveness.md`
- `spec_reentry_loss_guard_tuning.md`

---

## Your Tasks

### Task 1: Run skip_guards A/B test
Run two batch tests (use `http://127.0.0.1:8000`, NOT localhost):
```powershell
# With guards (baseline)
Invoke-RestMethod -Uri "http://127.0.0.1:8000/warrior/sim/run_batch_concurrent" -Method POST -ContentType "application/json" -Body '{"include_trades": true}' -TimeoutSec 120

# Without guards
Invoke-RestMethod -Uri "http://127.0.0.1:8000/warrior/sim/run_batch_concurrent" -Method POST -ContentType "application/json" -Body '{"include_trades": true, "skip_guards": true}' -TimeoutSec 120
```

Compare total P&L, capture rate, and per-case deltas. Identify which cases improve most without guards.

### Task 2: Identify worst guards
From the `guard_analysis` data in the with-guards run, identify:
1. Which guard types block the most profitable entries
2. Which guard has the worst accuracy (blocks entries that would have been profitable)
3. Per-guard P&L impact

### Task 3: Read the existing guard reports
Read the Feb 23 reports listed above. Build on their findings rather than duplicating.

### Task 4: Propose specific fixes
For the top 2-3 worst-performing guards, propose:
- Specific parameter changes (thresholds, timeouts, tolerances)
- How to A/B test each change independently
- Expected impact per case

**IMPORTANT:** All proposals must be grounded in Ross Cameron methodology. Read `.agent/strategies/warrior.md` before proposing changes. Do NOT invent thresholds.

---

## Output

Write your findings to: `nexus2/reports/2026-02-24/spec_guard_tuning_investigation.md`

Include:
1. Skip-guards A/B comparison table (with vs without)
2. Per-guard accuracy and impact analysis
3. Proposed fixes ranked by expected P&L impact
4. A/B test plan for each proposed fix
