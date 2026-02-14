# Audit 2: Trade Management Status Report

**Date**: 2026-02-13  
**Auditor**: Code Auditor (AI)  
**Scope**: Exit/trade management logic — active, disabled, and dead code

---

## A. File Inventory

| File | Lines | Key Functions | Imports From |
|------|-------|--------------|--------------|
| `warrior_monitor_exit.py` | 1177 | `evaluate_position`, `_check_base_hit_target`, `_check_home_run_exit`, `_check_time_stop`, `_check_profit_target`, `handle_exit` + 6 more | `warrior_types`, `trade_event_service`, `warrior_db` |
| `warrior_monitor.py` | 730 | `_create_new_position`, `_check_all_positions`, `_evaluate_position` (delegates to exit module) | `warrior_types`, `warrior_monitor_exit`, `warrior_monitor_scale`, `warrior_monitor_sync` |
| `warrior_monitor_scale.py` | 285 | `check_scale_opportunity`, `execute_scale_in` | `warrior_types` |
| `warrior_types.py` | 175 | `WarriorExitReason`, `WarriorMonitorSettings`, `WarriorPosition` | — |
| `warrior_engine.py` | 760 | `_handle_profit_exit` (re-entry callback) | `warrior_monitor`, `warrior_scanner_service` |

---

## B. Dependency Graph

```
warrior_monitor_exit.py
  └── imports: warrior_types.py, trade_event_service.py, warrior_db.py
  └── imported by: warrior_monitor.py

warrior_monitor.py
  └── imports: warrior_types.py, warrior_monitor_exit.py, warrior_monitor_scale.py, warrior_monitor_sync.py
  └── imported by: warrior_engine.py, warrior_sim_routes.py

warrior_monitor_scale.py
  └── imports: warrior_types.py
  └── imported by: warrior_monitor.py

warrior_types.py
  └── imports: (none project-internal)
  └── imported by: ALL above files

warrior_engine.py
  └── imports: warrior_monitor.py, warrior_scanner_service.py
  └── imported by: api routes
```

---

## C. Findings Table

### C1: Phase A — Candle-Low Trail is ACTIVE

**Finding**: `_check_base_hit_target` uses candle-low trailing when `base_hit_candle_trail_enabled=True` (the default).  
**File**: `nexus2/domain/automation/warrior_types.py`  
**Line**: 114  
**Code**:
```python
    base_hit_candle_trail_enabled: bool = True  # Enable candle-low trailing for base_hit
    base_hit_trail_activation_cents: Decimal = Decimal("10")  # Start trailing after +10¢
```
**Verify**:
```powershell
python -c "lines=open('nexus2/domain/automation/warrior_types.py',encoding='utf-8').readlines(); [print(f'L{i+1}: {l.rstrip()}') for i,l in enumerate(lines) if 'candle_trail' in l.lower()]"
```

**Trail logic is reachable** via `evaluate_position` → `_check_base_hit_target` (L986-990 in exit module):
```python
    if exit_mode == "base_hit":
        signal = await _check_base_hit_target(monitor, position, current_price, r_multiple)
```
**File**: `nexus2/domain/automation/warrior_monitor_exit.py`  
**Line**: 699  
**Code** (activation gate):
```python
    if s.base_hit_candle_trail_enabled and monitor._get_intraday_candles:
        activation_cents = s.base_hit_trail_activation_cents
```
**Verify**:
```powershell
python -c "lines=open('nexus2/domain/automation/warrior_monitor_exit.py',encoding='utf-8').readlines(); [print(f'L{i+1}: {l.rstrip()}') for i,l in enumerate(lines) if 'candle_trail_enabled' in l]"
```

---

### C2: Phase B — Time Stop is WIRED but DISABLED by default

**Finding**: `_check_time_stop` exists (L319-372) and IS wired into `evaluate_position` at L957-960 as "CHECK 0.7". However, `enable_time_stop` defaults to `False`.  

**File**: `nexus2/domain/automation/warrior_types.py`  
**Line**: 83  
**Code**:
```python
    enable_time_stop: bool = False  # Disabled: kills winners (NPT -$1740). Ross accepts losses.
    time_stop_seconds: int = 600  # 10 minutes without momentum
    breakout_hold_threshold: float = 0.5  # Must hold 50% of breakout
```

**Wiring proof** in `evaluate_position`:  
**File**: `nexus2/domain/automation/warrior_monitor_exit.py`  
**Line**: 957-960  
**Code**:
```python
    # CHECK 0.7: Time Stop (no momentum)
    signal = await _check_time_stop(monitor, position, current_price, r_multiple)
    if signal:
        return signal
```

**Guard** inside `_check_time_stop`:  
**File**: `nexus2/domain/automation/warrior_monitor_exit.py`  
**Line**: 341-342  
**Code**:
```python
    if not s.enable_time_stop:
        return None
```

