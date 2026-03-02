# Research Handoff: Profitability Blockers

**Agent:** Backend Planner
**Date:** 2026-03-02
**Priority:** HIGH — These are the top two remaining blockers to Warrior Bot profitability.

## Context

On 2026-03-02, WB took 7 live trades before 6 AM ET, losing $7K+. Analysis revealed multiple safety failures. Two have been fixed:
- ✅ Missing 6AM time guard on `detect_pmh_break` → centralized in `check_entry_triggers`
- ✅ Spread filter dead in live mode → `get_quote_with_spread` now wired to engine

Two critical issues remain:

---

## Issue 1: Re-entry Cooldown (Missing)

### Observed Behavior
On 2026-03-02 live trades:
- **BATL**: Lost $1,742 on trade #1 (entry 09:16 UTC, exit 09:19). Re-entered at 10:19 UTC, lost $2,166 more.
- **CISS**: Lost $1,923 on trade #1 (entry 09:57, exit 10:08). Re-entered at 10:10, lost $1,591 more.
- The bot doubles down on losers — the opposite of Ross's methodology.

### Open Questions (Investigate)
1. **Does any re-entry cooldown mechanism exist?** Search for cooldown/blacklist/lockout logic after a losing trade on the same symbol.
2. **Where should it live?** Likely in `warrior_engine_entry.py` in `check_entry_triggers`, or in `warrior_entry_guards.py`.
3. **What does Ross do?** He sometimes re-enters after a loss, but only after a meaningful pullback and fresh setup — NOT immediately.
4. **Can this be verified in batch tests?** Check if any test cases show re-entries and whether adding a cooldown (e.g., 10-15 min after a loss) changes P&L.

### Starting Points
- `C:\Dev\Nexus\nexus2\domain\automation\warrior_engine_entry.py` — `check_entry_triggers()` line 334
- `C:\Dev\Nexus\nexus2\domain\automation\warrior_entry_guards.py` — `check_entry_guards()`
- `C:\Dev\Nexus\nexus2\db\warrior_db.py` — trade history lookups
- Search for: `entry_attempt_count`, `re-entry`, `cooldown`, `blacklist`

---

## Issue 2: Stop Adherence (`candle_under_candle` vs Stop Loss)

### Observed Behavior
On 2026-03-02 live trades:
- **BATL #1**: Stop was set at $9.71 (`consolidation_low`). Trade exited via `candle_under_candle` at $10.00. The exit reason overrode the stop, but in other cases `candle_under_candle` exits BELOW the defined stop price, creating a worse loss than the stop would have.

### Open Questions (Investigate)
1. **Does `candle_under_candle` respect the stop price?** If `candle_under_candle` fires and the exit price is below the stop, should the stop take precedence?
2. **What is the priority order between exit triggers?** Is `candle_under_candle` supposed to be a "tighter than stop" exit (which is fine) or can it create exits worse than the stop?
3. **Are there cases in batch tests where `candle_under_candle` exits below the stop?** Find examples and quantify the P&L impact.
4. **What does Ross say about stops?** His hard rule: "never let a trade go past your stop." Does our logic violate this?

### Starting Points
- `C:\Dev\Nexus\nexus2\domain\automation\warrior_monitor_exit.py` — `candle_under_candle` exit logic
- `C:\Dev\Nexus\nexus2\domain\automation\warrior_monitor.py` — exit priority/ordering
- Search for: `candle_under_candle`, `stop_price`, `exit_reason`, `mental_stop`

## Issue 3: Entry Quality Analysis — Bad Setups vs Bad Luck?

### The Question
Re-entry cooldown might treat the symptom, not the cause. If the original entries are fundamentally bad (wrong timing, wrong price, poor setup), then preventing re-entry just limits bleeding without fixing the root issue.

### How to Investigate
Use the batch test cases (38 cases, all based on Ross's actual trades) to compare:

1. **Entry timing**: For cases where the bot loses and Ross profits, compare entry times. Did we enter much earlier/later than Ross?
2. **Entry price**: Compare bot entry price vs Ross's entry price. If we consistently enter higher, that's a quality issue.
3. **Loss categorization**: For the bot's losing trades, categorize:
   - **Ross also lost** → Setup didn't work. Not our fault.
   - **Ross profited, we lost** → Our entry or exit was worse. Root cause needed.
   - **Ross didn't trade** → We entered something he wouldn't have. Scanner issue.

### Starting Points
- `C:\Dev\Nexus\scripts\gc_quick_test.py` — use `--all --trades` for per-trade details
- Focus on the cases with the largest negative deltas:
  - MLEC 2026-02-13: Bot -$578 vs Ross +$43K (Delta -$43K)
  - ROLR 2026-01-14: Bot +$46K vs Ross +$85K (Delta -$39K)
  - HIND 2026-01-27: Bot +$19K vs Ross +$55K (Delta -$36K)
  - MNTS 2026-02-09: Bot -$16K vs Ross +$9K (Delta -$25K)

### Deliverable
For the top 5 worst-performing cases (by delta), document:
- What time/price did the bot enter vs Ross?
- What was the exit reason for the bot vs Ross?
- Was the entry objectively bad, or was it a reasonable entry that went against us?

---

## Deliverables

Write research findings to: `nexus2/reports/2026-03-02/research_profitability_blockers.md`

For each issue:
1. **Current behavior** — exact code paths with file:line references
2. **Is it a bug?** — evidence-based conclusion
3. **Proposed fix** — specific code changes with rationale
4. **Batch test impact** — if possible, estimate which test cases are affected
5. **Ross methodology alignment** — cite `.agent/strategies/warrior.md` if relevant

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
