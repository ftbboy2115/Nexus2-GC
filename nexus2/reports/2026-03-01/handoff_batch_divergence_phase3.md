# Handoff: Batch Divergence — Phase 3 Deep Investigation

**Agent:** Backend Planner  
**Priority:** P1  
**Date:** 2026-03-01  

---

## Problem

Batch tests produce **$409K on Windows** and **$271K on Linux** — a **$139K gap**. Both environments use the same code, Python 3.12.3, identical library versions, and identical configs.

---

## What We Already Fixed (Keep — These Were Real Bugs)

### Exit logic (warrior_monitor_exit.py)
- All `datetime.now()` and `now_utc()` replaced with `sim_aware_now_utc()` / `sim_aware_now_et()` 
- New centralized functions in `nexus2/utils/time_utils.py`

### Entry logic
- `_get_eastern_time()` in `warrior_engine.py:291` → uses `sim_aware_now_et()`
- `time.time()` throttle in `warrior_engine_entry.py:398` → uses `sim_aware_now_utc().timestamp()`
- `datetime.now()` in `warrior_entry_helpers.py:356` → uses `sim_aware_now_utc()`

### Impact of fixes
- Both environments improved by ~$17K (correct time_score with sim time)
- **Gap unchanged** — $137K → $139K

---

## What We Eliminated

| Hypothesis | How Tested | Result |
|-----------|-----------|--------|
| Wall-clock in exit logic | Fixed all 4 sites | No convergence |
| Wall-clock in entry logic | Fixed all 3 sites | No convergence |
| Process isolation (max_workers) | Forced 1 and 2 workers | No change |
| Config differences | API comparison | Identical |
| Python version | Both 3.12.3 | Same |
| Library versions (numpy, pandas, sqlalchemy) | pip show comparison | Identical |
| max_workers=1 on Windows | Tested locally | Still $391K → not worker count |
| DB contamination (nexus.db) | Clean empty DB on VPS | Still $254K |
| Set iteration order | Grep audit | All sets use `sorted()` |
| Bar loading order | Code review | Time-sorted from JSON |
| SQLite version differences | Per-process in-memory DB | No shared queries |
| TechnicalService singleton leak | ProcessPoolExecutor isolation | Each process fresh |

---

## What To Investigate Next

### 1. Comprehensive wall-clock audit
Run this and investigate EVERY match:
```powershell
Select-String -Path "nexus2\domain\automation\*.py" -Pattern "datetime\.now\(|time\.time\(\)|\.now_et\(\)|\.now_utc\(\)" -Recurse
```
Also check:
- `nexus2/adapters/simulation/*.py`
- `nexus2/domain/scanner/*.py`
- Any utility function called from the sim code path

### 2. Technical indicator implementation 
Even though numpy/pandas versions match, the `TechnicalService` (likely in `nexus2/domain/market_data/`) computes EMA, VWAP, MACD. Check if:
- Any caching key depends on wall-clock
- Any float comparison uses `>` vs `>=` at boundary values
- pandas-ta produces different results on Windows vs Linux for edge cases

### 3. Run single-case trace comparison
Pick ROLR (`ross_rolr_20260114`): $61K local vs a few K on VPS.
Add trace logging at:
- **Entry decision** (`warrior_engine_entry.py` ~line 614): log pattern name, score, threshold
- **Guard evaluation** result for each call
- **Technical values** at entry point (EMA9, VWAP, MACD)
Run on both environments, diff the logs.

### 4. Check for any remaining `import time` usage
The `time` module (not `datetime`) might be used in unexpected places:
```powershell
Select-String -Path "nexus2\domain\automation\*.py" -Pattern "import time|time\.time|time\.sleep"
```

### 5. Check mock_broker.py and mock_bar_loader.py
These are in the sim code path. Any non-determinism here would affect results.

---

## Key Files

| File | Role |
|------|------|
| `nexus2/utils/time_utils.py` | `sim_aware_now_utc()`, `sim_aware_now_et()` |
| `nexus2/adapters/simulation/sim_clock.py` | ContextVar `_sim_clock_ctx` |
| `nexus2/adapters/simulation/sim_context.py` | Concurrent batch runner |
| `nexus2/domain/automation/warrior_engine_entry.py` | Entry decisions |
| `nexus2/domain/automation/warrior_entry_guards.py` | Guard evaluation |
| `nexus2/domain/automation/warrior_entry_helpers.py` | Technical calculations |
| `nexus2/domain/automation/warrior_monitor_exit.py` | Exit decisions |

---

## Previous Reports
- `nexus2/reports/2026-02-28/research_batch_divergence.md` — Initial research (Phase 1)
- `nexus2/reports/2026-02-28/research_trace_divergence.md` — Entry logic findings (Phase 2)
- `nexus2/reports/2026-02-28/validation_batch_divergence.md` — Phase 1 validation
- `nexus2/reports/2026-02-28/validation_trace_divergence.md` — Phase 2 validation

## Batch Test Results (for reference)

| Run | Local PnL | VPS PnL | Gap |
|-----|-----------|---------|-----|
| Pre-fix baseline | $391,215 | $253,758 | $137,457 |
| After entry+exit fix | $409,384 | $270,526 | $138,858 |

## Deliverable
Research report at `nexus2/reports/2026-03-01/research_batch_divergence_phase3.md`
