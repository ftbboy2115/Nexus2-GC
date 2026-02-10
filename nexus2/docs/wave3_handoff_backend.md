# Wave 3 Backend Specialist Handoff: Phases 5-6 (Final Wave)

> **Prerequisites:** Wave 1 ✅ (`d5d918b`) + Wave 2 ✅ (`9087523`, `0799a28`)
> **Architecture Doc:** [concurrent_batch_runner_architecture.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/docs/concurrent_batch_runner_architecture.md)
> **Key files created in earlier waves:**
> - `sim_context.py` — `SimContext` dataclass + `step_clock_ctx()`
> - `sim_clock.py` — `_sim_clock_ctx` ContextVar + `set_simulation_clock_ctx()`
> - `trade_event_service.py` — `_is_sim_mode` ContextVar + `set_sim_mode_ctx()`
> - `warrior_db.py` — WAL mode, `batch_run_id`, `purge_batch_trades()`

> [!WARNING]
> **Grep may fail due to CRLF encoding.** If `grep_search` returns 0 results, fall back to `view_file_outline` or `view_file`.

---

## Phase 5: Concurrent Batch Runner

### 5A: Create `load_case_into_context()` function

**File:** `nexus2/adapters/simulation/sim_context.py` (append to existing file)

This function replicates what `load_historical_test_case()` in `warrior_sim_routes.py` L690-1088 does, but operates on a `SimContext` instead of global singletons.

The existing function:
1. Loads bar data into `HistoricalBarLoader`
2. Sets clock to first bar's time
3. Sets initial price on broker
4. Loads mock market data (daily bars for VWAP/EMA)
5. Creates `WatchedCandidate` + adds to engine watchlist
6. Wires 11 callbacks on monitor and engine

Your concurrent version must do the same but against `ctx.*`:

```python
def load_case_into_context(ctx: SimContext, case: dict, yaml_data: dict) -> int:
    """
    Load a test case into a SimContext.
    
    Replicates load_historical_test_case() from warrior_sim_routes.py
    but uses ctx.loader, ctx.clock, ctx.broker, ctx.engine instead of globals.
    
    Args:
        ctx: The SimContext to load into
        case: Test case dict from YAML (has 'id', 'symbol', 'ross_pnl', etc.)
        yaml_data: Full YAML data dict (for looking up case by ID)
    
    Returns:
        Number of bars loaded
    """
```

**CRITICAL: The 11 Callback Wiring**

Study `warrior_sim_routes.py` L835-1050. These are the exact callbacks to wire:

#### Monitor callbacks via `set_callbacks()` (L960-967):
```python
ctx.engine.monitor.set_callbacks(
    get_price=sim_get_price,           # L843: broker.get_price()
    get_prices_batch=sim_get_prices_batch,  # L851: broker price batch
    execute_exit=sim_execute_exit,     # L861: broker.sell_position()
    update_stop=sim_update_stop,       # L895: broker.update_stop()
    get_intraday_candles=sim_get_intraday_bars,  # L920: loader bars
    get_quote_with_spread=sim_get_price,  # L966: same as get_price in sim
)
```

#### Monitor callbacks cleared (L971-973):
```python
ctx.engine.monitor._get_broker_positions = None  # Prevent Alpaca calls
ctx.engine.monitor._submit_scale_order = None    # Set to sim_submit_order below
ctx.engine.monitor._get_order_status = None      # MockBroker fills instantly
```

#### Engine callbacks (L975-1050):
```python
ctx.engine._get_intraday_bars = sim_get_intraday_bars   # L975
ctx.engine._get_quote = sim_get_quote_historical         # L1002
ctx.engine._submit_order = sim_submit_order_historical   # L1042
ctx.engine._get_order_status = None                      # L1046
ctx.engine.monitor._submit_scale_order = sim_submit_order_historical  # L1049
```

**TOTAL: 11 wiring points** (6 set_callbacks + 3 cleared + _get_intraday_bars + _get_quote + _submit_order + _get_order_status + _submit_scale_order... counts to 13 discrete assignments but some are the same function, canonically "11 unique callback points" from the R2 audit).

> [!IMPORTANT]
> Every callback closure must capture `ctx.broker`, `ctx.loader`, `ctx.clock` via default args to prevent cross-context leakage. Example:
> ```python
> async def sim_get_price(symbol: str, _broker=ctx.broker):
>     return _broker.get_price(symbol)
> ```

