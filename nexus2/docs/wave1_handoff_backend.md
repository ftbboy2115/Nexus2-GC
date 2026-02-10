# Wave 1 Backend Specialist Handoff: Concurrent Batch Runner

> **Scope:** Phases 1-2 of [Architecture Doc v4](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/docs/concurrent_batch_runner_architecture.md)
> **Mode:** Implementation — modify production code
> **After you finish:** Code auditor will verify your changes before testing

---

## Context

We're building a concurrent batch test runner for Warrior Bot's Mock Market. Currently 25 test cases run sequentially (~15-20 min). The concurrent runner will use `asyncio.gather()` — but first, global singletons must be replaced with per-context instances via `ContextVar`.

## Phase 1A: SimulationClock ContextVar

**File:** [sim_clock.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_clock.py)

**Current code (L304-321):**
```python
# Global simulation clock (singleton for easy access)
_simulation_clock: Optional[SimulationClock] = None

def get_simulation_clock() -> SimulationClock:
    """Get or create global simulation clock."""
    global _simulation_clock
    if _simulation_clock is None:
        _simulation_clock = SimulationClock()
    return _simulation_clock

def reset_simulation_clock(start_time=None, speed=1.0) -> SimulationClock:
    """Reset global simulation clock to new state."""
    global _simulation_clock
    _simulation_clock = SimulationClock(start_time=start_time, speed=speed)
    return _simulation_clock
```

**Required change:** Add a `ContextVar` that takes priority over the global singleton when set. This ensures existing callers (12+ files, 7 call sites in batch path) work without any signature changes.

```python
from contextvars import ContextVar

# ContextVar for per-task clock (concurrent batch mode)
_sim_clock_ctx: ContextVar[Optional[SimulationClock]] = ContextVar('sim_clock', default=None)

# Global simulation clock (singleton for interactive/live mode)
_simulation_clock: Optional[SimulationClock] = None

def get_simulation_clock() -> SimulationClock:
    """Get simulation clock — checks ContextVar first, falls back to global singleton."""
    ctx_clock = _sim_clock_ctx.get()
    if ctx_clock is not None:
        return ctx_clock
    global _simulation_clock
    if _simulation_clock is None:
        _simulation_clock = SimulationClock()
    return _simulation_clock

def set_simulation_clock_ctx(clock: SimulationClock) -> None:
    """Set per-task clock for concurrent batch mode."""
    _sim_clock_ctx.set(clock)

def reset_simulation_clock(start_time=None, speed=1.0) -> SimulationClock:
    """Reset global simulation clock to new state."""
    global _simulation_clock
    _simulation_clock = SimulationClock(start_time=start_time, speed=speed)
    return _simulation_clock
```

**Also update `__init__.py`** at [adapters/simulation/__init__.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/__init__.py) — add `set_simulation_clock_ctx` to imports and `__all__`.

> [!IMPORTANT]
> Do NOT change any consumer files. The `get_simulation_clock()` function signature is unchanged — all 12+ consumer files will automatically get the ContextVar clock when it's set.

---

## Phase 1B: Clock Injection into MockBroker

**File:** [mock_broker.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/mock_broker.py)

**Problem:** `sell_position()` (L441) does an inline import of `get_simulation_clock()`. In concurrent mode, this needs to resolve to the correct per-task clock.

**Fix 1 — Constructor injection (L103-118):**

Current:
```python
def __init__(self, initial_cash: float = 100_000.0):
```

Change to:
```python
def __init__(self, initial_cash: float = 100_000.0, clock: Optional['SimulationClock'] = None):
    ...
    self._clock = clock  # Injected clock for concurrent batch mode
```

**Fix 2 — Use injected clock in `sell_position()` (L440-444):**

Current:
```python
    try:
        from nexus2.adapters.simulation import get_simulation_clock
        sim_clock = get_simulation_clock()
        sim_time = sim_clock.get_time_string() if sim_clock and sim_clock.current_time else None
    except ImportError:
        sim_time = None
```

Change to:
```python
    try:
        if self._clock:
            sim_time = self._clock.get_time_string()
        else:
            from nexus2.adapters.simulation import get_simulation_clock
            sim_clock = get_simulation_clock()
            sim_time = sim_clock.get_time_string() if sim_clock and sim_clock.current_time else None
    except ImportError:
        sim_time = None
```

> [!NOTE]  
> `forward-type hint` with quotes avoids circular import. `SimulationClock` is in same package.

---

## Phase 1C: Sim-Mode ContextVar for trade_event_service

**File:** [trade_event_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/trade_event_service.py)

**Problem:** 5 sites check `get_warrior_sim_broker() is not None` as a "am I in sim?" boolean. In concurrent mode, the global sim broker won't be set per-context.