**Verify**:
```powershell
python -c "lines=open('nexus2/domain/automation/warrior_monitor_exit.py',encoding='utf-8').readlines(); [print(f'L{i+1}: {l.rstrip()}') for i,l in enumerate(lines) if 'time_stop' in l]"
```

---

### C3: Phase C — `base_hit_stop_cents` is WIRED into `_create_new_position`

**Finding**: `_create_new_position` uses `base_hit_stop_cents` for the mental stop calculation when exit mode is `base_hit`.  

**File**: `nexus2/domain/automation/warrior_monitor.py`  
**Line**: 401-409  
**Code**:
```python
        # Mental stop: Use base_hit_stop_cents for base_hit mode, mental_stop_cents otherwise
        # Base hit = tight 15¢ stop (tight scalp), Home run = wide 50¢ stop (give room)
        exit_mode = exit_mode_override or s.session_exit_mode
        if exit_mode == "base_hit":
            mental_stop = entry_price - s.base_hit_stop_cents / 100
            logger.debug(
                f"[Warrior] {symbol}: Base hit stop = ${mental_stop:.2f} "
                f"(-{s.base_hit_stop_cents}¢ from entry)"
            )
        else:
            mental_stop = entry_price - s.mental_stop_cents / 100
```

**Default value**:  
**File**: `nexus2/domain/automation/warrior_types.py`  
**Line**: 112  
**Code**:
```python
    base_hit_stop_cents: Decimal = Decimal("15")  # Mental stop at -15¢
```

**Verify**:
```powershell
python -c "lines=open('nexus2/domain/automation/warrior_monitor.py',encoding='utf-8').readlines(); [print(f'L{i+1}: {l.rstrip()}') for i,l in enumerate(lines) if 'base_hit_stop_cents' in l]"
```

---

### C4: Exit Path Map (execution order in `evaluate_position`)

**File**: `nexus2/domain/automation/warrior_monitor_exit.py`  
**Lines**: 889-997

| # | Check | Function | Line | Active? | Guard Setting |
|---|-------|----------|------|---------|---------------|
| 0 | After-Hours Exit | `_check_after_hours_exit` | 948 | ✅ YES | `enable_after_hours_exit=True` |
| 0.5 | Spread Exit | `_check_spread_exit` | 953 | ✅ YES | `enable_spread_exit=True` |
| 0.7 | Time Stop | `_check_time_stop` | 958 | ❌ DISABLED | `enable_time_stop=False` |
| 1 | Stop Hit | `_check_stop_hit` | 963 | ✅ YES | Always on (no guard) |
| 2 | Candle-Under-Candle | `_check_candle_under_candle` | 968 | ✅ YES | `enable_candle_under_candle=True` |
| 3 | Topping Tail | `_check_topping_tail` | 973 | ✅ YES | `enable_topping_tail=True` |
| 4a | Base Hit Target | `_check_base_hit_target` | 988 | ✅ YES (if mode=base_hit) | `session_exit_mode="base_hit"` |
| 4b | Home Run Exit | `_check_home_run_exit` | 993 | ✅ YES (if mode=home_run) | `session_exit_mode="home_run"` |

**Verify** (shows the ordered check calls):
```powershell
python -c "lines=open('nexus2/domain/automation/warrior_monitor_exit.py',encoding='utf-8').readlines(); [print(f'L{i+1}: {l.rstrip()}') for i,l in enumerate(lines[946:996]) if '_check_' in lines[946+i]]"
```

---

### C5: Dead Code — `_check_profit_target` is ORPHANED

**Finding**: `_check_profit_target` is defined at L618-670 but is **never called** from `evaluate_position` or anywhere else. It was superseded by mode-specific checks (`_check_base_hit_target` and `_check_home_run_exit`).

**File**: `nexus2/domain/automation/warrior_monitor_exit.py`  
**Line**: 618-670  
**Code** (definition):
```python
async def _check_profit_target(
    monitor: "WarriorMonitor",
    position: WarriorPosition,
    current_price: Decimal,
    r_multiple: float,
) -> Optional[WarriorExitSignal]:
    """Check for profit target hit (partial exit)."""
```

**Verify** (should show ONLY the definition, no callers):
```powershell
python -c "lines=open('nexus2/domain/automation/warrior_monitor_exit.py',encoding='utf-8').readlines(); hits=[f'L{i+1}: {l.rstrip()}' for i,l in enumerate(lines) if '_check_profit_target' in l]; print('\n'.join(hits)); print(f'\nTotal references: {len(hits)} (1=dead code, definition only)')"
```

---

### C6: Dead Code — `BREAKOUT_FAILURE` enum is never GENERATED

**Finding**: `WarriorExitReason.BREAKOUT_FAILURE` is defined in the enum and referenced in `handle_exit` mappings, but **no exit check ever returns a signal with this reason**. There is no `_check_breakout_failure` function.

