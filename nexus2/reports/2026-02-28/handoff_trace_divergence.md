# Trace Logging Investigation: Windows vs Linux Batch Divergence

**Agent:** Backend Planner  
**Priority:** P1  
**Date:** 2026-02-28  

---

## Context

Batch tests produce **$391K on Windows** and **$254K on Linux** — a $137K gap. We have **exhaustively eliminated** the following hypotheses:

| Hypothesis | Test Result |
|-----------|-------------|
| Wall-clock leakage (`datetime.now()`) | Fixed → no PnL change |
| Process isolation (`max_workers`) | Forced 1 + 2 workers → no change |
| Persisted config differences | API comparison → identical |
| Python version | Both 3.12.3 |
| Library versions (numpy, pandas, sqlalchemy) | All identical |
| Worker count causing state bleed | `max_workers=1` on Windows still $391K |
| DB contamination (old nexus.db records) | Clean empty DB on VPS → still $254K |

**Conclusion:** The divergence is a **pure Windows vs Linux behavioral difference** at the OS/platform level.

---

## Task: Find the First Divergent Decision

### Step 1: Pick one highly-divergent case

**ROLR** (`ross_rolr_20260114`): $45,724 on Windows vs -$1,458 on Linux.

### Step 2: Add trace logging to `_run_single_case_async`

At key decision points in the sim replay, log the current sim time and state. The trace should capture:

1. **Every entry decision:**
   - Sim time, symbol, price, shares, trigger type
   - "ENTRY at 09:42, ROLR @ $4.50, 5000 shares, trigger=pmh_break"

2. **Every exit decision:**
   - Sim time, symbol, price, shares, exit reason
   - "EXIT at 10:15, ROLR @ $4.20, 5000 shares, reason=mental_stop"

3. **Every guard block:**
   - Sim time, guard name, reason
   - "GUARD_BLOCK at 09:38, spread_too_wide, spread=2.5%"

4. **Key technical indicator values at entry points:**
   - EMA, VWAP, MACD values that gate entries
   - These are most likely to diverge between OS implementations

### Step 3: Run ROLR on both environments

Run the single case with trace logging:
```powershell
# This should be a new endpoint or a modified single-case run
Invoke-RestMethod -Method POST -Uri "http://localhost:8000/warrior/sim/enable" > $null
Invoke-RestMethod -Method POST -Uri "http://localhost:8000/warrior/sim/load_historical?case_id=ross_rolr_20260114" > $null
Invoke-RestMethod -Method POST -Uri "http://localhost:8000/warrior/sim/step?minutes=960" > $null
```

Then retrieve the trace log from both environments and diff them.

### Step 4: Find the first divergence point

Compare the traces line-by-line. The FIRST line that differs reveals whether the divergence is in:
- **Entry logic** (different price seen, different technical calc)
- **Exit logic** (different exit timing)
- **Data loading** (bars loaded in different order)

---

## Key Files to Investigate

| File | Why |
|------|-----|
| `nexus2/adapters/simulation/sim_context.py` | `step_clock_ctx()` — processes each simulated minute |
| `nexus2/domain/automation/warrior_engine_entry.py` | Entry decision logic |
| `nexus2/domain/automation/warrior_entry_guards.py` | Guard evaluation |
| `nexus2/domain/automation/warrior_entry_helpers.py` | Technical calculations (EMA, VWAP, MACD) |
| `nexus2/domain/automation/warrior_monitor_exit.py` | Exit decision logic |
| `nexus2/adapters/simulation/mock_bar_loader.py` | Bar data loading (ordering?) |

---

## Hypotheses to Test (Ranked by Likelihood)

### H1: Float arithmetic difference (MSVC vs glibc)
EMA, MACD, VWAP calculations use floating-point math. Windows (MSVC) and Linux (glibc) can produce subtly different results for the same float operations, especially with accumulated FMA (fused multiply-add) differences. Over hundreds of bars, tiny differences could compound and flip entry/exit decisions at thresholds.

**Test:** Log the EMA/MACD/VWAP values at entry decision points on both OS. Do they match exactly?

### H2: Dict/set iteration order
Although Python 3.7+ guarantees dict insertion order, `set` iteration order is still implementation-defined and can vary between runs/platforms. If any guard or indicator logic iterates over a `set`, results could differ.

**Test:** Grep for `set()` usage in entry/exit logic.

### H3: Bar loading order
If `mock_bar_loader.py` uses unordered iteration or file system listing, bars might load in different order on NTFS vs ext4.

**Test:** Log the first 5 and last 5 bars loaded for ROLR on both OS.

### H4: SQLite version / behavior
Windows Python bundles a different SQLite version than Linux. Query ordering without explicit `ORDER BY` can differ.

**Test:** Check `SELECT sqlite_version()` on both.

---

## Deliverable

Research report at `nexus2/reports/2026-02-28/research_trace_divergence.md` containing:
1. The trace logging approach taken
2. The first divergence point found
3. Root cause identification
4. Proposed fix
