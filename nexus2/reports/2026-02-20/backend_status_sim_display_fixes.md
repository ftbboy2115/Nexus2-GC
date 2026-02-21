# Backend Status: Sim Engine Display Fixes

**Date:** 2026-02-20
**Agent:** Backend Specialist
**Reference:** `handoff_backend_sim_display_fixes.md`

---

## Changes Made

### Fix #1: Enrich Trade Detail with Partial Exit Info

**Files modified:**
- `nexus2/db/warrior_db.py` — Added `partial_exit_prices` column (JSON text), tracking in `log_warrior_exit` partial branch
- `nexus2/adapters/simulation/sim_context.py` — Added `_compute_avg_exit_price()` helper, enriched trade result dict

**New fields in per-trade result:**
| Field | Type | Description |
|-------|------|-------------|
| `partial_taken` | bool | Whether a partial exit occurred |
| `remaining_quantity` | int | Shares remaining at final exit |
| `avg_exit_price` | float | VWAP across all exits (partials + final) |

**Evidence:** MLEC batch test shows `partial_taken=true`, `avg_exit_price=20.1475` which reconciles with `entry_price=19.96` and `pnl=+244.20`.

---

### Fix #2: Sim Clock Timestamps

**Files modified:**
- `nexus2/db/warrior_db.py` — Added `entry_time_override` param to `log_warrior_entry`, `exit_time_override` param to `log_warrior_exit` (default=None → `now_utc()`, backward-compatible)
- `nexus2/domain/automation/warrior_engine_entry.py:1242-1247` — Passes `engine._sim_clock.current_time` when available
- `nexus2/adapters/simulation/sim_context.py:344,602` — Passes `ctx.clock.current_time` in exit callback and EOD close

**Evidence:** MLEC batch test shows `entry_time=2026-02-20T07:56:00Z`, `exit_time=2026-02-20T09:47:00Z` — both reflect simulated trading day, not wall-clock.

---

### Fix #3: Dual P&L Documentation

**File modified:** `nexus2/adapters/simulation/sim_context.py:546-563`

Added docstring to `_run_single_case_async` explaining:
- MockBroker P&L (top-level `total_pnl`) vs warrior_db P&L (per-trade `pnl`)
- When they can diverge (scale-ins shifting avg_entry_price)
- Why `exit_price` doesn't reconcile with `pnl` when partials occur

---

## Verification Results

### Test Suite
```
757 passed, 4 skipped, 0 failed (115.72s)
```

### MLEC Batch Test
```json
{
  "entry_price": 19.96,
  "exit_price": 18.91,
  "shares": 1302,
  "pnl": 244.2,
  "partial_taken": true,
  "remaining_quantity": 0,
  "avg_exit_price": 20.1475,
  "entry_time": "2026-02-20T07:56:00Z",
  "exit_time": "2026-02-20T09:47:00Z"
}
```

✅ New fields present (`partial_taken`, `avg_exit_price`, `remaining_quantity`)
✅ Timestamps reflect simulated market time (07:56-09:47 ET, not wall-clock)
✅ `avg_exit_price=20.1475` reconciles with `entry=19.96` and `pnl=+244.20`
✅ Full test suite passes (757/757)

### Testable Claims for Validation

| # | Claim | File:Line | Grep Pattern |
|---|-------|-----------|--------------|
| 1 | `partial_exit_prices` column exists in model | `warrior_db.py:79` | `partial_exit_prices = Column` |
| 2 | Partial prices tracked in JSON during exit | `warrior_db.py:401-404` | `existing_partials.append` |
| 3 | `entry_time_override` param on `log_warrior_entry` | `warrior_db.py:284` | `entry_time_override` |
| 4 | `exit_time_override` param on `log_warrior_exit` | `warrior_db.py:376` | `exit_time_override` |
| 5 | Sim clock passed in entry | `warrior_engine_entry.py:1243` | `entry_time_override` |
| 6 | Sim clock passed in exit callback | `sim_context.py:347` | `exit_time_override=ctx.clock` |
| 7 | `avg_exit_price` in trade result | `sim_context.py:632` | `avg_exit_price` |
| 8 | Dual P&L docstring | `sim_context.py:548` | `Dual P&L System` |
