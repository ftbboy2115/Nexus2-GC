# Testing Handoff: VELO Divergence Fix Verification

## Context

Three fixes were deployed to resolve VELO GUI vs batch P&L divergence:
1. Batch replay range changed from `bar_count + 30` to `960` (full day)
2. Monitor background loop stopped during GUI replay
3. TRACE-VELO diagnostic logging removed

Code is deployed to VPS at `root@100.113.178.7`.

## Tests to Run

### Test 1: Batch VELO P&L

Run the batch for VELO only and record the P&L. Previously this was +$21.36 (with `bar_count + 30`). With 960-minute replay, it should now include after-hours bars and may produce a different result.

```powershell
$body = '{"case_ids": ["ross_velo_20260210"]}'
$r = Invoke-RestMethod -Uri "http://100.113.178.7:8000/warrior/sim/run_batch" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 300
Write-Host "Batch VELO PnL: $($r.results[0].realized_pnl)"
Write-Host "Batch VELO total_pnl: $($r.results[0].total_pnl)"
```

### Test 2: GUI VELO P&L

Run VELO through the GUI path (load_historical + step_clock) and compare to batch:

```powershell
# Clear trade log
ssh root@100.113.178.7 "> /root/Nexus2/data/warrior_trade.log"

# Load and step
$r = Invoke-RestMethod -Uri "http://100.113.178.7:8000/warrior/sim/load_historical?case_id=ross_velo_20260210" -Method Post -ContentType "application/json" -TimeoutSec 120
Write-Host "Loaded: $($r.bar_count) bars"
$s = Invoke-RestMethod -Uri "http://100.113.178.7:8000/warrior/sim/step?minutes=960&headless=true" -Method Post -ContentType "application/json" -TimeoutSec 300
Write-Host "Step done"

# Check trade log for P&L
ssh root@100.113.178.7 "cat /root/Nexus2/data/warrior_trade.log"
```

### Test 3: Full batch regression

Run all test cases and compare total P&L to the previous baseline ($4,006.82 total across 22 cases):

```powershell
$r = Invoke-RestMethod -Uri "http://100.113.178.7:8000/warrior/sim/run_batch" -Method Post -ContentType "application/json" -TimeoutSec 600
Write-Host "Total PnL: $($r.summary.total_pnl)"
Write-Host "Cases run: $($r.summary.cases_run)"
Write-Host "Profitable: $($r.summary.cases_profitable)"
$r.results | ForEach-Object { Write-Host "$($_.case_id): $($_.total_pnl)" }
```

### Test 4: No dual entries in GUI

Check that the GUI path no longer produces two ENTRY events for VELO:

```powershell
ssh root@100.113.178.7 "Select-String -Path '/root/Nexus2/data/warrior_trade.log' -Pattern 'ENTRY'" 
# Or: ssh root@100.113.178.7 "grep ENTRY /root/Nexus2/data/warrior_trade.log"
```

Expected: exactly 1 ENTRY event (not 2 like before the fix).

## Pass Criteria

| Test | Pass If |
|------|---------|
| T1 + T2 | GUI and batch VELO P&L match (or are very close) |
| T3 | Full batch completes without errors |
| T4 | Exactly 1 ENTRY event for VELO in GUI path |

## Deliverable

Write report to `nexus2/velo_fix_test_report.md` with results for each test.
