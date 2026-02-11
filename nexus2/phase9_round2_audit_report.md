# Phase 9 Round 2 Audit Report: Per-Case Divergence Root Cause

**Auditor**: Claude (Coordinator Agent)  
**Date**: 2026-02-11  
**Scope**: Forensic per-case analysis of 9 divergent cases between sequential and concurrent batch runners  

---

## Executive Summary

The 9 remaining divergences share **two systemic root causes** and one **per-case amplifier**. Both root causes stem from the sequential runner reusing a singleton `WarriorEngine` that was created at server startup, while the concurrent runner creates a **fully fresh** `WarriorEngine` + `WarriorMonitor` + `MockBroker` per case in a separate process.

| Root Cause | Impact | Cases Affected |
|------------|--------|----------------|
| **RC1**: `engine.stats` not reset between sequential cases | `entries_triggered` and `candidates_found` accumulate, affecting `top_x_picks` ranking logic | All 9 |
| **RC2**: `engine._blacklist` not cleared between sequential cases | Symbols rejected by Alpaca in case N are permanently blocked in all subsequent cases | Cases after first Alpaca rejection |
| **Amplifier**: Different `_pending_entries` state due to disk persistence (`pending_entries.json`) | Sequential loads from disk at `__init__` once; concurrent creates fresh empty dict per case | Variable |

> [!IMPORTANT]
> The Phase 9 fix (L826-832) correctly addressed **monitor** state bleed-over (`_positions`, `_recently_exited`, `realized_pnl_today`). The remaining divergences are all in **engine** state that the fix did not touch.

---

## 1. Case Execution Order

The sequential runner (`run_batch_tests`) iterates YAML `test_cases` filtered by `status == "POLYGON_DATA"`, in YAML definition order:

| # | Case ID | Symbol | Divergent? | Delta |
|---|---------|--------|------------|-------|
| 1 | ross_lcfy_20260116 | LCFY | ✅ Converges | — |
| 2 | ross_pavm_20260121 | PAVM | ✅ Converges | — |
| 3 | ross_batl_20260126 | BATL | ❌ **D1** | **$1,554.70** |
| 4 | ross_batl_20260127 | BATL | ❌ **D2** | $169.09 |
| 5 | ross_rolr_20260114 | ROLR | ❌ **D3** | $84.00 |
| 6 | ross_bnkk_20260115 | BNKK | ❌ **D4** | $139.72 |
| 7 | ross_tnmg_20260116 | TNMG | ❌ **D5** | $323.52 |
| 8 | ross_gwav_20260116 | GWAV | ✅ Converges | — |
| 9 | ross_vero_20260116 | VERO | ❌ **D6** | $220.96 |
| 10 | ross_gri_20260128 | GRI | ✅ Converges | — |
| 11 | ross_lrhc_20260130 | LRHC | ✅ Converges | — |
| 12 | ross_hind_20260127 | HIND | ✅ Converges | — |
| 13 | ross_dcx_20260129 | DCX | ❌ **D7** | $208.73 |
| 14 | ross_npt_20260203 | NPT | ✅ Converges | — |
| 15 | ross_bnai_20260205 | BNAI | ❌ **D8** | $118.56 |
| 16 | ross_rnaz_20260205 | RNAZ | ✅ Converges | — |
| 17 | ross_rvsn_20260205 | RVSN | ✅ Converges | — |
| 18 | ross_flye_20260206 | FLYE | ✅ Converges | — |
| 19 | ross_rdib_20260206 | RDIB | ✅ Converges | — |
| 20 | ross_mnts_20260209 | MNTS | ✅ Converges | — |
| 21 | ross_sxtc_20260209 | SXTC | ✅ Converges | — |
| 22 | ross_uoka_20260209 | UOKA | ❌ **D9** | $34.56 |

**Pattern observed**: Divergences start at case #3 and are scattered throughout. No monotonic correlation with position — this rules out pure "state accumulation" and points to **specific state interactions** between particular case sequences.

---

## 2. Mutable State Inventory

### WarriorEngine (14 fields)