#### Monitor state setup (L839-841):
```python
ctx.engine.monitor.sim_mode = True
ctx.engine.monitor._sim_clock = ctx.clock
ctx.engine.monitor._recently_exited_sim_time.clear()
```

### 5B: Create `run_batch_concurrent()` function

**File:** `nexus2/adapters/simulation/sim_context.py` (append)

```python
async def run_batch_concurrent(cases: list, yaml_data: dict) -> list:
    """
    Run all test cases concurrently using asyncio.gather().
    
    Each case gets its own SimContext with fully isolated state.
    
    Args:
        cases: List of test case dicts from YAML
        yaml_data: Full YAML data dict
    
    Returns:
        List of result dicts, one per case
    """
    import asyncio
    
    async def run_single_case(case: dict) -> dict:
        case_id = case.get("id")
        symbol = case.get("symbol")
        ross_pnl = case.get("ross_pnl", 0) or 0
        
        import time
        case_start = time.time()
        
        try:
            # Create isolated context
            ctx = SimContext.create(case_id)
            
            # Set ContextVars for this task
            from nexus2.adapters.simulation.sim_clock import set_simulation_clock_ctx
            from nexus2.domain.automation.trade_event_service import set_sim_mode_ctx
            set_simulation_clock_ctx(ctx.clock)
            set_sim_mode_ctx(True)
            
            # Load test case into context
            bar_count = load_case_into_context(ctx, case, yaml_data)
            
            if bar_count == 0:
                return {
                    "case_id": case_id, "symbol": symbol,
                    "date": case.get("trade_date"),
                    "bar_count": 0, "trades": [], "total_pnl": 0,
                    "ross_pnl": ross_pnl, "delta": -ross_pnl,
                    "error": "No bars loaded",
                }
            
            # Step through all bars + 30 min EOD buffer
            await step_clock_ctx(ctx, bar_count + 30)
            
            # EOD close: force-close any open positions
            eod_positions = ctx.broker.get_positions()
            for pos in eod_positions:
                pos_symbol = pos.get("symbol")
                pos_qty = pos.get("qty", 0)
                if pos_qty > 0:
                    eod_price = ctx.broker._current_prices.get(
                        pos_symbol, pos.get("avg_price", 0)
                    )
                    ctx.broker.sell_position(pos_symbol, pos_qty)
                    
                    # Log EOD exit to warrior_db
                    try:
                        from nexus2.db.warrior_db import (
                            get_warrior_trade_by_symbol, log_warrior_exit
                        )
                        trade = get_warrior_trade_by_symbol(pos_symbol)
                        if trade:
                            log_warrior_exit(
                                trade_id=trade["id"],
                                exit_price=float(eod_price),
                                exit_reason="eod_close",
                                quantity_exited=pos_qty,
                            )
                    except Exception as e:
                        import logging
                        logging.getLogger(__name__).warning(
                            f"[{case_id}] warrior_db EOD exit failed: {e}"
                        )
            
            # Collect results
            account = ctx.broker.get_account()
            realized = round(account.get("realized_pnl", 0), 2)
            unrealized = round(account.get("unrealized_pnl", 0), 2)
            total_pnl = round(realized + unrealized, 2)
            case_time = round(time.time() - case_start, 2)
            
            # Get trades from warrior_db
            trades = []  # Simplified for now — can be enhanced later
            
            return {
                "case_id": case_id, "symbol": symbol,
                "date": case.get("trade_date"),
                "bar_count": bar_count,
                "trades": trades,
                "realized_pnl": realized,
                "unrealized_pnl": unrealized,
                "total_pnl": total_pnl,
                "ross_pnl": ross_pnl,
                "delta": round(total_pnl - ross_pnl, 2),
                "runtime_seconds": case_time,
            }
            
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"[{case_id}] Failed: {e}")
            return {
                "case_id": case_id, "symbol": symbol,
                "date": case.get("trade_date"),
                "bar_count": 0, "trades": [], "total_pnl": 0,
                "ross_pnl": ross_pnl, "delta": -ross_pnl,
                "error": str(e),
            }
    
    results = await asyncio.gather(
        *[run_single_case(c) for c in cases],
        return_exceptions=True,
    )
    
    # Convert exceptions to error dicts
    final = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            final.append({
                "case_id": cases[i].get("id"),
                "symbol": cases[i].get("symbol"),
                "error": str(r),
                "total_pnl": 0,
                "ross_pnl": cases[i].get("ross_pnl", 0) or 0,
            })
        else:
            final.append(r)
    return final
```

