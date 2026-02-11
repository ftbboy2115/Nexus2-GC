# Phase 9 Round 2 Validation: Verify Per-Case Root Cause Claims

> [!CAUTION]
> The Round 1 auditor hand-waved and the Round 1 validator accepted it. This round we demand PROOF from the auditor, and YOUR job is to VERIFY that proof.
>
> The auditor claims two root causes: `engine.stats` accumulation (RC1) and `engine._blacklist` not cleared (RC2). These are plausible but NOT proven. The auditor provided ZERO runtime evidence — only code analysis. Your job is to determine whether these claims actually explain the specific P&L deltas, or if the auditor is telling a convincing story without evidence.

---

## Auditor Claims to Validate

### RC1: `engine.stats` Not Reset Causes Divergence

**Auditor's claim**: `entries_triggered`, `candidates_found`, `_seen_candidates` accumulate across sequential cases, "affecting `top_x_picks` ranking logic" and "entry selectivity."

**Your task — trace the ACTUAL impact path**:

1. **Does `entries_triggered` affect any entry decision?** Find every read of `engine.stats.entries_triggered` in the codebase. If it's only used for logging/display, it CANNOT cause P&L divergence.

```powershell
Get-ChildItem "nexus2\domain\automation" -Recurse -Filter "*.py" | Select-String -Pattern "entries_triggered" -Context 2,2
```

```powershell
Get-ChildItem "nexus2\domain\automation" -Recurse -Filter "*.py" | Select-String -Pattern "stats\.entries" -Context 2,2
```

2. **Does `_seen_candidates` affect any entry decision?** Find every read of `_seen_candidates`.

```powershell
Get-ChildItem "nexus2\domain\automation" -Recurse -Filter "*.py" | Select-String -Pattern "_seen_candidates" -Context 2,2
```

3. **Does `candidates_found` or `scans_run` gate any logic?**

```powershell
Get-ChildItem "nexus2\domain\automation" -Recurse -Filter "*.py" | Select-String -Pattern "stats\.(candidates_found|scans_run|orders_)" -Context 2,2
```

4. **Does `daily_pnl` gate entries?** The auditor says `max_daily_loss=999999` (effectively disabled). Verify this.

```powershell
Get-ChildItem "nexus2\domain\automation" -Recurse -Filter "*.py" | Select-String -Pattern "max_daily_loss|daily_pnl" -Context 2,2
```

**Verdict criteria**:
- If `entries_triggered`, `_seen_candidates`, `candidates_found`, and `scans_run` are ONLY used for logging/telemetry and never gate entry decisions → **RC1 is DISPROVED as a divergence cause** (still worth resetting for cleanliness, but NOT the cause of P&L differences)
- If ANY of these fields gate an entry/exit decision → **RC1 is CONFIRMED** — cite the exact line

---

### RC2: `engine._blacklist` Not Cleared

**Auditor's claim**: Symbols rejected in case N are permanently blocked in subsequent cases.

**Your task**:

1. **When does `_blacklist.add()` fire?** Under what conditions?

```powershell
Get-ChildItem "nexus2\domain\automation" -Recurse -Filter "*.py" | Select-String -Pattern "_blacklist\.add" -Context 3,3
```

2. **Would it fire during MockBroker sim mode?** The mock broker doesn't call real Alpaca APIs. Can a MockBroker rejection trigger a blacklist add?

```powershell
Select-String -Path "nexus2\adapters\simulation\mock_broker.py" -Pattern "reject|blacklist|error" -Context 2,2
```

3. **Is `_blacklist` checked in entry guards?**

```powershell
Get-ChildItem "nexus2\domain\automation" -Recurse -Filter "*.py" | Select-String -Pattern "_blacklist" -Context 2,2
```

4. **For D2 (BATL Day 2, case #4)**: Would BATL actually be in `_blacklist` after D1 (case #3)? What specific entry failure would trigger it?

**Verdict criteria**:
- If MockBroker can never trigger `_blacklist.add()` → **RC2 is DISPROVED** (blacklist would remain empty in sim/batch mode)
- If MockBroker CAN trigger `_blacklist.add()` → **RC2 is CONFIRMED for D2 (BATL)**, but cannot explain D3-D9 (all unique symbols)

---

### Per-Case Analysis (D1 + D5 specifically)

The auditor provided narrative explanations but NO EVIDENCE for D1 and D5. Validate:

**D1 (BATL 01-26, Δ=$1,555)**: The auditor says "concurrent runner takes more aggressive entry attempts that result in larger losses." 
- Is there ANY code path where `engine.stats` fields cause fewer entries?
- Or is the auditor telling a plausible story without a mechanism?

**D5 (TNMG, Δ=$324)**: The auditor says "entries_triggered counter is significantly elevated" causing "more selective" entries.
- Same question: what code reads `entries_triggered` and decides to be more selective?

---

### H5: `apply_settings_to_config` Differences

The auditor's state inventory shows `config` is "❌ Retained from `__init__`" in sequential vs "✅ Fresh `WarriorEngineConfig(sim_only=True)`" in concurrent.

**Validate**: Does `apply_settings_to_config()` run in BOTH paths? Do they produce the same config values?

```powershell
Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "apply_settings" -Context 3,3
```

```powershell
Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "apply_settings" -Context 3,3
```

```powershell
# Check what settings are applied
if (Test-Path "data\warrior_settings.json") { Get-Content "data\warrior_settings.json" }
```

---

## Output Requirements

```markdown
## Phase 9 Round 2 Validation Report

### RC1 Validation (stats accumulation)
| Stats Field | Used in entry/exit decisions? | Evidence |
|-------------|------------------------------|----------|
| entries_triggered | YES/NO | [line reference or "logging only"] |
| _seen_candidates | YES/NO | [line reference or "logging only"] |
| candidates_found | YES/NO | [line reference or "logging only"] |
| scans_run | YES/NO | [line reference or "logging only"] |
| daily_pnl | YES/NO | [line reference or "gated but disabled"] |

**Verdict**: RC1 CONFIRMED/DISPROVED as P&L divergence cause

### RC2 Validation (blacklist)
| Question | Answer | Evidence |
|----------|--------|----------|
| Can MockBroker trigger _blacklist.add()? | YES/NO | [code path] |
| Would BATL be blacklisted after D1? | YES/NO | [mechanism] |
| Does _blacklist explain D3-D9 (unique symbols)? | YES/NO | [reasoning] |

**Verdict**: RC2 CONFIRMED/DISPROVED as P&L divergence cause

### Config Differences (H5)
| Runner | apply_settings called? | Config values |
|--------|----------------------|---------------|
| Sequential | YES/NO at line X | [key values] |
| Concurrent | YES/NO at line X | [key values] |

**Verdict**: Config difference CONFIRMED/DISPROVED as divergence source

### Per-Case Validation
| Case | Auditor's Claimed Cause | Validated? | Actual Cause |
|------|------------------------|------------|--------------|
| D1 | RC1 (stats) | YES/NO | [your finding] |
| D5 | RC1 (stats) | YES/NO | [your finding] |

### Overall Rating
- **HIGH**: Auditor's root causes verified with evidence
- **MEDIUM**: Partially correct, some claims unsubstantiated  
- **LOW**: Root causes not proven, hand-waving detected

### If Root Causes Are Disproved
If RC1 and RC2 do NOT explain the divergence, propose what DOES. What other state difference between `load_historical_test_case` and `load_case_into_context` / `SimContext.create()` could cause P&L differences?
```

Write to `nexus2/phase9_round2_validation_report.md`.
