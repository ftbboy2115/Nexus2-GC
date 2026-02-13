# Backend Handoff: VELO Divergence Fix

## Reference

Read the implementation plan at `.gemini/antigravity/brain/e56e9f8f-208c-46dc-8c63-d13dcafec674/implementation_plan.md` for full context.

## Changes (3 total)

### Fix 1: Unify replay time range

**File**: `nexus2/api/routes/warrior_sim_routes.py` **L1495**

Change:
```python
step_minutes = bar_count + 30
```
To:
```python
step_minutes = 960  # Full day: 04:00→20:00, matches GUI step range
```

`bar_count + 30` only covers the number of bars, not the time span they cover. Bars have gaps (no trades during slow periods), so 472 bars ≠ 472 minutes. The data spans 04:00-19:56 but `bar_count + 30 = 502` only reaches ~12:22. Using 960 (04:00→20:00) matches the GUI and lets existing time-based exit logic (7:30pm aggressive close) handle end-of-day.

### Fix 2: Stop monitor during GUI replay

**File**: `nexus2/api/routes/warrior_sim_routes.py` **After L858**

Add after `engine.monitor.realized_pnl_today = Decimal("0")`:
```python
# Stop monitor background loop during replay — step_clock drives
# _check_all_positions explicitly. Without this, the monitor loop
# fires on wall-clock (2s), causing dual entries and race conditions.
if engine.monitor._running:
    await engine.monitor.stop()
```

This matches what `run_batch_tests` does at L1405-1406.

### Fix 3: Remove TRACE-VELO logging

Remove ALL lines containing `[TRACE-VELO]` from these files:

| File | Lines |
|------|-------|
| `nexus2/domain/automation/warrior_monitor_exit.py` | L79-83, L88, L105, L119, L920-924 |
| `nexus2/domain/automation/warrior_monitor.py` | L525-530 |
| `nexus2/api/routes/warrior_sim_routes.py` | L864-868, L1200-1204 |

Search for `TRACE-VELO` to find them all. Remove the full `logger.warning(...)` statement for each.

## Rules

- Do NOT modify entry, exit, or stop logic
- Do NOT modify the time-based exit (7:30pm aggressive close)
- Do NOT add new features — these are targeted fixes only
- Deploy to VPS using `/deploy-to-vps` workflow after changes
