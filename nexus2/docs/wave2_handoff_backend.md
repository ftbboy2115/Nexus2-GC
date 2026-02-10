# Wave 2 Backend Specialist Handoff: Concurrent Batch Runner (Phases 3-4)

> **Run AFTER:** Wave 1 verified (commit `d5d918b`, 6/6 tests pass)
> **Architecture Doc:** [concurrent_batch_runner_architecture.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/docs/concurrent_batch_runner_architecture.md)

> [!WARNING]
> **Grep may fail due to CRLF encoding.** If `grep_search` returns 0 results for a pattern you know exists, fall back to `view_file_outline` or `view_file` to verify.

---

## Context

Wave 1 added ContextVar plumbing for `SimulationClock` and `is_sim_mode`. Wave 2 creates:
- **Phase 3:** The `SimContext` dataclass + `step_clock_ctx()` function
- **Phase 4:** WAL mode + `batch_run_id` in warrior_db for concurrent writes

---

## Phase 3: SimContext + step_clock_ctx

### 3A: Create SimContext dataclass

**New file:** `nexus2/adapters/simulation/sim_context.py`

The `SimContext` holds all per-test-case isolated components. Create it following the architecture doc (L74-117):

```python
"""
SimContext: Fully isolated simulation environment for one test case.
Used by the concurrent batch runner to prevent cross-case state leakage.
"""
from dataclasses import dataclass
from uuid import uuid4
from typing import Optional

from nexus2.adapters.simulation.sim_clock import SimulationClock
from nexus2.adapters.simulation.mock_broker import MockBroker
from nexus2.adapters.simulation.historical_bar_loader import HistoricalBarLoader
from nexus2.domain.automation.warrior_engine import WarriorEngine, WarriorEngineConfig
from nexus2.domain.automation.warrior_scanner_service import WarriorScannerService
from nexus2.domain.automation.warrior_monitor import WarriorMonitor


@dataclass
class SimContext:
    """Fully isolated simulation environment for one test case."""
    broker: MockBroker
    clock: SimulationClock
    loader: HistoricalBarLoader
    engine: WarriorEngine
    monitor: WarriorMonitor
    batch_id: str
    case_id: str
    
    @classmethod
    def create(cls, case_id: str, batch_id: Optional[str] = None) -> "SimContext":
        clock = SimulationClock()
        
        # MockBroker with injected clock (Wave 1 Phase 1B)
        broker = MockBroker(initial_cash=100_000, clock=clock)
        
        # Monitor with clean state (R2 fix)
        monitor = WarriorMonitor()
        monitor.sim_mode = True
        monitor._recently_exited_file = None
        monitor._recently_exited = {}
        monitor._recently_exited_sim_time = {}
        
        # Engine + Scanner per context (R3 fix)
        engine = WarriorEngine(
            config=WarriorEngineConfig(sim_only=True),
            scanner=WarriorScannerService(),
            monitor=monitor,
        )
        engine._pending_entries_file = None  # Disable disk persistence
        
        return cls(
            broker=broker,
            clock=clock,
            loader=HistoricalBarLoader(),
            engine=engine,
            monitor=monitor,
            batch_id=batch_id or str(uuid4()),
            case_id=case_id,
        )
```

### 3B: Create step_clock_ctx function

Add to the **same file** (`sim_context.py`). This is the context-aware version of `step_clock()` from `warrior_sim_routes.py` (L1092-1205). Key differences:
- Uses `ctx.clock`, `ctx.broker`, `ctx.loader`, `ctx.engine`, `ctx.monitor` instead of globals
- Always headless (batch mode only)
- Supports 10s stepping like the original
- No UI/chart response building

```python
async def step_clock_ctx(ctx: SimContext, minutes: int):
    """
    Step a SimContext's clock forward, processing entries/exits each step.
    
    This is the concurrent-safe version of warrior_sim_routes.step_clock().
    Always headless — no chart data generation.
    """
    from nexus2.domain.automation.warrior_engine_entry import check_entry_triggers
    import logging
    log = logging.getLogger(__name__)
    
    # Determine step granularity (same logic as step_clock L1119-1134)
    use_10s_stepping = any(
        ctx.loader.has_10s_bars(sym) for sym in ctx.loader.get_loaded_symbols()
    )
    
    if use_10s_stepping:
        total_steps = minutes * 6
        step_seconds = 10
    else:
        total_steps = minutes
        step_seconds = 0
    
    for step_idx in range(total_steps):
        # Step forward
        if use_10s_stepping:
            ctx.clock.step_forward(minutes=0, seconds=step_seconds)
            time_str = ctx.clock.get_time_string_with_seconds()
        else:
            ctx.clock.step_forward(minutes=1)
            time_str = ctx.clock.get_time_string()
        
        # Update prices for all loaded symbols
        for symbol in ctx.loader.get_loaded_symbols():
            if use_10s_stepping and ctx.loader.has_10s_bars(symbol):
                price = ctx.loader.get_10s_price_at(symbol, time_str)
            else:
                price = ctx.loader.get_price_at(symbol, ctx.clock.get_time_string())
            
            if price:
                ctx.broker.set_price(symbol, price)
        
        # Check engine state
        engine_state_str = (
            ctx.engine.state.value 
            if hasattr(ctx.engine.state, 'value') 
            else str(ctx.engine.state)
        )
        
        # Trigger entry check if engine is running
        if engine_state_str in ("running", "premarket"):
            try:
                await check_entry_triggers(ctx.engine)
            except Exception as e:
                log.warning(f"[{ctx.case_id}] Entry check error at {time_str}: {e}")
        
        # Check positions for exits (monitor tick)
        if ctx.monitor._positions:
            try:
                # Ensure batch price callback is available
                if not ctx.monitor._get_prices_batch:
                    async def sim_get_prices_batch(symbols, _broker=ctx.broker):
                        result = {}
                        for s in symbols:
                            price = _broker.get_price(s)
                            if price:
                                result[s] = price
                        return result
                    ctx.monitor._get_prices_batch = sim_get_prices_batch
                
                await ctx.monitor._check_all_positions()
            except Exception as e:
                log.error(f"[{ctx.case_id}] Monitor check error at {time_str}: {e}")
```

