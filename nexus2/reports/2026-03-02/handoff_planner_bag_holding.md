# Research Handoff: Bag Holding / Stop Failure

**Agent:** Backend Planner
**Date:** 2026-03-02
**Priority:** CRITICAL — This is the #1 profitability blocker.

## Context

Entry quality analysis on the 5 worst batch test cases revealed that the biggest P&L drag isn't bad entries — it's **positions held to EOD without stops firing** ("bag holding"). Two cases show this pattern:

### Evidence

**MNTS 2026-02-09** (Delta: -$24K):
- Entry: 08:00:20 at $7.80 via `whole_half_anticipatory`
- Exit: **19:30** at **$6.14** via **`after_hours_exit`**
- Loss: **-$15,503** on 9,314 shares
- The stock fell from $7.80 to $6.14 (21% decline) over 11 hours without the stop firing
- Ross made +$9K on the same stock

**HIND 2026-01-27** (trade 1):
- Entry: 12:15 at $3.63 via `hod_break`
- Exit: **19:30** at **$3.63** via **`after_hours_exit`**
- P&L: $0 — entered and held flat to EOD close

## Open Questions (Investigate)

1. **Why didn't the mental stop fire on MNTS?** The entry was at $7.80. What was the stop price? When did the price first breach the stop? Did the stop check run at that time?

2. **Were there UNREALIZED PROFITS that were missed?** (MFE Analysis)
   - For each bag-held trade (MNTS entry $7.80, HIND entry $3.63), what was the **highest price** the stock reached after entry?
   - If MNTS went to $9.00 before falling to $6.14, the issue isn't just a stop failure — it's also a **missed profit-taking** opportunity.
   - Check the bar data: what was the MFE (Maximum Favorable Excursion) for each after_hours_exit trade?
   - This distinguishes between "the trade never worked" (stop issue) vs "the trade worked but we round-tripped" (trade management issue).

3. **Is `after_hours_exit` a common exit reason across all 38 test cases?** Search batch test results for how many trades exit via `after_hours_exit`. If it's common, this is a systemic problem.

4. **What is the `evaluate_position` polling interval in sim mode?** If the monitor only checks positions every N minutes, it might miss stop hits.

5. **Does the monitor check run during the full sim window (04:00-19:30)?** Or does it stop after a certain time?

6. **Why are there "ghost trades" (no exit, $0 P&L)?** Across the 5 worst cases, there are 10 trades logged with no exit and $0 P&L. Are these data artifacts or real entries that were never monitored?

## Starting Points

- `C:\Dev\Nexus\nexus2\domain\automation\warrior_monitor_exit.py` — `_check_stop_hit`, `evaluate_position`
- `C:\Dev\Nexus\nexus2\domain\automation\warrior_monitor.py` — monitor loop, position polling
- `C:\Dev\Nexus\nexus2\adapters\simulation\sim_context.py` — `step_clock_ctx`, how sim advances time and checks positions
- Search for: `after_hours_exit`, `_check_after_hours_exit`, `mental_stop`, `stop_price`

## Key Hypothesis

The sim might not be checking positions frequently enough (or at all after certain hours), causing stops to be missed and positions to bag-hold to EOD.

## Deliverables

Write findings to: `nexus2/reports/2026-03-02/research_bag_holding_stop_failure.md`

Include:
1. **Root cause** — why stops don't fire (with code evidence)
2. **Scope** — how many test cases are affected by `after_hours_exit`
3. **Ghost trades** — explain the $0 P&L no-exit trades
4. **Proposed fix** — specific code changes
5. **Estimated P&L impact** — if stops fired correctly, how much would MNTS have lost instead of $15K?

## Evidence Format (MANDATORY)
Every finding must include:
```
**Finding:** [description]
**File:** [absolute path]:[line number]
**Code:** [exact copy-pasted snippet]
**Verified with:** [PowerShell command]
**Output:** [actual command output]
**Conclusion:** [reasoning]
```
