# Handoff: Backend Specialist — L2 Soft Entry Gate

## Task
Add an L2-based entry gate to the existing guard system. The gate checks order book conditions before allowing entries. **Defaults to `log_only` mode — zero behavior change until explicitly enabled.**

## Important: Search Path
Use `C:\Dev\Nexus` for search tools.

## Architecture Context

Entry guards live in `nexus2/domain/automation/warrior_entry_guards.py`:
- `check_entry_guards()` (line 35) — orchestrates all guards, returns `(can_enter, block_reason)`
- Existing guards: `_check_macd_gate`, `_check_position_guards`, `_check_spread_filter`, `validate_technicals`
- Called from `warrior_engine_entry.py:~1017`
- Engine instance is passed as first arg — has `self._l2_streamer` (may be `None`)

Signal functions in `nexus2/domain/market_data/l2_signals.py`:
- `detect_ask_wall(book, threshold_volume)` → `WallSignal | None`
- `get_spread_quality(book)` → `SpreadQuality`
- `detect_thin_ask(book)` → `ThinAskSignal | None`

Streamer: `engine._l2_streamer.get_snapshot(symbol)` → `L2BookSnapshot | None`

---

## Changes

### [MODIFY] `nexus2/domain/automation/warrior_entry_guards.py`

Add `_check_l2_gate()`:

```python
def _check_l2_gate(
    engine: "WarriorEngine",
    symbol: str,
    entry_price: Decimal,
) -> tuple[bool, str]:
    """
    L2 order book gate. Checks for ask walls and spread quality.
    
    Modes (from settings):
        log_only: Log L2 conditions but never block (default)
        warn: Log WARNING but still allow entry
        block: Actually reject the entry
    
    Returns:
        (True, "") if entry allowed
        (False, reason) if blocked (only in 'block' mode)
    """
```

**Logic:**
1. If L2 disabled or no streamer → return `(True, "")` immediately
2. Get snapshot: `engine._l2_streamer.get_snapshot(symbol)` → if None, return `(True, "")`
3. Check for ask wall within `l2_wall_proximity_pct` (default 1.0%) above entry price
   - `detect_ask_wall(book, threshold_volume=l2_wall_threshold_volume)`
   - If wall exists AND `wall.price <= entry_price * (1 + proximity_pct/100)` → trigger
4. Check spread quality: `get_spread_quality(book)`
   - If `quality == "wide"` → trigger (optionally)
5. Log the L2 assessment always (INFO level)
6. Based on mode:
   - `log_only`: always return `(True, "")`
   - `warn`: log WARNING, return `(True, "")`  
   - `block`: return `(False, f"L2 gate: ask wall {wall.volume} shares at ${wall.price}")`

**Call it from `check_entry_guards()`** — add after the existing spread filter check.

### [MODIFY] `nexus2/domain/automation/warrior_types.py` (or wherever settings live)

Add settings fields (check existing settings pattern — likely in warrior_types.py WarriorSettings):
```python
l2_gate_mode: str = "log_only"         # "log_only" | "warn" | "block"
l2_wall_threshold_volume: int = 10000  # Minimum volume to count as a wall
l2_wall_proximity_pct: float = 1.0     # Wall must be within X% above entry
```

---

## Design Constraints
- **FAIL-OPEN**: If L2 data unavailable, ALWAYS allow entry (don't block trades due to missing data)
- **Default mode = `log_only`**: Zero behavior change until Clay explicitly switches
- Guard everything with `try/except` — L2 failures must never crash the entry flow
- Use lazy imports for l2_signals inside the guard function
- All thresholds configurable via settings (not hardcoded)

## Testable Claims
1. `_check_l2_gate` returns `(True, "")` when L2_ENABLED=false
2. `_check_l2_gate` returns `(True, "")` when no snapshot available
3. In `log_only` mode, never returns `(False, ...)`
4. In `block` mode, returns `(False, reason)` when ask wall within proximity
5. Settings `l2_gate_mode`, `l2_wall_threshold_volume`, `l2_wall_proximity_pct` exist
6. `check_entry_guards()` calls `_check_l2_gate`
7. Existing tests pass (no regressions)

> [!NOTE]
> **Testing Specialist will validate separately.** Implementation only.