> [!IMPORTANT]
> The `_broker=ctx.broker` default arg in the closure is critical — it captures the correct broker per context. Without it, all tasks would share the last loop iteration's broker.

### 3C: Export from simulation package

**File:** `nexus2/adapters/simulation/__init__.py`

Add `SimContext` and `step_clock_ctx` to imports and `__all__`.

---

## Phase 4: warrior_db WAL Mode + batch_run_id

### 4A: Enable WAL mode

**File:** `nexus2/db/warrior_db.py`

Add WAL mode pragma via SQLAlchemy event listener. Place this right after the engine creation (after L30):

```python
from sqlalchemy import event

@event.listens_for(warrior_engine, "connect")
def set_sqlite_wal(dbapi_conn, connection_record):
    """Enable WAL mode for concurrent batch writes."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()
```

### 4B: Add `batch_run_id` column

**File:** `nexus2/db/warrior_db.py`

Add column to `WarriorTradeModel` (after L89, `is_sim` column):

```python
    # Batch run tracking (concurrent batch runner)
    batch_run_id = Column(String(36), nullable=True, index=True)
```

Add migration to `init_warrior_db()` (after L236, before the print):

```python
        # Batch run ID column
        try:
            conn.execute(text("ALTER TABLE warrior_trades ADD COLUMN batch_run_id TEXT"))
            conn.commit()
        except Exception:
            pass  # Column already exists
```

### 4C: Add batch-scoped purge function

**File:** `nexus2/db/warrior_db.py`

Add a new function (place after `purge_sim_trades` around L770):

```python
def purge_batch_trades(batch_run_id: str) -> int:
    """
    Delete all trades for a specific batch run.
    
    Used by the concurrent batch runner to clean up after each test case
    without affecting other concurrent cases.
    
    Args:
        batch_run_id: UUID of the batch run to purge
        
    Returns:
        Number of trades deleted
    """
    import logging
    log = logging.getLogger(__name__)
    
    with get_warrior_session() as db:
        count = db.query(WarriorTradeModel).filter_by(
            batch_run_id=batch_run_id
        ).delete()
        db.commit()
        log.info(f"[Warrior DB] Purged {count} trades for batch {batch_run_id[:8]}")
        return count
```

### 4D: Update `log_warrior_entry` to accept `batch_run_id`

**File:** `nexus2/db/warrior_db.py`

Add `batch_run_id` parameter to `log_warrior_entry()` (L243):

Current signature:
```python
def log_warrior_entry(
    trade_id: str,
    symbol: str,
    ...
    is_sim: bool = False,
):
```

Add after `is_sim`:
```python
    batch_run_id: str = None,
```

And in the `WarriorTradeModel(...)` constructor call inside the function, add:
```python
    batch_run_id=batch_run_id,
```

---

## Summary of Files to Modify/Create

| File | Changes |
|------|---------|
| `adapters/simulation/sim_context.py` | **[NEW]** SimContext dataclass + step_clock_ctx() |
| `adapters/simulation/__init__.py` | Export SimContext, step_clock_ctx |
| `db/warrior_db.py` | WAL mode event listener, batch_run_id column + migration, purge_batch_trades(), log_warrior_entry param |

## Commit Message

```
feat: add SimContext, step_clock_ctx, and warrior_db WAL mode (Wave 2, Phases 3-4)

- SimContext dataclass for per-test-case isolation
- step_clock_ctx() with 10s stepping, entry/exit triggers
- WAL mode for concurrent SQLite writes
- batch_run_id column + batch-scoped purge
```

## DO NOT

- Do NOT modify `warrior_sim_routes.py` — the existing `step_clock()` and `run_batch_tests()` remain untouched
- Do NOT modify `warrior_engine.py`, `warrior_monitor.py`, or any files from Wave 1
- Do NOT start Phase 5 (concurrent batch runner wiring) — that's Wave 3
- Do NOT change the existing `purge_sim_trades()` function
