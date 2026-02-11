# Phase 8 Audit Validation Report

**Validator:** Audit Validator Agent  
**Source Report:** `nexus2/phase8_investigation_report.md`  
**Date:** 2026-02-10  

---

## Summary

| Category | Total | PASS | FAIL | Notes |
|----------|-------|------|------|-------|
| Claim Verifications (F1-F7) | 7 | 7 | 0 | All claims independently confirmed |
| Adversarial Investigations (A1-A3) | 3 | — | — | 2 NEW findings discovered |

**Overall Rating: HIGH** — All claims verified. Adversarial investigations found 2 additional contamination vectors not covered in the original report.

---

## Claim Verifications

### F1: `log_warrior_entry()` accepts `batch_run_id` but no caller passes it

**Result: ✅ PASS**

| Evidence | Detail |
|----------|--------|
| Function signature | [warrior_db.py:L262-284](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/db/warrior_db.py#L262-L284) — `batch_run_id: str = None` parameter exists |
| Caller 1 | [warrior_engine_entry.py:L1201](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py#L1201) — No `batch_run_id` passed |
| Caller 2 | [warrior_entry_execution.py:L462](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_execution.py#L462) — No `batch_run_id` passed |
| Caller 3 | [warrior_monitor_sync.py:L403](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_sync.py#L403) — No `batch_run_id` passed |
| Caller 4 | [warrior_broker_routes.py:L472](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_broker_routes.py#L472) — No `batch_run_id` passed |

**Command:** `rg "log_warrior_entry(" --include "*.py" nexus2/` → 0 of 4+ production callers pass `batch_run_id`.

> [!IMPORTANT]
> The investigation report cited "9 callers" but the actual count is **4 distinct production callers** of `warrior_db.log_warrior_entry()`. There is also a separate `trade_event_service.log_warrior_entry()` (different function, logs to file/events, not DB). The claim's core finding is correct regardless of count.

---

### F2: All 8 query functions lack `batch_run_id` / `is_sim` filtering

**Result: ✅ PASS**

| Function | Location | Filters Used | Missing |
|----------|----------|-------------|---------|
| `get_open_warrior_trades()` | L410-430 | `status.in_(active)` | `batch_run_id`, `is_sim` |
| `get_warrior_trade_by_symbol()` | L433-458 | `symbol`, `status.in_` | `batch_run_id`, `is_sim` |
| `get_all_warrior_trades()` | L882-920 | `status` (optional) | `batch_run_id`, `is_sim` |
| `get_trade_by_id()` | L923-927 | `id` | `batch_run_id`, `is_sim` |
| `get_recent_closed_trades()` | L930-945 | `status=closed` | `batch_run_id`, `is_sim` |
| `get_warrior_trade_for_recovery()` | (grep confirmed) | `symbol`, `entry_price` | `batch_run_id`, `is_sim` |
| `check_scaling_positions()` | (grep confirmed) | `status=scaling` | `batch_run_id`, `is_sim` |
| `close_orphaned_trades()` | (grep confirmed) | `status=open`, `symbol NOT IN active` | `batch_run_id`, `is_sim` |

**Verified**: Every query function operates on the full table without scoping.

---

### F3: `purge_batch_trades()` has zero production callers

**Result: ✅ PASS**

| Evidence | Detail |
|----------|--------|
| Function definition | [warrior_db.py:L794-800](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/db/warrior_db.py#L794-L800) |
| grep result | `rg "purge_batch_trades" --include "*.py"` → only the definition + import in `warrior_db.py`, zero call sites |

**Confirmed dead code.**

---

### F4: EOD close path uses unscoped `get_warrior_trade_by_symbol()`

**Result: ✅ PASS**

| Path | Location | Code |
|------|----------|------|
| Concurrent runner | [sim_context.py:L501-506](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L501-L506) | `trade = get_warrior_trade_by_symbol(pos_symbol)` — no `batch_run_id` |
| Sequential runner | [warrior_sim_routes.py:L1428-1429](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L1428-L1429) | `trade = get_warrior_trade_by_symbol(pos_symbol)` — no `batch_run_id` |

**Impact**: If two concurrent cases trade the same symbol, EOD close could retrieve the wrong trade's DB record and log exit against it.

---

### F5: `EntryValidationLogModel` lacks `batch_run_id`

**Result: ✅ PASS**

| Evidence | Detail |
|----------|--------|
| Model definition | [warrior_db.py:L142-195](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/db/warrior_db.py#L142-L195) |
| `is_sim` present | L191: `is_sim = Column(Boolean, default=True)` |
| `batch_run_id` absent | No such column exists in the model |

**Additional finding**: `log_entry_validation()` at [L972-1007](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/db/warrior_db.py#L972-L1007) also has no `batch_run_id` parameter.

---

### F6: `_log_to_file()` has no file locking

**Result: ✅ PASS**

| Evidence | Detail |
|----------|--------|
| Code | [trade_event_service.py:L86-101](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/trade_event_service.py#L86-L101) |
| Pattern | `with open(self._warrior_log_path, "a") as f: f.write(line)` |
| Locking | None — no `fcntl.flock`, `msvcrt.locking`, or `portalocker` usage |

**Risk**: Medium. In concurrent `ProcessPoolExecutor` mode, multiple processes may interleave writes. However, since each process gets its own file handle and lines are short, corruption likelihood is low on most OS/filesystem combinations, but not zero.

---

### F7: Sequential runner post-query `is_sim` filter

**Result: ✅ PASS**

| Evidence | Detail |
|----------|--------|
| Code | [warrior_sim_routes.py:L1461-1471](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L1461-L1471) |
| Query | `get_all_warrior_trades(limit=100, status_filter="closed")` — no `is_sim` in SQL |
| Post-filter | `if wt.get("is_sim"):` at L1471 — Python-side filter after full table scan |

**Impact**: Fetches all closed trades from all runs, then filters in Python. This works functionally for the sequential runner (since `purge_sim_trades` clears between runs) but is wasteful and would be incorrect if purge was skipped.

---

## Adversarial Investigations

### A1: Hidden In-Memory DB Dependencies Mid-Trade

**Result: 🔍 2 NEW FINDINGS**

Beyond the 8 query functions verified in F2, the following mid-trade DB lookups also use unscoped queries:

| Location | Function | Call | Risk |
|----------|----------|------|------|
| [warrior_engine_entry.py:L866](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py#L866) | `_scale_into_existing_position()` | `get_warrior_trade_by_symbol(symbol)` | Could scale into wrong batch's trade |
| [warrior_entry_execution.py:L327](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_execution.py#L327) | `scale_into_existing_position()` | `get_warrior_trade_by_symbol(symbol)` | Duplicate of above (extracted copy) |
| [warrior_monitor_sync.py:L108-110](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_sync.py#L108-L110) | `_check_pending_exit_status()` | `get_warrior_trade_by_symbol(symbol, status="pending_exit")` | Could match wrong batch's pending exit |
| [warrior_broker_routes.py:L537](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_broker_routes.py#L537) | `cancel_orders_for_symbol()` | `get_warrior_trade_by_symbol(symbol)` | Could update wrong trade's status |

> [!WARNING]
> The scale-in path is particularly dangerous: if two concurrent batch cases trade the same symbol, `_scale_into_existing_position` could look up and modify another case's trade record.

---

### A2: Additional `log_warrior_entry()` Callers Not In Report

**Result: 🔍 2 callers missed by investigation report**

The report cited callers in `warrior_engine_entry.py` and `trade_event_service.py`, but missed:

| Caller | Location | Context | Passes `batch_run_id`? |
|--------|----------|---------|----------------------|
| `_recover_position()` | [warrior_monitor_sync.py:L403](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_sync.py#L403) | External position recovery | ❌ No |
| `backfill_warrior_trades()` | [warrior_broker_routes.py:L472](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_broker_routes.py#L472) | Manual backfill endpoint | ❌ No |

These are less critical (recovery and backfill are live-only paths, not batch), but they contribute to the "no caller passes `batch_run_id`" finding.

---

### A3: ProcessPoolExecutor State Isolation

**Result: 🔍 CONFIRMED — True process isolation with shared DB risk**

| Factor | Finding |
|--------|---------|
| Start method | Windows defaults to `spawn` — each child process gets a fresh Python interpreter |
| In-memory state | Fully isolated. Each process creates its own `SimContext` with independent `WarriorEngine`, `MockBroker`, `SimulationClock` |
| SQLAlchemy engine | Module-level singleton at [warrior_db.py:L26-30](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/db/warrior_db.py#L26-L30). On `spawn`, each child process re-imports the module and creates its own engine |
| SQLite file | Shared `data/warrior.db` at L22. All processes read/write to the same file |
| WAL mode | Enabled (L33-38). Allows concurrent readers during writes but does NOT prevent logical data contamination |

> [!CAUTION]
> **WAL mode solves write-lock errors but NOT data isolation.** Each process can successfully write trades to `warrior.db`, but without `batch_run_id` scoping in queries (F2), any process can read another process's trades. The `ProcessPoolExecutor` provides memory isolation but the shared SQLite file is the contamination channel.

---

## Validation Verdict

| # | Claim | Result | Confidence |
|---|-------|--------|------------|
| F1 | `batch_run_id` never passed | ✅ PASS | HIGH |
| F2 | 8 queries unscoped | ✅ PASS | HIGH |
| F3 | `purge_batch_trades` dead code | ✅ PASS | HIGH |
| F4 | EOD close cross-contamination | ✅ PASS | HIGH |
| F5 | `EntryValidationLogModel` no `batch_run_id` | ✅ PASS | HIGH |
| F6 | File append no locking | ✅ PASS | HIGH |
| F7 | Post-query `is_sim` filter | ✅ PASS | HIGH |
| A1 | Hidden DB callers | 🔍 2 NEW | Scale-in + pending exit paths |
| A2 | Missed `log_warrior_entry` callers | 🔍 2 NEW | Recovery + backfill paths |
| A3 | ProcessPoolExecutor isolation | ✅ CONFIRMED | Shared SQLite = contamination channel |

### Corrections to Investigation Report

1. **Caller count**: Report says "9 callers" for `log_warrior_entry`. Actual count of `warrior_db.log_warrior_entry()` callers is **4** (2 in entry paths + 1 recovery + 1 backfill). The discrepancy likely comes from confusing `trade_event_service.log_warrior_entry()` (a different function) with the DB function.
2. **Missing contamination vectors**: The scale-in path (`_scale_into_existing_position`) and broker sync path (`_check_pending_exit_status`) both perform unscoped `get_warrior_trade_by_symbol()` lookups that could cause cross-batch contamination.

### Overall Assessment

**The investigation report's core findings are correct and independently verified.** The trade contamination issue is real and systemic. The additional vectors found in adversarial investigation reinforce the severity — the problem is even wider than the report documented.
