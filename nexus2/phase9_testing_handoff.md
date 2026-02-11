# Testing Handoff: Phase 9 Monitor Bleed-Over Verification

## Context

The monitor state bleed-over fix has been applied to `warrior_sim_routes.py` (L826-832).
3 unit tests (T17-T19) have been added to `nexus2/tests/test_concurrent_isolation.py`.

## Tasks

### Task 1: Run Unit Tests

Run the existing test suite to verify no regressions and that the new T17-T19 tests pass:

```powershell
cd "c:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus"
python -m pytest nexus2/tests/test_concurrent_isolation.py -v
```

**Expected**: All 19 tests pass (T1-T19), including the 3 new Phase 9 tests.

### Task 2: Run Full Batch Comparison

Start the server and run both batch endpoints. Compare P&L results.

**Sequential batch**:
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/warrior/sim/run_batch" -Method POST -ContentType "application/json" -Body "{}"
```

**Concurrent batch**:
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/warrior/sim/run_batch_concurrent" -Method POST -ContentType "application/json" -Body "{}"
```

### Success Criteria

1. All 19 unit tests pass
2. Sequential and concurrent batch P&L results **converge** (should be identical or very close)
3. FLYE and RVSN should no longer produce `$0` in the sequential runner

### Report

Write results to `nexus2/phase9_verification_report.md`.
