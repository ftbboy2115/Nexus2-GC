# Handoff: Bag Holding Fix — Deep Investigation Required

**Agent:** Backend Planner  
**Date:** 2026-03-02  
**Priority:** HIGH — #1 profitability blocker after re-entry cooldown fix

---

## Context

Bag holding (positions held to EOD without proper exits) was identified as the biggest P&L drag.
Four fix approaches were tested by the coordinator — **all were net negative**:

| Approach | Net Change | Improved | Regressed | Why It Failed |
|----------|-----------|----------|-----------|--------------|
| Entry candle low | **-$85K** | 12 | 18 | Too tight — stopped out NPT, PRFX, VERO |
| 50¢ fixed cap | **-$21K** | 3 | 7 | Still too tight for TNMG (+$8K → -$11K) |
| 5% entry cap | **-$55K** | 5 | 13 | Tighter than 50¢ for cheap stocks |
| MFE trail (3%/50%) | **-$215K** | 17 | 13 | Cut every big winner (NPT -$66K, ROLR -$45K) |

**Key insight:** Every blanket approach hurts winners more than it helps losers. The winning cases (NPT=$68K, BATL=$50K, ROLR=$46K) use the wide consolidation stops to survive pullbacks before running. The losing cases (MNTS=-$15K, UOKA=-$10K) would benefit from tighter exits.

## What Needs Investigation

1. **Per-case price action analysis**: For each of the 13 cases that regressed with MFE trail, what was the price pattern? Did the stock dip then recover? For the 17 improved cases, what was different?

2. **Time-based behavior**: Do winning cases tend to move quickly after entry, while losing cases drift? Could a time-based guard (e.g., "if not up 2% within 30 minutes, tighten stop") work better than price-based?

3. **Entry trigger correlation**: Do `dip_for_level` and `whole_half_anticipatory` entries bag-hold more than `micro_pullback` and `pmh_break`? If certain triggers produce wider stops or worse outcomes, the fix might be trigger-specific.

4. **MFE trail with higher thresholds**: The 3% activation / 50% give-back was too aggressive. What about 10% activation / 75% give-back? A param sweep across activation (3-15%) and give-back (50-90%) could find a sweet spot.

5. **Home_run vs base_hit interaction**: The code already switches from base_hit to home_run after partial. Does the MFE trail interfere with this transition? Should MFE trail only apply to base_hit and NOT home_run positions?

## Code Already Written (Dead Code)

`_check_mfe_trail` function exists in `warrior_monitor_exit.py` (around line 401) but is NOT wired into `evaluate_position`. Can be re-enabled by adding settings to `warrior_types.py` and wiring CHECK 0.8 back in.

## Ghost Trade DB Bug (Investigate & Fix)

34 of 76 trades across 38 cases have `exit_reason: null` and `pnl: $0`. These are scale-in DB records that never get closed. This inflates `hod_break` count and drags down its win rate (reported 10.3%, likely 30-50% real).

**Root cause hypothesis (VERIFY):**
- Scale-ins create new DB rows via `log_warrior_entry`, but exit only closes the first record found by `get_warrior_trade_by_symbol`
- In-memory `WarriorPosition.shares` is correct (consolidation works), but DB records are orphaned

**Questions to verify:**
1. Does `handle_exit` exit the correct total number of shares (from in-memory position), or only from the first DB record?
2. Does `get_warrior_trade_by_symbol` return first record or all? What if it returns record #3 instead of #1?
3. Is any P&L being lost because exit P&L is logged against only one record's share count?
4. In **live mode**, do orphaned `status=open` records interfere with re-entry guards or position tracking?

**Starting points:**
- `warrior_monitor.py:_consolidate_existing_position` (~line 290)
- `warrior_monitor_exit.py:handle_exit` (~line 1356)
- `warrior_db.py:get_warrior_trade_by_symbol` — which record does it return?
- `warrior_db.py:log_warrior_entry` — new rows for scale-ins?

**Proposed fix (after verification):** Either (a) stop creating new DB rows for scale-ins, or (b) at exit, close ALL open DB records for the symbol.

**Also:** Rerun trigger correlation analysis with `exit_reason IS NOT NULL` filter for clean win rates.

## Key Files

- `warrior_monitor_exit.py` — evaluate_position check chain, _check_mfe_trail function
- `warrior_types.py` — WarriorMonitorSettings
- `warrior_monitor.py` — _create_new_position (stop assignment)
- `warrior_entry_sizing.py` — calculate_stop_price (consolidation low)

## Deliverables

Write findings to: `nexus2/reports/2026-03-02/research_bag_holding_deep_analysis.md`

Include:
1. Per-case MFE/MAE analysis for all 38 cases
2. Correlation between entry trigger type and outcome
3. Time-to-profit analysis (how fast do winners move vs losers?)
4. Recommended approach with param sweep results
5. Evidence format per standard (file, line, code, command, output)
