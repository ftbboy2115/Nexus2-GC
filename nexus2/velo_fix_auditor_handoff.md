# Auditor Handoff: VELO Divergence Fix Verification

## What Changed

The backend agent made 3 changes across 3 files to fix the VELO GUI vs batch P&L divergence. All changes are deployed to VPS.

## Claims to Verify

### C1: Batch replay range changed from `bar_count + 30` to `960`

**File**: `nexus2/api/routes/warrior_sim_routes.py`  
**Expected**: Line containing `step_minutes = 960` with comment about full day 04:00→20:00  
**Previous**: `step_minutes = bar_count + 30`

```powershell
Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "step_minutes" | Select-Object LineNumber, Line
```

### C2: Monitor stopped in `load_historical_test_case`

**File**: `nexus2/api/routes/warrior_sim_routes.py`  
**Expected**: `if engine.monitor._running:` followed by `await engine.monitor.stop()` BEFORE the `sim_get_price` callback definition, AFTER `engine.monitor.realized_pnl_today = Decimal("0")`

```powershell
Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "monitor._running|monitor.stop|sim_mode = True|realized_pnl_today" | Select-Object LineNumber, Line
```

### C3: All TRACE-VELO logging removed

**Files**: `warrior_sim_routes.py`, `warrior_monitor.py`, `warrior_monitor_exit.py`  
**Expected**: Zero results for TRACE-VELO across all 3 files

```powershell
Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "TRACE-VELO"
Select-String -Path "nexus2\domain\automation\warrior_monitor.py" -Pattern "TRACE-VELO"
Select-String -Path "nexus2\domain\automation\warrior_monitor_exit.py" -Pattern "TRACE-VELO"
```

### C4: No unintended changes

Verify that entry logic, exit logic, stop logic, and time-based exit (7:30pm aggressive close) were NOT modified.

```powershell
Select-String -Path "nexus2\domain\automation\warrior_monitor_exit.py" -Pattern "check_stop_hit|base_hit|home_run|time_stop|aggressive" | Select-Object LineNumber, Line
```

## Deliverable

Write report to `nexus2/velo_fix_audit_report.md` with PASS/FAIL for each claim (C1-C4).
