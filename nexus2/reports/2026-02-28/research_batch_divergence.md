# Batch Test Divergence: Root Cause Analysis

**Agent:** Backend Planner  
**Date:** 2026-02-28  
**Type:** Runtime divergent behavior investigation  

---

## Executive Summary

The $137K PnL divergence is caused by the `ProcessPoolExecutor(max_workers=min(cases, cpu_count(), 8))` at `sim_context.py:972`. On the **1-core VPS**, `max_workers=1`, meaning all 38 cases run **sequentially in the same subprocess**. On the **10-core local**, each case gets its own fresh process. This introduces two classes of bugs:

1. **Shared DB contamination:** Guard block events written to the shared `nexus.db` accumulate across sequential cases (explains 125x guard block count differences).
2. **Wall-clock leakage in exit logic:** `datetime.now()` used in exit module (candle-under-candle 5m bucket, spread/topping grace periods) produces different behavior at different real-world times of day.

---

## Root Cause #1: Guard Block DB Cross-Contamination (REPORTING + LOGGING)

**Severity:** HIGH (explains guard_block_count divergence; partially affects PnL via dedup)

### Evidence

**Finding:** Guard blocks are written to shared `nexus.db` (not per-process in-memory DB)  
**File:** [trade_event_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/trade_event_service.py#L1036-L1044)  
**Code:**
```python
self._log_event(
    strategy="WARRIOR",
    position_id="GUARD_BLOCK",
    symbol=symbol,
    event_type=self.WARRIOR_GUARD_BLOCK,
    ...
)
```

**Finding:** Guard blocks read back from shared DB, filtered only by symbol  
**File:** [sim_context.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L756-L760)  
**Code:**
```python
blocks = db.query(TradeEventModel).filter(
    TradeEventModel.event_type == "GUARD_BLOCK",
    TradeEventModel.symbol == symbol.upper(),
).all()
```

**Finding:** `_trigger_rejection_dedup` dict on singleton persists between sequential cases  
**File:** [trade_event_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/trade_event_service.py#L90-L92)  
**Code:**
```python
# Dedup tracker for trigger rejections: {"SYMBOL_PATTERN": timestamp}
# Prevents redundant events during live trading (5s poll cycles)
self._trigger_rejection_dedup: Dict[str, float] = {}
```

### Analysis

- With `max_workers=1` (VPS), all 38 cases run in the **same subprocess** sequentially
- Each case writes guard block events to the shared `nexus.db` `trade_events` table
- When case N's result is assembled, it queries `trade_events` for `GUARD_BLOCK` by `symbol`
- On VPS: sequential execution means case N sees blocks from cases 1..N-1 too
- On local: parallel execution in separate processes means each sees only its own blocks
- BATL-0126 shows 15,679 blocks local vs 126 VPS — the local number includes accumulated blocks from other processes writing to the same DB file, while VPS shows only that case's own blocks
- Additionally, `_trigger_rejection_dedup` persists across sequential cases on VPS, potentially suppressing legitimate trigger rejection events for subsequent cases using the same symbol+pattern

**PnL Impact:** LOW — guard blocks are queried for **reporting only**, not for trading decisions. The actual guard logic uses in-memory engine state which IS properly reset per case.

---

## Root Cause #2: `datetime.now()` in Exit Module (PnL AFFECTING)

**Severity:** HIGH (directly affects exit timing → PnL)

### Finding 2a: Candle-under-candle 5m bucket uses real clock

**File:** [warrior_monitor_exit.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py#L516-L517)  
**Code:**
```python
et_now = datetime.now(ZoneInfo("America/New_York"))
bucket_start_minute = (et_now.minute // 5) * 5  # e.g., 9:37 → 35
```

**Impact:** During batch test, 5m bucket alignment is determined by real wall clock — different on local (4:00 PM run → minute=0) vs VPS (3:07 PM run → minute=5). This causes the synthetic 5m candle red confirmation check to produce different true/false results per case.

### Finding 2b: Grace periods use `now_utc()` (real clock)

**File:** [warrior_monitor_exit.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py#L285)  
```python
seconds_since_entry = (now_utc() - entry_time).total_seconds()
```

Also at lines 461 (candle-under-candle grace) and 612 (topping tail grace).

**Impact:** On the fast local machine, all 960 simulated minutes process in ~2 seconds real time. Grace periods (e.g., 60 seconds) never activate because real elapsed time is always < grace period. On the slow VPS, a case might process slowly enough that some grace periods actually trigger.

### Finding 2c: Correctly handled in `_check_after_hours_exit`

**File:** [warrior_monitor_exit.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py#L189-L197)

The after-hours exit logic **correctly** checks `monitor._sim_clock` first:
```python
if hasattr(monitor, '_sim_clock') and monitor._sim_clock:
    clock_time = monitor._sim_clock.current_time
    et_now = clock_time.astimezone(ET)
```

This pattern is the correct fix for all other `datetime.now()` usages in this file.

---

## Root Cause #3: ProcessPoolExecutor Bottleneck on 1-Core VPS

**Severity:** MEDIUM (amplifies Root Cause #1 and #2)

### Evidence

**File:** [sim_context.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L972-L974)  
**Code:**
```python
max_workers = min(len(cases), multiprocessing.cpu_count(), 8)
# On 1-core VPS: max_workers = min(38, 1, 8) = 1
# On 10-core local: max_workers = min(38, 10, 8) = 8
```

### Analysis

- VPS gets `max_workers=1` → single subprocess reused for all 38 cases
- This means the subprocess's module-level state persists across all cases:
  - `trade_event_service` singleton (with `_trigger_rejection_dedup` dict)
  - `_simulation_clock` global singleton (overridden by ContextVar, so harmless)
  - `get_session()` → shared `nexus.db` file operations
  - Any other module-level caches imported during execution

---

## What IS Properly Isolated

These components were verified as correctly isolated per case:

| Component | How Isolated | Evidence |
|-----------|-------------|----------|
| **warrior_db** | New in-memory SQLite per `_run_case_sync` call | `sim_context.py:597-600` |
| **SimContext** (engine, broker, clock, monitor) | Fresh `SimContext.create()` per case | `sim_context.py:656` |
| **Engine state** (watchlist, pending entries, fails) | Cleared in `load_case_into_context()` | `sim_context.py:296-300` |
| **Monitor sim_clock** | Wired per case | `sim_context.py:308` |
| **Engine sim_clock** | Wired per case | `sim_context.py:524` |
| **ContextVar sim clock** | Set per case via `set_simulation_clock_ctx()` | `sim_context.py:667` |
| **ContextVar sim mode** | Set per case via `set_sim_mode_ctx()` | `sim_context.py:668` |
| **Monitor _recently_exited** | Reset per case | `sim_context.py:42-44,309` |
| **Monitor _recently_exited_file** | Set to `None` (no disk I/O) | `sim_context.py:42` |
| **Engine _pending_entries_file** | Set to `None` (no disk I/O) | `sim_context.py:62` |
| **Entry guards** | Use `monitor._sim_clock` (correctly wired) | `warrior_entry_guards.py:66-69` |

---

## Questions Answered

### Q1: Does `_get_eastern_time()` use real clock or sim clock?
**CORRECTLY GUARDED.** Entry guards check `engine.monitor._sim_clock` first (line 66-69).

### Q2: Does the concurrent runner's engine have `_sim_clock` set?
**YES.** Both `monitor._sim_clock` (line 308) and `engine._sim_clock` (line 524) are set.

### Q3: Are there guard functions using real clock?
**Entry guards: NO.** Exit logic: **YES** — 3 instances of `datetime.now()` or `now_utc()` in `warrior_monitor_exit.py`.

### Q4: Do persisted configs differ?
**NOT VERIFIED AT RUNTIME.** Both environments load from `load_warrior_settings()` / `load_monitor_settings()`. If the persisted `nexus.db` differs between local and VPS, configs would differ. **Recommend runtime verification.**

### Q5: Non-determinism in concurrent runner?
**YES.** From shared `nexus.db` (guard blocks), `_trigger_rejection_dedup` singleton, and real-clock exit logic.

### Q6: Did concurrency regress on VPS?
**YES — mechanically.** `max_workers=min(cases, cpu_count(), 8)` returns `1` on 1-core VPS. The code always did this; the regression likely corresponds to a VPS downgrade from multi-core to 1-core, or the addition of wall-clock code in the exit module.

### Q7: Why dramatically different guard block counts?
**Root Cause #1.** Guard blocks accumulate in shared `nexus.db`. On VPS (sequential), each case sees only its own + previous cases' blocks. On local (parallel), each process sees only blocks from other processes writing to the same file concurrently — the more processes, the more cross-contamination.

---

## Proposed Fix Priority

| Fix | Impact | Effort | Priority |
|-----|--------|--------|----------|
| #2a: Candle-under-candle sim clock | PnL affecting | Small | **P1** |
| #2b: Grace period → bar count | PnL affecting | Small | **P1** |
| #1: Guard block DB isolation | Reporting accuracy | Medium | **P2** |
| #3: Force min workers > 1 | Performance + isolation | Trivial | **P2** |
| Q4: Verify configs match | Diagnostic | Small | **P2** |

### Fix Details

**Fix #2a:** Replace `datetime.now(ZoneInfo(...))` at `warrior_monitor_exit.py:516` with sim-clock-aware lookup, using the same pattern as `_check_after_hours_exit` (lines 189-197).

**Fix #2b:** Replace `(now_utc() - entry_time).total_seconds()` at lines 285, 461, 612 with `position.candles_since_entry`, using the same pattern as `_check_time_stop` (line 372).

**Fix #1:** Either add `batch_id` to guard block metadata and filter on read, OR redirect guard block logging to per-process in-memory warrior_db.

**Fix #3:** Set `max_workers = max(2, min(...))` to ensure at least 2 workers, providing some process isolation even on 1-core machines.
