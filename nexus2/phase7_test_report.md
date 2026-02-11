# Phase 7 Test Report

**Date**: 2026-02-10 12:57 ET  
**Tester**: Testing Specialist (AI)  
**Server**: 100.113.178.7:8000

---

## Results Summary

| Test | Criteria | Result | Verdict |
|------|----------|--------|---------|
| 1. Performance Benchmark | concurrent < 30s | 33.0s | ❌ FAIL |
| 2. P&L Fidelity | seq == conc for all cases | ROLR diverged | ❌ FAIL |
| 3. Live Safety | phantom check guarded by `sim_only` | Properly guarded | ✅ PASS |

---

## Test 1: Performance Benchmark

**Concurrent endpoint**: `/warrior/sim/run_batch_concurrent`  
**Wall time**: 33.0s (threshold: <30s)

| Case | Bars | Runtime |
|------|------|---------|
| ross_rolr_20260114 | 653 | 9.73s |
| ross_gri_20260128 | 563 | 15.47s |
| ross_hind_20260127 | 612 | 7.50s |

**Server-reported total**: 32.83s  
**Sequential comparison**: 34.2s (sequential was only ~1s slower)

> [!WARNING]
> Concurrent runtime (33s) barely exceeds the 30s threshold and is nearly identical to sequential (34s). The `ProcessPoolExecutor` parallelism is not producing the expected speedup — cases appear to still run serially or the GIL bottleneck was not the primary issue.

---

## Test 2: P&L Fidelity

| Case ID | Sequential P&L | Concurrent P&L | Match |
|---------|---------------|----------------|-------|
| ross_rolr_20260114 | $1,538.73 | $1,622.73 | ❌ FAIL |
| ross_hind_20260127 | $0.00 | $0.00 | ✅ PASS |
| ross_gri_20260128 | $201.41 | $201.41 | ✅ PASS |

**ROLR delta**: $84.00 difference

> [!CAUTION]
> The ROLR case produces different P&L between sequential and concurrent runs. This indicates a **non-determinism or state leakage** issue. Possible causes:
> - Database not fully purged between runs (trades from prior batch accumulating)
> - Shared mutable state affecting trade decisions (different trade taken/skipped)
> - `batch_run_id` isolation not filtering correctly in P&L aggregation

**Additional observation**: The sequential ROLR result includes a massive trades array (30+ entries) where most have `exit_price: null` and `pnl: 0.0`. This suggests **orphaned trades from previous runs** are being included in the response. The concurrent endpoint returned `trades: []` for ROLR despite showing $1,622.73 realized P&L — the trades exist in the DB but aren't being returned in the response.

---

## Test 3: Live Safety

**File**: [warrior_engine_entry.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py#L358-L388)

```python
# Line 362-363: Phantom quote check correctly guarded
is_sim = getattr(engine.config, 'sim_only', False)
if not is_sim:
    skip_phantom_check = False
    # ... phantom quote validation runs ONLY in live mode
```

**Verdict**: ✅ PASS — Phantom quote check is **skipped in sim mode** and **runs in live mode**. The guard uses `engine.config.sim_only`, not a global flag, so it's safe per-engine.

---

## Issues Found

### Bug 1: ROLR P&L Divergence (Sequential vs Concurrent)
- **Location**: `sim_context.py` / `warrior_db.py` (batch isolation)
- **Expected**: Identical realized_pnl for same case on both endpoints
- **Actual**: $1,538.73 (seq) vs $1,622.73 (conc) — Δ $84.00
- **Strategy**: Warrior
- **Evidence**: Test output above. Likely cause: incomplete `purge_batch_trades()` or `batch_run_id` not filtering correctly.

### Bug 2: No Parallelism Speedup
- **Location**: `sim_context.py` `run_batch_concurrent()`
- **Expected**: ~15s concurrent (max single-case time) vs ~34s sequential
- **Actual**: 33s concurrent vs 34s sequential — essentially no speedup
- **Strategy**: N/A (infrastructure)
- **Evidence**: Wall times above. The `ProcessPoolExecutor` may not be spawning processes correctly, or the event loop is serializing work.

### Bug 3: Orphaned Trades in Sequential Response
- **Location**: `warrior_sim_routes.py` / `warrior_db.py`
- **Expected**: Only trades from current batch run in response
- **Actual**: 30+ trades with `exit_price: null` from multiple timestamps (17:06, 17:08, 17:30, 17:53, 17:55) suggesting accumulation across runs
- **Strategy**: Warrior
- **Evidence**: Sequential ROLR response includes trade entries spanning ~50 minutes of wall-clock time across what should be a single replay.
