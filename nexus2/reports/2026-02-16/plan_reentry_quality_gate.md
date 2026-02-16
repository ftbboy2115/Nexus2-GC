# Re-entry Quality Gate — Implementation Plan

## Design Decisions (Approved)

- **Gate strictness**: Block re-entry after ANY single loss on that symbol (no cumulative tracking)
- **Gate scope**: Centralized in `check_entry_guards` (catches ALL entry paths universally)
- **Approach**: Backend Planner researches first, then Backend Specialist implements

## Problem Statement

Analysis of 29 batch test cases shows that **bad re-entries** cost the bot ~$62K in P&L delta vs Ross. Specifically:

| Case | Bot vs Ross | Re-entry Issue |
|------|-------------|----------------|
| MNTS | -$16K delta | Re-entered at 13:08 after losing first trade, price -10% below entry |
| MLEC | -$46K delta | 3rd entry at 15:39 was on exhausted stock, near original entry after round-trip |

**No simple time/price filter works** — every heuristic blocks 3-10 good re-entries alongside the bad ones:
- Time gap > 120 min: blocks 10 good + 3 bad
- Price below entry: blocks 4 good + 1 bad
- Price above entry: blocks 10 good + 2 bad

**The distinguishing factor is whether the prior trade was profitable**, not time or price direction. Good re-entries occur on stocks that are "still working" — bad re-entries are "revenge trades" on stocks that already failed.

## Architecture (Verified Evidence)

### How Re-entries Currently Work

1. **Exit fires callback**: [warrior_monitor_exit.py:1432-1444](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py#L1432-L1444) — Only fires `_on_profit_exit` for `PROFIT_TARGET` exits
2. **Engine enables re-entry**: [warrior_engine.py:206-254](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_engine.py#L206-L254) — `_handle_profit_exit` resets `entry_triggered=False`, stores exit price/time
3. **Re-entry guards check**: [warrior_entry_guards.py:119-137](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py#L119-L137) — Cooldown only (10 min live, configurable sim)
4. **Pattern-specific guards**: [warrior_entry_patterns.py:423-457](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py#L423-L457) — DIP_FOR_LEVEL has its own re-entry guards (cooldown, max attempts, price above exit)

### Gap

The system **only enables re-entry after PROFIT exits** (`_on_profit_exit` callback). But the data shows MNTS and MLEC bad re-entries still happen — meaning entries are re-triggered through other paths (not the profit exit callback). The `entry_triggered` flag gets reset through the general entry flow, not just through `_on_profit_exit`.

> [!IMPORTANT]
> **Open question for Backend Planner**: How exactly are MNTS and MLEC re-entries triggered? Is it through `_on_profit_exit` (meaning the first trade *did* exit at profit target before the bad re-entry), or through a different path? The Planner must trace the exact flow.

## Proposed Changes

### Phase 1: Backend Planner (Research + Spec)

The Backend Planner should:
1. **Trace** the exact re-entry path for MNTS and MLEC using sim logs
2. **Verify** whether the prior trade exited at profit or loss before re-entry
3. **Spec** the exact change surface for adding a `last_exit_pnl` field and quality gate
4. **Document** interaction with existing re-entry guards (cooldown, max attempts, price-above-exit)

### Phase 2: Backend Specialist (Implementation)

Based on Planner's spec:
1. Add `last_exit_pnl: Optional[Decimal]` to `WatchedCandidate` ([warrior_engine_types.py:170](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_engine_types.py#L170))
2. Populate `last_exit_pnl` in exit callback (extend `_on_profit_exit` or create `_on_any_exit`)
3. Add quality gate in `check_entry_guards` ([warrior_entry_guards.py:119](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py#L119)): **block re-entry if `last_exit_pnl < 0`**
4. A/B toggle: `enable_reentry_quality_gate: bool` in `WarriorMonitorSettings`

### Phase 3: Testing Specialist (Validation)

1. Run batch test with gate ON vs OFF
2. Verify MNTS, MLEC re-entries are blocked
3. Verify ROLR, BATL, VERO re-entries still pass

## Agents Required

| Agent | Task | Handoff |
|-------|------|---------|
| **Backend Planner** | Research re-entry flow, trace MNTS/MLEC, write spec | `handoff_planner_reentry_gate.md` |
| **Backend Specialist** | Implement quality gate per spec | `handoff_backend_reentry_gate.md` (after Planner) |
| **Testing Specialist** | Run batch validation | `handoff_testing_reentry_gate.md` (after Backend) |

## Expected P&L Impact

Conservative estimate: blocks MNTS 13:08 re-entry (-$5K saved) and MLEC 15:39 re-entry (portion of -$3K saved).
Total: **+$5K–8K improvement** in batch total with zero good re-entries blocked.
