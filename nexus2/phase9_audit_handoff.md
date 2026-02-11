# Phase 9 Audit: Remaining Runner Divergence (9 Cases)

## Background

Phase 9 monitor bleed-over fix was applied and verified by the testing agent. Results:
- **13/22 cases converge** ✅ (including FLYE/RVSN which now both produce $0)  
- **9/22 cases still diverge** ⚠️ (sequential $4,062 vs concurrent $1,376)
- Concurrent runner is more correct (fresh `SimContext` per case = zero state leakage)

## The 9 Divergent Cases

| Case | Symbol | Date | Seq P&L | Conc P&L | Delta |
|------|--------|------|---------|----------|-------|
| ross_batl_20260126 | BATL | 01-26 | -$175.79 | -$1,730.49 | **$1,554.70** |
| ross_batl_20260127 | BATL | 01-27 | -$550.86 | -$719.95 | $169.09 |
| ross_rolr_20260114 | ROLR | 01-14 | $1,538.73 | $1,622.73 | $84.00 |
| ross_bnkk_20260115 | BNKK | 01-15 | $176.70 | $36.98 | $139.72 |
| ross_tnmg_20260116 | TNMG | 01-16 | -$52.53 | -$376.05 | $323.52 |
| ross_vero_20260116 | VERO | 01-16 | -$81.69 | -$302.65 | $220.96 |
| ross_dcx_20260129 | DCX | 01-29 | $326.99 | $118.26 | $208.73 |
| ross_bnai_20260205 | BNAI | 02-05 | $185.26 | $66.70 | $118.56 |
| ross_uoka_20260209 | UOKA | 02-09 | $279.50 | $244.94 | $34.56 |

## Files to Examine

| File | Purpose |
|------|---------|
| `nexus2/api/routes/warrior_sim_routes.py` | Sequential batch runner + `load_historical_test_case` |
| `nexus2/adapters/simulation/sim_context.py` | Concurrent runner: `SimContext.create()`, `load_case_into_context()` |
| `nexus2/domain/automation/warrior_engine.py` | Engine entry logic, `apply_settings_to_config`, saved settings |
| `nexus2/domain/automation/warrior_monitor.py` | Position monitoring, exit evaluation |
| `nexus2/db/warrior_db.py` | Trade logging, query, purge functions |
| `nexus2/adapters/simulation/mock_broker.py` | MockBroker order/position tracking |

---

## Claims to Investigate (C1–C5)

### C1: Shared Engine State in Sequential Runner

The sequential runner reuses the **global singleton** `WarriorEngine` (via `get_engine()`). The concurrent runner creates a **fresh engine per case** via `SimContext.create()`.

**Investigate**: What engine state beyond `_watchlist`, `_pending_entries`, `_symbol_fails`, and monitor fields could persist between sequential cases?

Focus on:
- `engine.stats` — does it accumulate across cases?
- `engine._last_scan_started` / `engine._last_scan_result` — stale scan state?
- `engine.scanner` — any internal state in the scanner?
- `engine.config` — does `apply_settings_to_config` run per-case or once at startup?

```powershell
Select-String -Path "nexus2\domain\automation\warrior_engine.py" -Pattern "self\._" -Context 0,0 | Select-Object -First 40
```

```powershell
# Check what state load_historical_test_case resets vs what it doesn't
Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "\.clear\(\)|engine\." -Context 1,1 | Select-Object -First 30
```

---

### C2: Wall-Clock Throttle Divergence

Both runners throttle `update_candidate_technicals` using `time.time()` (wall-clock). In headless batch mode, bars replay in <1s — so technicals may only compute once per case. But the sequential runner's `_last_tech_update_ts` could carry over between cases.

**Investigate**: Is `_last_tech_update_ts` (or equivalent) reset between sequential cases?

```powershell
Select-String -Path "nexus2\domain\automation\warrior_engine.py" -Pattern "tech_update|throttle|time\.time" -Context 2,2
```

```powershell
# Check if the concurrent runner has a different throttle path
Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "tech_update|throttle" -Context 2,2
```

---

### C3: Trade DB Contamination Between Sequential Cases

The sequential runner calls `purge_sim_trades()` before each case (L1379-1383). The concurrent runner uses in-memory SQLite per ProcessPoolExecutor worker.

**Investigate**: 
- Does `purge_sim_trades()` actually delete ALL sim trades, or only specific ones?
- Could trades from case N survive the purge and affect case N+1's P&L query?
- How are trades queried after each case to compute `realized_pnl`?

```powershell
Select-String -Path "nexus2\db\warrior_db.py" -Pattern "purge_sim_trades" -Context 5,15
```

```powershell
# Check how trades are queried in the batch loop after each case
Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "realized_pnl|get_.*trades|warrior_db" -Context 2,2
```

---

### C4: Callback Wiring Differences

Sequential: re-wires callbacks on the GLOBAL engine/monitor each case.  
Concurrent: creates fresh engine + monitor with fresh callbacks via `load_case_into_context()`.

**Investigate**: Are there callbacks in the sequential path that reference stale closures from a previous case?

```powershell
# Sequential callback wiring
Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "_submit_order|_get_quote|_execute_exit|_get_positions" -Context 1,1
```

```powershell
# Concurrent callback wiring
Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "_submit_order|_get_quote|_execute_exit|_get_positions" -Context 1,1
```

---

### C5: MockBroker `initial_cash` and Reset Completeness

Sequential: creates MockBroker once with `initial_cash=25000` (L736), then calls `broker.reset()` per case.  
Concurrent: creates fresh `MockBroker(initial_cash=100_000)` per case.

**Investigate**: 
- What does `broker.reset()` actually clear? Does it reset ALL state?
- Does `initial_cash` difference (25K vs 100K) affect position sizing or buying power?

```powershell
Select-String -Path "nexus2\adapters\simulation\mock_broker.py" -Pattern "def reset" -Context 2,15
```

---

## Pattern to Look For

The 13 converging cases share a characteristic — they likely don't depend on any state that differs between runners. The 9 divergent cases somehow hit a code path where the sequential runner's shared state affects the outcome.

**Key question**: BATL 01-26 has the LARGEST divergence (-$176 vs -$1,730). Why? Is it because BATL is the 3rd case in the batch (after LCFY + PAVM), so accumulated state has more impact?

## Report

Write findings to `nexus2/phase9_audit_report.md`.
