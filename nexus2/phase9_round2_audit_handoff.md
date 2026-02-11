# Phase 9 Round 2 Audit: Per-Case Divergence Root Cause

> [!CAUTION]
> The previous audit round declared "monitor bleed-over was the root cause" and dismissed all 5 claims as non-issues. This is **UNACCEPTABLE** because **9 out of 22 cases still diverge** after the fix was applied. Hand-waving like "secondary effects that only manifest..." is NOT a root cause analysis.
>
> This round demands **per-case forensic analysis** for every divergent case. For each case, you must identify the SPECIFIC code path that produces different P&L in sequential vs concurrent. "It's probably X" is not acceptable — show the exact line(s) and mechanism.

---

## What Has Already Been Done

1. **Phase 9 fix applied** at `warrior_sim_routes.py:L826-832`:
   - `engine.monitor._positions.clear()`
   - `engine.monitor._recently_exited.clear()`
   - `engine.monitor._recently_exited_sim_time.clear()` (L849)
   - `engine.monitor.realized_pnl_today = Decimal("0")` (L850)

2. **Testing agent verified**: 13/22 cases now converge. 9 still diverge.

3. **Previous auditor dismissed C1-C5** (engine state, throttle, DB, callbacks, broker cash) as non-issues. Validator found one missed bug: `_blacklist` not cleared (AF1).

---

## The 9 Divergent Cases (HARD DATA)

| # | Case | Symbol | Seq P&L | Conc P&L | Delta | Notes |
|---|------|--------|---------|----------|-------|-------|
| D1 | ross_batl_20260126 | BATL | -$175.79 | -$1,730.49 | **$1,554.70** | LARGEST divergence |
| D2 | ross_batl_20260127 | BATL | -$550.86 | -$719.95 | $169.09 | Same symbol as D1 |
| D3 | ross_rolr_20260114 | ROLR | $1,538.73 | $1,622.73 | $84.00 | |
| D4 | ross_bnkk_20260115 | BNKK | $176.70 | $36.98 | $139.72 | |
| D5 | ross_tnmg_20260116 | TNMG | -$52.53 | -$376.05 | $323.52 | |
| D6 | ross_vero_20260116 | VERO | -$81.69 | -$302.65 | $220.96 | |
| D7 | ross_dcx_20260129 | DCX | $326.99 | $118.26 | $208.73 | |
| D8 | ross_bnai_20260205 | BNAI | $185.26 | $66.70 | $118.56 | |
| D9 | ross_uoka_20260209 | UOKA | $279.50 | $244.94 | $34.56 | Smallest divergence |

**Total**: Sequential $4,062.26 vs Concurrent $1,376.42 — **$2,685.84 gap**

---

## Required Analysis: Per-Case Root Cause

For **AT MINIMUM** D1 (BATL 01-26, $1,555 delta) and D5 (TNMG, $324 delta), you must:

### Step 1: Determine Case Execution Order

The sequential runner runs cases in order. Determine which case number each divergent case is (1st, 2nd, 3rd, etc.). Cases that run LATER have more opportunity for state accumulation.

```powershell
# Check the test case order in warrior_setups.yaml
Select-String -Path "nexus2\tests\test_cases\warrior_setups.yaml" -Pattern "case_id:" -Context 0,0
```

### Step 2: Identify State Differences

For D1 (BATL 01-26), answer these SPECIFIC questions:

1. **How many trades does each runner execute for this case?** Compare the `trades` array length and entry_triggers from both results.
2. **Do they enter at different prices?** If entries differ, the ENGINE is behaving differently.
3. **Do they exit at different prices?** If exits differ, the MONITOR is behaving differently.
4. **Is there a trade in one runner that doesn't exist in the other?** This would indicate a state-dependent entry decision.

### Step 3: Trace the Divergent Code Path

For each difference found in Step 2, trace backwards:

- If **different number of entries**: What entry condition fired in one runner but not the other? Check entry guards, blacklist, recently_exited, pending_entries. 
- If **different entry prices**: Is the get_price callback returning different values?
- If **different exits**: Is the monitor evaluating different stop levels or exit conditions?
- If **same trades but different P&L math**: Is MockBroker computing P&L differently?

---

## Specific Hypotheses to Test

### H1: Engine State Beyond the Cleared Fields

The sequential runner clears 7 fields between cases. List ALL mutable state on `WarriorEngine` and cross-check against what's cleared:

```powershell
# Find ALL self._ assignments in WarriorEngine.__init__
Select-String -Path "nexus2\domain\automation\warrior_engine.py" -Pattern "self\._\w+" -Context 0,0
```

```powershell
# Find ALL .clear() or reset calls in load_historical_test_case
Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "\.clear\(\)|engine\._|monitor\._" -Context 0,0
```

Produce a table: `| Field | Cleared? | Could Affect P&L? |`

### H2: MockBroker State Accumulation

`broker.reset()` clears 7 fields. List ALL mutable state on `MockBroker` and verify reset covers everything:

```powershell
Select-String -Path "nexus2\adapters\simulation\mock_broker.py" -Pattern "self\._\w+" -Context 0,0 | Select-Object -First 30
```

### H3: Monitor State Beyond Phase 9 Fix

Are there monitor fields besides `_positions`, `_recently_exited`, `_recently_exited_sim_time`, and `realized_pnl_today` that could leak?

```powershell
Select-String -Path "nexus2\domain\automation\warrior_monitor.py" -Pattern "self\._\w+" -Context 0,0
```

### H4: `load_historical_test_case` vs `load_case_into_context` Behavioral Differences

These two functions should produce identical engine states. Diff their logic:

```powershell
# Sequential: load_historical_test_case setup steps
Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "def load_historical_test_case" -Context 0,50
```

```powershell
# Concurrent: load_case_into_context setup steps  
Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "def load_case_into_context" -Context 0,50
```

### H5: `apply_settings_to_config` Persistence

If `apply_settings_to_config()` reads from `data/warrior_settings.json`, it may apply settings that the concurrent runner doesn't have (since the concurrent runner may skip this or read different defaults):

```powershell
Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "apply_settings" -Context 2,5
```

```powershell
Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "apply_settings|warrior_settings" -Context 2,5
```

---

## Output Requirements

### Format

```markdown
## Phase 9 Round 2 Audit Report

### Case Execution Order
[Numbered list of all 22 cases in sequential execution order]

### Engine State Inventory
| # | Field | Type | Cleared? | P&L Impact? |
|---|-------|------|----------|-------------|
| 1 | _watchlist | dict | YES (L822) | — |
| 2 | ... | ... | ... | ... |

### Per-Case Root Cause (D1 – D9)
For each divergent case:

#### D1: BATL 01-26 (seq -$176 vs conc -$1,730)
- **Execution position**: Nth case in sequential order
- **Trade count**: seq X trades, conc Y trades
- **Divergence mechanism**: [SPECIFIC code path]
- **Evidence**: [grep output or line references]

[Repeat for D2-D9, at minimum D1 and D5 fully traced]

### Root Cause Summary
[What SPECIFICALLY causes the remaining 9-case divergence]

### Recommended Fixes
[Concrete, line-level fixes with before/after code]
```

> [!IMPORTANT]
> **DO NOT** conclude "monitor bleed-over was the root cause." That fix is already applied. The 9 cases diverge WITH the fix in place. Your job is to explain WHY they still diverge.

Write to `nexus2/phase9_round2_audit_report.md`.
