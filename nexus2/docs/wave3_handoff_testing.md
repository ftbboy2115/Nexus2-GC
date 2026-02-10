# Wave 3 Testing Specialist Handoff: Phases 5-6 Tests

> **Run AFTER:** Code auditor confirms all 8 claims PASS
> **Audit Report:** `nexus2/wave3_audit_report.md`

> [!WARNING]
> **Grep may fail due to CRLF encoding.** Fall back to `view_file_outline` or `view_file`.

---

## What Was Changed (Phase 5-6 Summary)

1. `sim_context.py` — Added `load_case_into_context()` (callback wiring) + `run_batch_concurrent()` (asyncio.gather)
2. `warrior_sim_routes.py` — Added `/sim/run_batch_concurrent` endpoint

---

## Tests to Write

Add to `nexus2/tests/test_concurrent_isolation.py`.

### T14: load_case_into_context function exists

```python
def test_load_case_into_context_exists():
    """load_case_into_context function should exist."""
    from nexus2.adapters.simulation.sim_context import load_case_into_context
    import inspect
    sig = inspect.signature(load_case_into_context)
    assert 'ctx' in sig.parameters
    assert 'case' in sig.parameters
```

### T15: run_batch_concurrent function exists

```python
def test_run_batch_concurrent_exists():
    """run_batch_concurrent function should be importable."""
    from nexus2.adapters.simulation.sim_context import run_batch_concurrent
    import inspect
    assert inspect.iscoroutinefunction(run_batch_concurrent)
```

### T16: Concurrent endpoint exists

```python
def test_concurrent_endpoint_registered():
    """The /sim/run_batch_concurrent endpoint should be registered."""
    from nexus2.api.routes.warrior_sim_routes import sim_router
    routes = [r.path for r in sim_router.routes]
    assert "/sim/run_batch_concurrent" in routes
```

### T17: All Wave 1+2 tests still pass (regression)

Run the full test file:
```powershell
cd nexus2
python -m pytest tests/test_concurrent_isolation.py -x -v --timeout=30
```

### T18: Acceptance Test (MANUAL — requires running server)

> [!IMPORTANT]
> This test requires the Nexus server to be running. If the testing specialist cannot start the server, document it as "SKIPPED — requires running server" and note it for Clay to run manually.

If server is available:

```powershell
# Sequential
$seq = Invoke-RestMethod -Uri "http://localhost:8000/warrior/sim/run_batch" -Method Post -ContentType "application/json" -Body '{}'

# Concurrent  
$con = Invoke-RestMethod -Uri "http://localhost:8000/warrior/sim/run_batch_concurrent" -Method Post -ContentType "application/json" -Body '{}'

# Compare P&L per case
$seq.results | ForEach-Object { $_.case_id + ": " + $_.total_pnl }
$con.results | ForEach-Object { $_.case_id + ": " + $_.total_pnl }

# Timing comparison
"Sequential: " + $seq.summary.runtime_seconds + "s"
"Concurrent: " + $con.summary.runtime_seconds + "s"
```

**Pass criteria:**
- Same `total_pnl` per case_id in both runs
- Concurrent runtime < sequential runtime / 5

---

## Output Format

Write report to: `nexus2/wave3_test_report.md`

```markdown
# Wave 3 Test Report: Phases 5-6

## New Tests
| # | Test | Result |
|---|------|:------:|
| T14 | load_case_into_context exists | PASS/FAIL |
| T15 | run_batch_concurrent exists | PASS/FAIL |
| T16 | Endpoint registered | PASS/FAIL |

## Regression Tests
| # | Test | Result |
|---|------|:------:|
| T1-T13 | All Wave 1+2 tests | PASS/FAIL |

## Acceptance Test
| Metric | Sequential | Concurrent | Match? |
|--------|:----------:|:----------:|:------:|
| Total P&L | $X | $X | YES/NO |
| Runtime | Xs | Xs | - |
| Speedup | - | - | Xx |

## Verdict
- ALL PASS: Concurrent batch runner complete! 🎉
- ANY FAIL: [describe failure and impact]
```