### 5C: Add API endpoint

**File:** `nexus2/api/routes/warrior_sim_routes.py`

Add new endpoint **after** the existing `run_batch_tests` function (around L1563):

```python
@sim_router.post("/sim/run_batch_concurrent")
async def run_batch_concurrent_endpoint(request: BatchTestRequest = BatchTestRequest()):
    """
    Run test cases CONCURRENTLY using isolated SimContexts.
    
    Same interface as /sim/run_batch but uses asyncio.gather() for ~15x speedup.
    """
    import time
    start_time = time.time()
    
    # Load cases from YAML (same logic as run_batch_tests L1310-1327)
    base_path = os.path.join(os.path.dirname(__file__), "..", "..", "tests", "test_cases")
    yaml_path = os.path.join(base_path, "warrior_setups.yaml")
    
    if not os.path.exists(yaml_path):
        raise HTTPException(status_code=404, detail="warrior_setups.yaml not found")
    
    with open(yaml_path, "r") as f:
        yaml_data = yaml.safe_load(f)
    
    all_cases = yaml_data.get("test_cases", [])
    cases = [c for c in all_cases if c.get("status") == "POLYGON_DATA"]
    
    if request.case_ids:
        cases = [c for c in cases if c.get("id") in request.case_ids]
    
    if not cases:
        return {"results": [], "summary": {"total_pnl": 0, "cases_run": 0}, "error": "No cases"}
    
    # Run concurrently
    from nexus2.adapters.simulation.sim_context import run_batch_concurrent
    results = await run_batch_concurrent(cases, yaml_data)
    
    # Build summary (same format as run_batch_tests L1540-1562)
    total_runtime = round(time.time() - start_time, 2)
    total_pnl = sum(r.get("total_pnl", 0) for r in results)
    total_ross_pnl = sum(r.get("ross_pnl", 0) for r in results)
    
    return {
        "results": results,
        "summary": {
            "total_pnl": round(total_pnl, 2),
            "total_ross_pnl": round(total_ross_pnl, 2),
            "delta": round(total_pnl - total_ross_pnl, 2),
            "cases_run": len(results),
            "cases_profitable": sum(1 for r in results if r.get("total_pnl", 0) > 0),
            "cases_with_errors": sum(1 for r in results if "error" in r),
            "runtime_seconds": total_runtime,
        },
    }
```

> [!IMPORTANT]
> The sequential endpoint (`/sim/run_batch`) must remain unchanged. We're adding a parallel endpoint so we can compare results for acceptance testing.

---

## Phase 6: Acceptance Testing

### Run both endpoints on the same cases and compare P&L

After the coding is done, run:

```powershell
# Sequential baseline
Invoke-RestMethod -Uri "http://localhost:8000/warrior/sim/run_batch" -Method Post -ContentType "application/json" -Body '{}' | ConvertTo-Json -Depth 10 > sequential_results.json

# Concurrent
Invoke-RestMethod -Uri "http://localhost:8000/warrior/sim/run_batch_concurrent" -Method Post -ContentType "application/json" -Body '{}' | ConvertTo-Json -Depth 10 > concurrent_results.json
```

**Acceptance criteria:**
- Every case_id produces the same `total_pnl` in both runs
- Concurrent is at least 5x faster than sequential
- No errors exclusive to the concurrent run
- No Alpaca API calls during concurrent run (check for live broker references)

---

## Summary of Files to Modify/Create

| File | Changes |
|------|---------|
| `adapters/simulation/sim_context.py` | Add `load_case_into_context()` + `run_batch_concurrent()` |
| `api/routes/warrior_sim_routes.py` | Add `/sim/run_batch_concurrent` endpoint |

## Commit Message

```
feat: concurrent batch runner with asyncio.gather (Wave 3, Phases 5-6)

- load_case_into_context() with all 11 callbacks per SimContext
- run_batch_concurrent() via asyncio.gather
- /sim/run_batch_concurrent endpoint (parallel to existing sequential)
```

## DO NOT

- Do NOT modify the existing `run_batch_tests()` or `load_historical_test_case()` functions
- Do NOT modify `sim_clock.py`, `mock_broker.py`, `trade_event_service.py`, or `warrior_db.py`
- Do NOT modify `warrior_engine.py` or `warrior_monitor.py`