**Sites (all must be updated):**
- L96: `if get_warrior_sim_broker() is not None:`
- L230: `if get_warrior_sim_broker() is not None:`
- L498: `is_mock_market = get_warrior_sim_broker() is not None`
- L777: `"is_mock_market": get_warrior_sim_broker() is not None,`
- L804: `is_mock_market = get_warrior_sim_broker() is not None`

**Fix — Add ContextVar at top of file:**

```python
from contextvars import ContextVar

# ContextVar for sim mode detection (concurrent batch mode)
_is_sim_mode: ContextVar[bool] = ContextVar('is_sim_mode', default=False)

def set_sim_mode_ctx(value: bool) -> None:
    """Set sim mode for current async task context."""
    _is_sim_mode.set(value)

def is_sim_mode() -> bool:
    """Check if current context is in simulation mode."""
    if _is_sim_mode.get():
        return True
    # Fallback to legacy global check
    from nexus2.api.routes.warrior_sim_routes import get_warrior_sim_broker
    return get_warrior_sim_broker() is not None
```

Then replace each of the 5 sites with `is_sim_mode()`:
- L96: `if is_sim_mode():`
- L230: `if is_sim_mode():`
- L498: `is_mock_market = is_sim_mode()`
- L777: `"is_mock_market": is_sim_mode(),`
- L804: `is_mock_market = is_sim_mode()`

---

## Phase 1D: Monitor `_recently_exited` Isolation

**File:** [warrior_monitor.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor.py)

**No code changes needed here.** The `WarriorMonitor.__init__` (L53-107) already starts with clean dicts. The batch runner's `SimContext.create()` will create a new monitor per context and set:
- `monitor._recently_exited_file = None` (disable disk persistence)
- `monitor._recently_exited = {}` (explicit clean state)
- `monitor._recently_exited_sim_time = {}` (explicit clean state)

This phase is handled by the `SimContext.create()` wiring in Phase 5. Nothing to change in Phase 1.

---

## Phase 2: WarriorEngine + Scanner Per-Context

**File:** [warrior_engine.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine.py)

**No code changes needed to the engine itself.** The `WarriorEngine.__init__` (L61-122) already accepts `config`, `scanner`, and `monitor` as optional params:

```python
def __init__(
    self,
    config: Optional[WarriorEngineConfig] = None,
    scanner: Optional[WarriorScannerService] = None,
    monitor: Optional[WarriorMonitor] = None,
):
```

When called with all three params, it skips the global singleton fallbacks. The batch runner's `SimContext.create()` will:

```python
engine = WarriorEngine(
    config=WarriorEngineConfig(sim_only=True),
    scanner=WarriorScannerService(),
    monitor=monitor,
)
engine._pending_entries_file = None  # Disable disk persistence
```

**Validator note from R4 audit:** `apply_settings_to_config()` (L80-86) runs during `__init__` and mutates the config in-place with DB-saved values. Verify that `sim_only=True` is preserved after this mutation. If `apply_settings_to_config` overwrites `sim_only`, add a guard:

```python
# After L84:
self.config.sim_only = config.sim_only if config else False  # Preserve explicit sim_only
```

Check [warrior_settings.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/db/warrior_settings.py) `apply_settings_to_config()` to see if it touches `sim_only`.

---

## Summary of Files to Modify

| File | Changes |
|------|---------|
| `adapters/simulation/sim_clock.py` | Add ContextVar + `set_simulation_clock_ctx()` |
| `adapters/simulation/__init__.py` | Export `set_simulation_clock_ctx` |
| `adapters/simulation/mock_broker.py` | Add `clock` param to `__init__`, use in `sell_position()` |
| `domain/automation/trade_event_service.py` | Add `_is_sim_mode` ContextVar + `set_sim_mode_ctx()` + `is_sim_mode()`, update 5 call sites |
| `domain/automation/warrior_engine.py` | **Possibly**: guard `sim_only` after `apply_settings_to_config` |

## Commit Message

```
refactor: add ContextVar support for concurrent batch runner (Wave 1, Phases 1-2)

- SimulationClock: ContextVar override in get_simulation_clock()
- MockBroker: clock injection via constructor
- trade_event_service: is_sim_mode() ContextVar replaces global broker check
- Guard sim_only config preservation in WarriorEngine.__init__
```

## DO NOT

- Do NOT modify any files outside the list above
- Do NOT change `warrior_monitor.py` (Phase 1D is handled by SimContext wiring later)
- Do NOT start Phase 3 (`step_clock_ctx`) — that's Wave 2
- Do NOT create `SimContext` — that's Phase 5
