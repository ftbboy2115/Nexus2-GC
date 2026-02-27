# Handoff: Backend Specialist — L2 Phase 2 (Subscription Manager + Engine Integration)

## Task
Build the L2 subscription manager and wire L2 streaming into the Warrior engine lifecycle.

## Dependencies (from Phase 1)
- `nexus2/adapters/market_data/schwab_l2_streamer.py` — `SchwabL2Streamer` class, already implemented
- `nexus2/domain/market_data/l2_recorder.py` — `L2Recorder` class, already implemented
- `nexus2/domain/market_data/l2_types.py` — `L2BookSnapshot` type
- `nexus2/config.py` — `L2_ENABLED`, `L2_MAX_SYMBOLS`, `L2_SAMPLE_RATE_SECONDS`

## Important: Search Path
Use `C:\Dev\Nexus` for search tools (symlink to actual path with spaces).

---

## Files to Create/Modify

### [NEW] `nexus2/domain/market_data/l2_subscription_manager.py`

Dynamic L2 subscription manager that rotates symbols based on scanner output.

**Responsibilities:**
- Accept updated watchlist from scanner (list of `WatchedCandidate` objects)
- Rank candidates by `quality_score` (already exists on `WarriorCandidate`)
- Subscribe top N (capped by `L2_MAX_SYMBOLS`) to L2 streaming
- When new higher-priority candidates appear, unsubscribe lowest-priority and subscribe new ones
- Log all subscription changes for debugging: `[L2 Sub Manager]` prefix

**Key methods:**
- `__init__(self, streamer: SchwabL2Streamer, max_symbols: int = 5)`
- `async update_watchlist(self, watchlist: Dict[str, WatchedCandidate])` — called after each scan
- `get_active_subscriptions(self) -> List[str]` — currently subscribed symbols
- `get_status(self) -> dict` — status dict for engine status endpoint

**Design notes:**
- The `WatchedCandidate` type is defined in `nexus2/domain/automation/warrior_engine_types.py`
- It has a `.candidate` field which is a `WarriorCandidate` with `.quality_score()` method
- The `SchwabL2Streamer` has `subscribe(symbols)` and `unsubscribe(symbols)` async methods

---

### [MODIFY] `nexus2/domain/automation/warrior_engine.py`

Integration points (line numbers from Phase 1 commit `71960c2`):

#### 1. In `__init__` (around line 88-112)
Add L2-related instance variables:
```python
# L2 streaming (Phase 2)
self._l2_streamer = None
self._l2_recorder = None  
self._l2_sub_manager = None
```

#### 2. In `start()` (line 316-341)
After `await self.monitor.start()` (line 334), conditionally start L2:
```python
# Start L2 streaming if enabled
if app_config.L2_ENABLED:
    await self._start_l2()
```

Create helper `_start_l2()`:
- Instantiate `SchwabL2Streamer`, `L2Recorder`, `L2SubscriptionManager`
- Wire recorder as the streamer's update callback
- Call `await streamer.start()`
- Start recorder
- Log `[Warrior Engine] L2 streaming started`

#### 3. In `stop()` (line 343-366)
Before clearing watchlist (line 363), stop L2:
```python
# Stop L2 streaming
if self._l2_streamer:
    await self._stop_l2()
```

Create helper `_stop_l2()`:
- Stop recorder
- Call `await streamer.stop()`
- Log `[Warrior Engine] L2 streaming stopped`

#### 4. In `_run_scan()` (after line 503)
After `logger.info(f"[Warrior Scan] Found {len(result.candidates)} candidates, watching {len(self._watchlist)}")`, update L2 subscriptions:
```python
# Update L2 subscriptions based on current watchlist
if self._l2_sub_manager and self._watchlist:
    await self._l2_sub_manager.update_watchlist(self._watchlist)
```

#### 5. In `get_status()` (line 726-780)
Add L2 status to the returned dict:
```python
"l2": {
    "enabled": app_config.L2_ENABLED,
    "connected": self._l2_streamer.is_connected if self._l2_streamer else False,
    "subscriptions": self._l2_sub_manager.get_active_subscriptions() if self._l2_sub_manager else [],
} if app_config.L2_ENABLED else None,
```

---

## Constraints
- **Feature flag**: All L2 code guarded behind `if app_config.L2_ENABLED`
- **No breaking changes**: Engine must work identically when `L2_ENABLED=false` (default)
- **Import at use site**: Use lazy imports for L2 modules inside the `if` blocks to avoid import overhead when L2 is disabled
- **Do NOT add L2 data to entry decisions yet** — that's Phase 3

## Testable Claims (document these in your status report)
Focus on:
1. All new imports work
2. Engine starts/stops cleanly with `L2_ENABLED=false` (no behavior change)
3. Subscription manager correctly ranks by quality_score
4. Subscription manager respects max_symbols limit
5. `get_status()` includes L2 section when enabled
6. No changes to existing test behavior (`pytest nexus2/tests/ -v` passes)

> [!NOTE]
> **Testing will be handled by a separate Testing Specialist** after implementation. Document testable claims but do NOT write tests yourself.
