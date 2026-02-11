# Validation Handoff: Monitor State Bleed-Over Theory

## Theory Under Test

**Claim**: The sequential batch runner's P&L divergence from the concurrent runner is caused by `WarriorMonitor._positions` and `_recently_exited` NOT being cleared between sequential batch cases. The concurrent runner creates a fresh `WarriorMonitor()` per case, avoiding this.

## Files to Examine

| File | Role |
|------|------|
| `nexus2/api/routes/warrior_sim_routes.py` | Sequential runner |
| `nexus2/adapters/simulation/sim_context.py` | Concurrent runner |
| `nexus2/domain/automation/warrior_monitor.py` | Monitor class |

---

## Claims to Verify (V1–V5)

### V1: `remove_position()` is NEVER called in `warrior_sim_routes.py`

**What to check**: The monitor's `remove_position()` method is never invoked anywhere in the sequential runner file.

**Expected**: Zero matches.

```powershell
Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "remove_position"
```

**If PASS**: Confirms positions added to the monitor during case N are never removed before case N+1 loads.

---

### V2: `_positions.clear()` is NOT called in `load_historical_test_case`

**What to check**: The `_positions` dict on the monitor is never cleared during test case loading.

```powershell
Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "_positions"
```

**Expected**: Zero matches for `_positions.clear()`. You may find references to broker positions but NOT `monitor._positions.clear()`.

**If PASS**: Confirms positions bleed across sequential cases.

---

### V3: Only `_recently_exited_sim_time` is cleared, NOT `_recently_exited`

**What to check**: Line ~841 clears `_recently_exited_sim_time` but the wall-clock `_recently_exited` dict is NOT cleared.

```powershell
Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "recently_exited"
```

**Expected**: Should find `_recently_exited_sim_time.clear()` but NOT `_recently_exited.clear()`.

**If PASS**: Confirms wall-clock exit cooldowns could also bleed across cases.

---

### V4: EOD close sells broker positions but does NOT clear monitor

**What to check**: The batch loop's EOD close (lines ~1408-1442) calls `broker.sell_position()` but never calls `monitor.remove_position()` or `monitor._positions.clear()`.

```powershell
Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "sell_position|remove_position" -SimpleMatch
```

**Expected**: `sell_position` appears (EOD close), `remove_position` does NOT appear.

**If PASS**: Confirms that even after EOD close, monitor retains stale position objects.

---

### V5: Concurrent runner creates fresh monitor per case (control)

**What to check**: `SimContext.create()` instantiates `WarriorMonitor()` fresh with explicit resets.

```powershell
Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "WarriorMonitor|_recently_exited"
```

**Expected**: Shows `monitor = WarriorMonitor()` and explicit `_recently_exited_file = None`, `_recently_exited = {}`, `_recently_exited_sim_time = {}`.

**If PASS**: Confirms concurrent runner has zero bleed-over by design.

---

## Verdict Criteria

| Result | Meaning |
|--------|---------|
| **All 5 PASS** | Theory is CONFIRMED — monitor state bleed is the root cause |
| **V1 or V4 FAIL** | Theory is WRONG — positions ARE being cleaned up somewhere |
| **V2 FAIL** | Theory is WRONG — `_positions` IS being cleared |
| **V3 irrelevant** | `_recently_exited` may or may not matter (secondary) |
| **V5 FAIL** | Both runners have contamination (different problem) |

---

## Report Format

Write results to `nexus2/monitor_bleedover_validation_report.md`:

```markdown
## Validation Report: Monitor Bleed-Over Theory

### Claims Verified
| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| V1 | remove_position never called | PASS/FAIL | [command + output] |
| V2 | _positions never cleared | PASS/FAIL | [command + output] |
| V3 | _recently_exited not cleared | PASS/FAIL | [command + output] |
| V4 | EOD close doesn't clear monitor | PASS/FAIL | [command + output] |
| V5 | Concurrent creates fresh monitor | PASS/FAIL | [command + output] |

### Verdict
CONFIRMED / DISPROVED / INCONCLUSIVE

### Additional Findings (if any)
[Note anything unexpected]
```