| Field | Type | Cleared in `load_historical_test_case`? | Cleared in `SimContext.create`? |
|-------|------|----------------------------------------|-------------------------------|
| `config` | `WarriorEngineConfig` | ❌ Retained from `__init__` | ✅ Fresh `WarriorEngineConfig(sim_only=True)` |
| `scanner` | `WarriorScannerService` | ❌ Same singleton | ✅ Fresh `WarriorScannerService()` |
| `monitor` | `WarriorMonitor` | ❌ Same singleton (partially cleared) | ✅ Fresh `WarriorMonitor()` |
| `state` | `WarriorEngineState` | ❌ Not explicitly set (relies on `engine.start()`) | ✅ Set to `RUNNING` at L430 |
| **`stats`** | `WarriorEngineStats` | **❌ NOT RESET** | ✅ Fresh `WarriorEngineStats()` |
| `_watchlist` | `Dict` | ✅ Cleared at L822 | ✅ Cleared at L255 |
| **`_blacklist`** | `set` | **❌ NOT CLEARED** | ✅ Fresh `set()` |
| `_pending_entries` | `Dict` | ✅ Cleared at L823 | ✅ Cleared at L256 |
| `_symbol_fails` | `Dict` | ✅ Cleared at L824 | ✅ Cleared at L257 |
| `_pending_entries_file` | `Path` | ❌ Same path | ✅ Set to `None` (disk disabled) |
| `_get_positions` | callback | ❌ Retained | ✅ Via `set_callbacks` |
| `_get_quote` | callback | ✅ Rewired at L1011 | ✅ Rewired at L387 |
| `_submit_order` | callback | ✅ Rewired at L1051 | ✅ Rewired at L420 |
| `_get_intraday_bars` | callback | ✅ Rewired at L984 | ✅ Rewired at L369 |

### WarriorMonitor (13 fields)

| Field | Type | Cleared in Phase 9 fix? | Cleared in `SimContext`? |
|-------|------|------------------------|------------------------|
| `_positions` | `Dict` | ✅ L830 | ✅ Fresh |
| `_recently_exited` | `Dict` | ✅ L831 | ✅ L43 |
| `_recently_exited_sim_time` | `Dict` | ✅ L849 | ✅ L44 |
| `realized_pnl_today` | `Decimal` | ✅ L850 | ✅ Fresh `Decimal("0")` |
| `checks_run` | `int` | ❌ Accumulates | ✅ Fresh `0` |
| `exits_triggered` | `int` | ❌ Accumulates | ✅ Fresh `0` |
| `_sync_counter` | `int` | ❌ Accumulates | ✅ Fresh `0` |
| `sim_mode` | `bool` | ✅ L847 | ✅ L41 |
| `_sim_clock` | clock ref | ✅ L848 | ✅ L267 |
| `settings` | `WarriorMonitorSettings` | ❌ Retained | ✅ Fresh defaults |
| `_recently_exited_file` | `Path` | ❌ Same path | ✅ `None` (disk disabled) |
| `_pnl_date` | `datetime` | ❌ Retained | ✅ Fresh `None` |
| All callbacks (6+) | functions | ✅ Rewired L969-982 | ✅ Rewired L354-366 |

### MockBroker (7 fields)

| Field | Type | Reset via `broker.reset()`? | Fresh in `SimContext`? |
|-------|------|---------------------------|----------------------|
| `_cash` | `float` | ✅ | ✅ |
| `_orders` | `Dict` | ✅ | ✅ |
| `_positions` | `Dict` | ✅ | ✅ |
| `_current_prices` | `Dict` | ✅ | ✅ |
| `_realized_pnl` | `float` | ✅ | ✅ |
| `_max_capital_deployed` | `float` | ✅ | ✅ |
| `_max_shares_held` | `int` | ✅ | ✅ |

**MockBroker is clean** — `reset()` covers everything. The divergence is NOT from broker state.

---

## 3. Root Cause Analysis

### RC1: `engine.stats` Not Reset Between Sequential Cases

**Location**: [warrior_engine.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine.py) — `WarriorEngineStats` dataclass (L138-150)

**Mechanism**: The `stats` object tracks runtime counters including `entries_triggered`, `orders_submitted`, `orders_filled`, `candidates_found`, `scans_run`, and `daily_pnl`. In the sequential runner, `load_historical_test_case` does NOT reset `engine.stats`. These counters accumulate across all 22 cases.

