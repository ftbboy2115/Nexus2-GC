# Backend Planner: Winner-to-Loser Investigation

**Date:** 2026-02-16  
**Priority:** HIGH — 5 cases where Ross profited and bot loses = -$27k gap at Ross sizing  
**Output:** `nexus2/reports/2026-02-16/findings_winner_to_loser.md`

---

## Objective

Investigate why 5 Ross-profitable test cases produce LOSSES for the Warrior bot. Identify the root cause for each — bad entry timing, bad exit, re-entry damage, or pattern mismatch.

## Cases to Investigate (Ross-matched sizing: risk=$2500, shares=10k)

| Case | Bot P&L | Ross P&L | Gap | Setup |
|------|---------|----------|-----|-------|
| MNTS | -$7,046 | +$9,000 | $16,046 | PMH |
| LCFY | -$4,833 | +$10,457 | $15,290 | PMH |
| FLYE | -$3,866 | +$4,800 | $8,666 | PMH |
| MLEC | -$2,997 | +$43,000 | $45,997 | PMH |
| BNRG | -$4,526 | +$272 | $4,798 | VWAP reclaim |

Combined gap: **~$90,797** at Ross sizing.

## Investigation Steps

### For Each Case, Answer:

1. **Did the bot enter?** (total_pnl < 0 means yes, it entered and lost)
2. **Where did the bot enter vs Ross?**
   - Bot entry price vs `expected.entry_near` from YAML
   - How far off from Ross's entry?
3. **What pattern triggered entry?**
   - Was it the right pattern for this setup?
   - Did pattern competition pick a suboptimal trigger?
4. **What exit triggered?**
   - Exit reason (mental_stop, candle_under_candle, topping_tail, profit_target, etc.)
   - Exit price vs what Ross actually did
5. **Did re-entries happen?**
   - How many re-entries?
   - Did re-entries turn a small loss into a large loss?
   - Could re-entry quality gates have helped?
6. **What would have been the P&L if:**
   - Only 1 entry (no re-entries)?
   - Ross's entry price was used?

### How to Get This Data

Run each case individually and examine the detailed trade log:

```powershell
$body = '{"case_ids": ["ross_mnts_20260209"]}';
$r = Invoke-RestMethod -Uri "http://localhost:8000/warrior/sim/run_batch_concurrent" -Method POST -ContentType "application/json" -Body $body -TimeoutSec 300;
$r.results[0] | ConvertTo-Json -Depth 10
```

Check the response for:
- `trades` array — each entry/exit event
- `total_pnl` — final P&L
- Pattern types, entry prices, exit reasons

Also check the warrior_db trade log after each run:
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/warrior/trades" -Method GET | ConvertTo-Json -Depth 5
```

### Key Areas to Research in Code

1. **Entry timing:** `warrior_engine_entry.py` — when does the first pattern fire?
2. **Exit logic:** `warrior_monitor_exit.py` — which exit check triggers?
3. **Re-entry logic:** `warrior_monitor.py` — how many re-entries, and what quality?
4. **Scaling impact:** Does the accidental 1-scale (50% add) amplify losses?

## Evidence Requirements

For EVERY finding, provide:
```
**Finding:** [description]
**File:** [absolute path]:[line number] (if code-related)
**Data:** [exact command output showing the behavior]
**Conclusion:** [reasoning]
```

## Output Format

Write to: `nexus2/reports/2026-02-16/findings_winner_to_loser.md`

Structure:
1. Per-case breakdown (entry/exit/re-entry analysis)
2. Common patterns across cases (are they all the same root cause?)
3. Quantified impact of each failure mode
4. Prioritized recommendations (what fix would recover the most P&L?)

## Current Config (for running sims)

The server is running with Ross-matched sizing:
- risk_per_trade: $2,500
- max_shares_per_trade: 10,000
- max_capital: $100,000
- enable_partial_then_ride: True (Fix 1)
- enable_scaling: True (accidental 1-scale)
- enable_improved_scaling: False