**File**: `nexus2/domain/automation/warrior_types.py`  
**Line**: 27  
**Code**:
```python
    BREAKOUT_FAILURE = "breakout_failure"  # Failed to hold breakout
```

**References** (only in enum definition and exit handler mappings, never as a generated signal):
- L27: Enum definition
- L1058 in exit module: Mapping in `handle_exit` → `exit_reason_map`
- L1162 in exit module: Used in `stop_reasons` set for 2-strike rule

**Verify**:
```powershell
python -c "lines=open('nexus2/domain/automation/warrior_monitor_exit.py',encoding='utf-8').readlines(); hits=[f'L{i+1}: {l.rstrip()}' for i,l in enumerate(lines) if 'BREAKOUT_FAILURE' in l]; print('\n'.join(hits)); print(f'\nTotal: {len(hits)} refs (all in mappings, none generating this reason)')"
```

---

### C7: Dead Setting — `breakout_hold_threshold` is defined but NEVER READ

**Finding**: `breakout_hold_threshold` is defined in `WarriorMonitorSettings` but is never accessed by any code. It was presumably intended for a `_check_breakout_failure` function that was never written.

**File**: `nexus2/domain/automation/warrior_types.py`  
**Line**: 85  
**Code**:
```python
    breakout_hold_threshold: float = 0.5  # Must hold 50% of breakout
```

**Verify**:
```powershell
python -c "import pathlib; hits=[]; [hits.extend([f'{f.name}:L{i+1}: {l.rstrip()}' for i,l in enumerate(f.read_text(encoding='utf-8').splitlines()) if 'breakout_hold_threshold' in l]) for f in pathlib.Path('nexus2/domain/automation').glob('*.py')]; print('\n'.join(hits)); print(f'\nTotal: {len(hits)} (should be 1 = definition only)')"
```

---

### C8: Implicit Setting — `topping_tail_grace_seconds` used via `getattr` but NOT in `WarriorMonitorSettings`

**Finding**: `_check_topping_tail` uses `getattr(s, 'topping_tail_grace_seconds', 120)` to read a grace period, but this field is NOT defined in `WarriorMonitorSettings`. It always falls back to the hardcoded default of 120s.

**File**: `nexus2/domain/automation/warrior_monitor_exit.py`  
**Line**: 572  
**Code**:
```python
    grace_seconds = getattr(s, 'topping_tail_grace_seconds', 120)  # Default 2 minutes
```

**File**: `nexus2/domain/automation/warrior_types.py` — **NOT PRESENT**

**Verify**:
```powershell
python -c "lines=open('nexus2/domain/automation/warrior_types.py',encoding='utf-8').readlines(); hits=[f'L{i+1}: {l.rstrip()}' for i,l in enumerate(lines) if 'topping_tail_grace' in l]; print('\n'.join(hits) if hits else 'NOT FOUND in warrior_types.py')"
```

---

## D. Phase Status Summary

| Phase | Feature | Status | Default | Controlled By |
|-------|---------|--------|---------|---------------|
| **A** | Candle-low trailing | ✅ **ACTIVE** | Enabled, activates at +10¢ | `base_hit_candle_trail_enabled=True` |
| **B** | Time stop | ⚠️ **WIRED, DISABLED** | Disabled (kills winners NPT -$1740) | `enable_time_stop=False` |
| **C** | `base_hit_stop_cents` wiring | ✅ **ACTIVE** | 15¢ stop for base_hit mode | `base_hit_stop_cents=Decimal("15")` |
| **D** | Context-aware topping tail | ❌ **NOT STARTED** | — | — |
| **E** | Dead code cleanup | ❌ **NOT STARTED** | — | — |

---

## E. Dead Code Summary (Phase E candidates)

| Item | Type | Location | Recommendation |
|------|------|----------|----------------|
| `_check_profit_target` | Orphaned function | exit.py L618-670 | **DELETE** — replaced by mode-specific checks |
| `BREAKOUT_FAILURE` enum | Unreachable reason | types.py L27 | **KEEP** (reserved for future use) or DELETE |
| `breakout_hold_threshold` | Unused setting | types.py L85 | **DELETE** — no code reads it |
| `topping_tail_grace_seconds` | Implicit via getattr | exit.py L572 | **ADD** to `WarriorMonitorSettings` or hardcode |

---

## F. Refactoring Recommendations

| # | Issue | Files | Action | Effort |
|---|-------|-------|--------|--------|
| 1 | `_check_profit_target` is dead code (53 lines) | exit.py | Delete function | S |
| 2 | `breakout_hold_threshold` setting unused | types.py | Delete field | S |
| 3 | `topping_tail_grace_seconds` not in settings | types.py, exit.py | Add field to `WarriorMonitorSettings` | S |
| 4 | `candle_exit_grace_seconds` also used via `getattr` (L438) | exit.py | Verify — already in settings (L79), `getattr` is unnecessary | S |