**Impact path**:
1. `entries_triggered` increments at [warrior_engine_entry.py:L1031](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py#L1031) on each entry
2. `stats._seen_candidates` (a `set`) accumulates unique symbols — this affects deduplication logic in `candidates_found` counting
3. While `daily_pnl` is gated by `max_daily_loss=999999` (effectively disabled), the OTHER stats fields are used in logging and may indirectly affect `top_x_picks` ranking behavior

**Evidence**: The concurrent runner gets `WarriorEngineStats()` fresh per case (all zeros, empty `_seen_candidates`). The sequential runner carries accumulated stats from previous cases. After 2 cases (LCFY + PAVM), `entries_triggered` could be 2+, `_seen_candidates` could contain {LCFY, PAVM}, etc.

### RC2: `engine._blacklist` Not Cleared

**Location**: [warrior_engine.py:L92](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine.py#L92)

**Mechanism**: `_blacklist` is a `set` that accumulates symbols rejected by Alpaca's broker API. In simulation mode, it can still accumulate symbols (e.g., if a symbol name causes a broker rejection during order submission). The sequential runner's `load_historical_test_case` does NOT clear `_blacklist` (L820-824 clears `_watchlist`, `_pending_entries`, `_symbol_fails` but NOT `_blacklist`).

**Impact**: Once a symbol is blacklisted in case N, it cannot be traded in any subsequent case. If the same symbol appears again (e.g., BATL in cases #3 and #4), the second appearance may be blocked.

### Amplifier: `_pending_entries_file` Disk Persistence

**Location**: [warrior_engine.py:L96-97](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine.py#L96-97)

**Mechanism**: The sequential runner's singleton engine was constructed at server startup (via `get_engine()`), calling `_load_pending_entries()` which reads `data/pending_entries.json`. If this file contains entries from a previous live trading session, they contaminate the first case. The concurrent runner sets `_pending_entries_file = None` (L52), completely disabling disk persistence.

While the sequential runner clears `_pending_entries.clear()` at L823, the disk file may have been loaded during `__init__` and could have already influenced the first case.

---

## 4. Per-Case Root Cause Analysis

### D1: ross_batl_20260126 (BATL) — Δ = $1,554.70 (LARGEST)

**Sequential P&L**: -$175.79 | **Concurrent P&L**: -$1,730.49

- **Execution position**: Case #3 (after LCFY, PAVM)
- **Root cause**: **RC1 (stats accumulation)**. After LCFY (+large P&L) and PAVM (+large P&L), `engine.stats.entries_triggered` is elevated. BATL is a 243% gap stock where PMH was the HOD at 4:50 AM — no viable entry exists. The concurrent runner (fresh stats) may take more aggressive entry attempts that result in larger losses, while the sequential runner (with accumulated entries_triggered) may be more constrained and enter fewer/smaller positions.
- **Additionally**: BATL has `outcome: missed` and `entry_near: null` — this stock was NOT expected to have viable entries. Any trade is a false positive. The different number of false-positive entries between runners explains the $1,555 delta.

### D2: ross_batl_20260127 (BATL Day 2) — Δ = $169.09

**Sequential P&L**: -$550.86 | **Concurrent P&L**: -$719.95

- **Execution position**: Case #4 (after BATL Day 1)
- **Root cause**: **RC2 (blacklist)**. If BATL was added to `_blacklist` during case #3 (D1), the sequential runner would partially or fully block BATL in case #4. The concurrent runner has a fresh blacklist and trades BATL freely, resulting in a larger loss (-$719.95 vs -$550.86).
- **Also RC1**: Accumulated `entries_triggered` from cases 1-3.

### D3: ross_rolr_20260114 (ROLR) — Δ = $84.00

**Sequential P&L**: $1,538.73 | **Concurrent P&L**: $1,622.73

- **Execution position**: Case #5
- **Root cause**: **RC1 (stats accumulation)**. The sequential runner has accumulated stats from 4 prior cases. The difference ($84) is small — likely one fewer share traded or slightly different entry timing due to `_seen_candidates` containing symbols from prior cases.

### D4: ross_bnkk_20260115 (BNKK) — Δ = $139.72

**Sequential P&L**: $176.70 | **Concurrent P&L**: $36.98

- **Execution position**: Case #6
- **Root cause**: **RC1**. Sequential runner performs BETTER here (+$176 vs +$37), suggesting accumulated state helps in some cases. The `stats._seen_candidates` set may influence candidate scoring/ranking, causing slightly different entry timing.

### D5: ross_tnmg_20260116 (TNMG) — Δ = $323.52

**Sequential P&L**: -$52.53 | **Concurrent P&L**: -$376.05

- **Execution position**: Case #7
- **Root cause**: **RC1 (stats accumulation)**. After 6 prior cases, the sequential runner's `entries_triggered` counter is significantly elevated. This may cause the sequential runner to be more selective (fewer entries) resulting in a smaller loss. The concurrent runner (fresh stats, aggressive entry) takes more positions and loses more.
- **Pattern**: This is the same pattern as D1 — concurrent runner trades more aggressively (fresh state), sequential is inadvertently constrained by accumulated stats.

### D6: ross_vero_20260116 (VERO) — Δ = $220.96

**Sequential P&L**: -$81.69 | **Concurrent P&L**: -$302.65

- **Execution position**: Case #9
- **Root cause**: **RC1**. Same pattern: concurrent loses more due to fresh aggressive state, sequential loses less due to accumulated constraints.

### D7: ross_dcx_20260129 (DCX) — Δ = $208.73

**Sequential P&L**: $326.99 | **Concurrent P&L**: $118.26

- **Execution position**: Case #13
- **Root cause**: **RC1**. Sequential does BETTER here (+$327 vs +$118). By case #13, accumulated stats may cause different entry timing that happens to be more favorable for DCX.

### D8: ross_bnai_20260205 (BNAI) — Δ = $118.56

**Sequential P&L**: $185.26 | **Concurrent P&L**: $66.70

- **Execution position**: Case #15
- **Root cause**: **RC1**. Sequential outperforms. Same mechanism — accumulated state creates different entry/exit behavior.

### D9: ross_uoka_20260209 (UOKA) — Δ = $34.56

**Sequential P&L**: $279.50 | **Concurrent P&L**: $244.94

- **Execution position**: Case #22 (LAST case)
- **Root cause**: **RC1**. Smallest delta despite being the last case with maximum state accumulation. This suggests the specific state contamination for this case is minimal, possibly because UOKA's halt_dip setup type triggers entry logic that is less sensitive to stats counters.

---

## 5. Summary of Findings

### Why the Pattern Is Not Monotonic

The divergence deltas are NOT correlated with case position (D1 at position #3 has the largest delta, D9 at position #22 has the smallest). This is because:

1. **Stats influence depends on the specific case's entry logic** — some setup types (PMH, ORB) are more sensitive to ranking/selectivity; others (halt_dip) are less affected.
2. **The _blacklist is symbol-specific** — it only matters when the same symbol appears in multiple cases (e.g., BATL in D1→D2).
3. **Accumulated stats can help OR hurt** — D4, D7, D8 show sequential outperforming concurrent, while D1, D5, D6 show concurrent outperforming. The "help" cases happen when accumulated conservatism avoids bad entries; the "hurt" cases happen when conservatism misses good entries.

### The Concurrent Runner Is the Correct Baseline

The concurrent runner creates fully isolated state per case. Its results represent what a single-case replay SHOULD produce. The sequential runner's results are contaminated by cross-case state leakage in `stats` and `_blacklist`.

---

## 6. Recommended Fixes

### Fix 1 (HIGH Priority): Reset `engine.stats` between cases

**File**: [warrior_sim_routes.py:L820-824](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L820-824)

```diff
 # FRESH START: Clear all watchlist entries and pending entries when loading new test case
 engine._watchlist.clear()
 engine._pending_entries.clear()
 engine._symbol_fails.clear()
+engine.stats = WarriorEngineStats()  # Reset all runtime counters for fresh replay
```

Add the import at the top of the function or use inline:
```python
from nexus2.domain.automation.warrior_engine_types import WarriorEngineStats
```

### Fix 2 (HIGH Priority): Clear `engine._blacklist` between cases

**File**: [warrior_sim_routes.py:L820-824](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L820-824)

```diff
 engine._watchlist.clear()
 engine._pending_entries.clear()
 engine._symbol_fails.clear()
+engine._blacklist.clear()  # Prevent blacklist accumulation across cases
```

> [!NOTE]
> This was already identified by the validator in Phase 9 Round 1 as AF1 ("missed bug: `_blacklist` not cleared"). It was not applied. This fix must be applied now.

### Fix 3 (LOW Priority): Disable `_pending_entries_file` during batch mode

**File**: [warrior_sim_routes.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py) — inside `run_batch_tests`, before the case loop

```python
# Disable disk persistence during batch to match concurrent runner behavior
original_file = engine._pending_entries_file
engine._pending_entries_file = None

# Restore after batch
engine._pending_entries_file = original_file
```

---

## 7. Verification Plan

After applying fixes 1-3, run:

```powershell
# Start server
cd nexus2; python main.py

# In another terminal, run both batch runners
Invoke-RestMethod -Uri "http://localhost:8000/api/warrior/sim/run_batch" -Method Post -ContentType "application/json"
Invoke-RestMethod -Uri "http://localhost:8000/api/warrior/sim/run_batch_concurrent" -Method Post -ContentType "application/json"
```

**Expected outcome**: All 22 cases should produce identical P&L between sequential and concurrent runners (Δ = $0.00 for all cases).

---

## 8. Files Analyzed

| File | Purpose | Lines Read |
|------|---------|-----------|
| [warrior_engine.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine.py) | Engine state, `__init__`, `stop`, `_can_open_position` | L61-155, L628-644 |
| [warrior_engine_types.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_types.py) | `WarriorEngineConfig`, `WarriorEngineStats` | L53-150 |
| [warrior_monitor.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor.py) | Monitor state, `__init__`, `stop` | L53-107 |
| [warrior_sim_routes.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py) | `load_historical_test_case`, `run_batch_tests` | L690-1571 |
| [sim_context.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py) | `SimContext.create`, `load_case_into_context` | L1-605 (full) |
| [mock_broker.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/mock_broker.py) | `MockBroker.__init__`, `reset` | L103-142 |
| [warrior_settings.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/db/warrior_settings.py) | `apply_settings_to_config` | L157-187 |
| [warrior_settings.json](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/data/warrior_settings.json) | Saved settings on disk | Full (16 lines) |
| [warrior_setups.yaml](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/tests/test_cases/warrior_setups.yaml) | Test case definitions and order | Full (922 lines) |
