# Wave 3 Code Auditor Handoff: Verify Phases 5-6

> **Run AFTER:** Backend specialist completes Phases 5-6
> **Architecture Doc:** [concurrent_batch_runner_architecture.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/docs/concurrent_batch_runner_architecture.md)

> [!WARNING]
> **Grep may fail due to CRLF encoding.** Fall back to `view_file_outline` or `view_file`.

---

## Claims to Verify (8 total)

### C1: `load_case_into_context()` exists and uses ctx
- **File:** `nexus2/adapters/simulation/sim_context.py`
- **Check:** Function accepts `SimContext` and loads bars, sets clock, creates watchlist entry
- **Red flag:** Any reference to `get_warrior_sim_broker()`, `get_simulation_clock()`, `get_historical_bar_loader()`, or `get_engine()` — these are global singletons and MUST NOT appear in this function

### C2: All 11 callback wiring points are present
Cross-reference against `warrior_sim_routes.py` L835-1050:

| # | Callback | Target |
|---|----------|--------|
| 1 | `monitor.set_callbacks(get_price=...)` | `ctx.broker.get_price` |
| 2 | `monitor.set_callbacks(get_prices_batch=...)` | batch from `ctx.broker` |
| 3 | `monitor.set_callbacks(execute_exit=...)` | `ctx.broker.sell_position` |
| 4 | `monitor.set_callbacks(update_stop=...)` | `ctx.broker.update_stop` |
| 5 | `monitor.set_callbacks(get_intraday_candles=...)` | `ctx.loader` bars |
| 6 | `monitor.set_callbacks(get_quote_with_spread=...)` | same as get_price |
| 7 | `monitor._get_broker_positions = None` | disabled |
| 8 | `monitor._get_order_status = None` | disabled |
| 9 | `engine._get_intraday_bars = ...` | `ctx.loader` bars |
| 10 | `engine._get_quote = ...` | `ctx.loader` + `ctx.broker` fallback |
| 11 | `engine._submit_order = ...` | `ctx.broker.submit_bracket_order` |
| 12 | `engine._get_order_status = None` | disabled |
| 13 | `monitor._submit_scale_order = ...` | same as submit_order |

### C3: Closure capture correctness
- **Check:** All callback closures use `_broker=ctx.broker`, `_loader=ctx.loader`, `_clock=ctx.clock` default args
- **Red flag:** Any closure that captures `ctx` directly without default args — this will leak state between contexts when the closure is called later

### C4: `run_batch_concurrent()` uses asyncio.gather
- **Check:** `asyncio.gather(*[run_single_case(c) for c in cases])` pattern
- **Check:** Sets `set_simulation_clock_ctx(ctx.clock)` and `set_sim_mode_ctx(True)` inside each task
- **Check:** Creates `SimContext.create()` inside each task (not outside)
- **Check:** Exception handling wraps gather results

### C5: EOD close logic exists
- **Check:** After `step_clock_ctx()`, open positions are force-closed via `ctx.broker.sell_position()`
- **Check:** EOD exit is logged to `warrior_db` via `log_warrior_exit()`

### C6: New endpoint exists
- **File:** `nexus2/api/routes/warrior_sim_routes.py`
- **Check:** `@sim_router.post("/sim/run_batch_concurrent")` exists
- **Check:** Endpoint calls `run_batch_concurrent()` from `sim_context.py`
- **Check:** Returns same response format as `run_batch_tests()`

### C7: Existing endpoints unchanged
- **File:** `nexus2/api/routes/warrior_sim_routes.py`
- **Check:** `run_batch_tests()` function is NOT modified (same P&L logic)
- **Check:** `load_historical_test_case()` is NOT modified
- **Check:** `step_clock()` is NOT modified

### C8: No unintended changes
- **Run:** `git diff --stat`
- **Expected:** Only `sim_context.py` and `warrior_sim_routes.py` modified
- **Red flag:** Changes to any Wave 1/2 files

---

## Output Format

Write report to: `nexus2/wave3_audit_report.md`

```markdown
# Wave 3 Audit Report: Phases 5-6

| # | Claim | Result | Evidence |
|---|-------|:------:|----------|
| C1-C8 | ... | PASS/FAIL | [details] |

## Verdict
- ALL PASS: Ready for acceptance testing
- ANY FAIL: Return to backend specialist
```
