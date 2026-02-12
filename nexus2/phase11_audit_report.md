# Phase 11 Audit Report

**Auditor**: Code Auditor Agent  
**Date**: 2026-02-12  
**Scope**: Console errors (C1-C3), TML gap (C4), PSM re-entry flow (C5), adversarial checks (A1-A3)  
**Handoff**: `phase11_auditor_handoff.md`

---

## Summary

| # | Claim | Verdict | Severity |
|---|-------|---------|----------|
| C1 | `_pending_entries_file` None crash | **CONFIRMED** | Medium (caught by `except`) |
| C2 | `_recently_exited_file` None crash | **CONFIRMED** | Medium (caught by `except`) |
| C3 | `_get_quote_with_spread` float/dict mismatch | **CONFIRMED** | **High** (silent logic failure) |
| C4 | Missing TML event for re-entry | **CONFIRMED** | Low (observability gap) |
| C5 | PSM re-entry flow integrity | **SOUND** | N/A |
| A1 | Fail-closed violation in spread filter | **FOUND** | Medium |
| A2 | C3 also affects entry guards | **FOUND** | **High** |
| A3 | Crash ordering in `handle_exit` | **FOUND** | Medium (theoretical) |

---

## C1: `_pending_entries_file` None Crash

**Verdict: CONFIRMED**

### Evidence

**Root cause**: `sim_context.py:62` sets `engine._pending_entries_file = None` to disable disk persistence.

```python
# sim_context.py line 62
engine._pending_entries_file = None
```

**Crash site**: `warrior_engine.py:191` calls `.parent.mkdir()` on `None`:

```python
# warrior_engine.py lines 186-195
def _save_pending_entries(self):
    try:
        import json
        data = {symbol: dt.isoformat() for symbol, dt in self._pending_entries.items()}
        self._pending_entries_file.parent.mkdir(parents=True, exist_ok=True)  # ← CRASH: None.parent
        with open(self._pending_entries_file, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning(f"[Warrior Engine] Failed to save pending entries: {e}")
```

**All callers** (all crash in sim):
| Caller | File | Line |
|--------|------|------|
| `_save_pending_entries` (direct) | `warrior_engine.py` | 191 |
| `clear_pending_entry` | `warrior_engine.py` | 201 |
| Entry execution | `warrior_entry_execution.py` | 116 |
| Entry (engine_entry) | `warrior_engine_entry.py` | 1087 |

**Impact**: The `except Exception` at line 194 catches the `AttributeError`, so this produces a console warning rather than a crash. The save silently fails, which is **acceptable** for sim (no persistence needed), but generates noise in logs.

**`_load_pending_entries`** at line 153 also affected — called during `__init__` at line 97. However, `sim_context.py:62` sets `_pending_entries_file = None` *after* construction, and `SimContext.create()` builds a new `WarriorEngine()` which calls `_load_pending_entries` with the default path before the override. This is **not a crash** because the default path is valid.

### Verification Command

```powershell
Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "_pending_entries_file"
Select-String -Path "nexus2\domain\automation\warrior_engine.py" -Pattern "_pending_entries_file.parent"
```

---

## C2: `_recently_exited_file` None Crash

**Verdict: CONFIRMED**

### Evidence

**Root cause**: `sim_context.py:42` sets `monitor._recently_exited_file = None`:

```python
# sim_context.py line 42
monitor._recently_exited_file = None
```

**Crash site**: `warrior_monitor.py:138` calls `.parent.mkdir()` on `None`:

```python
# warrior_monitor.py lines 132-142
def _save_recently_exited(self):
    try:
        import json
        data = {symbol: dt.isoformat() for symbol, dt in self._recently_exited.items()}
        self._recently_exited_file.parent.mkdir(parents=True, exist_ok=True)  # ← CRASH: None.parent
        with open(self._recently_exited_file, "w") as f:
            json.dump(data, f)
    except Exception as e:
        logger.warning(f"[Warrior] Failed to save recently exited: {e}")
```

**All callers** (crash in sim):
| Caller | File | Line |
|--------|------|------|
| `handle_exit` | `warrior_monitor_exit.py` | 1004 |
| Manual API | `warrior_positions.py` | 371 |

**Impact**: Same as C1 — caught by `except`, produces console warning, save silently fails. Acceptable behavior but noisy.

### Verification Command

```powershell
Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "_recently_exited_file"
Select-String -Path "nexus2\domain\automation\warrior_monitor.py" -Pattern "_recently_exited_file.parent"
```

---

## C3: `_get_quote_with_spread` Float/Dict Mismatch

**Verdict: CONFIRMED — HIGH SEVERITY**

### Evidence

**Contract mismatch**: In sim mode, `_get_quote_with_spread` is wired to `sim_get_price`, which returns a **raw float**. But all downstream callers expect a **dict** with `.get()` access.

**Wiring sites** (both wire the same broken pattern):

1. **Sequential runner** (`warrior_sim_routes.py:981`):
   ```python
   get_quote_with_spread=sim_get_price,  # Returns float!
   ```

2. **Concurrent runner** (`sim_context.py:370`):
   ```python
   get_quote_with_spread=sim_get_price,  # Returns float!
   ```

**`sim_get_price` definition** (`warrior_sim_routes.py:858-864`):
```python
async def sim_get_price(symbol: str):
    sim_broker = get_warrior_sim_broker()
    if sim_broker:
        price = sim_broker.get_price(symbol)  # Returns float
        if price is not None:
            return price  # ← Returns float, NOT dict
    return None
```

**Live version** (`warrior_callbacks.py:168`) returns:
```python
return {"price": price, "bid": price * 0.999, "ask": price * 1.001}  # ← Returns dict
```

**Affected callers** (all call `.get()` on the result):

| Caller | File | Line | Impact |
|--------|------|------|--------|
| Spread exit check | `warrior_monitor_exit.py` | 273 | `float.get("liquidity_status")` → `AttributeError` → silent failure (wrapped in try/except), **spread exit never triggers in sim** |
| Scale-in limit price | `warrior_monitor_scale.py` | 180 | `float.get("ask")` → `AttributeError` → falls back to stale price, **scale orders may use wrong limit price** |
| Entry spread filter | `warrior_entry_guards.py` | 283 | `float.get("bid")` → `AttributeError` → falls through to `return True`, **spread filter bypassed in sim** |

### Why This Is High Severity

In **live mode**, the `create_get_quote_with_spread` function has sim detection (lines 163-170) that checks for a `MockBroker` and returns a proper dict. But this only applies when using `warrior_broker_routes.py`'s wiring. The **sequential runner** and **concurrent runner** both bypass this by directly wiring `sim_get_price`.

The result is that three safety mechanisms are silently disabled in sim:
1. **Spread-based exit** — never triggers (bad for testing exit logic)
2. **Fresh quote for scale limit** — falls back to stale price
3. **Entry spread filter** — always passes (bad for testing entry guards)

### Fix

Replace `sim_get_price` with a wrapper that returns the expected dict format:

```python
async def sim_get_quote_with_spread(symbol: str):
    sim_broker = get_warrior_sim_broker()
    if sim_broker:
        price = sim_broker.get_price(symbol)
        if price is not None:
            return {"price": price, "bid": price * 0.999, "ask": price * 1.001}
    return None
```

### Verification Command

```powershell
Select-String -Path "nexus2\api\routes\warrior_sim_routes.py" -Pattern "get_quote_with_spread=sim_get_price"
Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "get_quote_with_spread=sim_get_price"
Select-String -Path "nexus2\domain\automation\warrior_monitor_exit.py" -Pattern "spread_data.get"
Select-String -Path "nexus2\domain\automation\warrior_monitor_scale.py" -Pattern "spread_data.get"
Select-String -Path "nexus2\domain\automation\warrior_entry_guards.py" -Pattern "spread_data.get"
```

---

## C4: Missing TML Event for Re-Entry

**Verdict: CONFIRMED**

### Evidence

`_handle_profit_exit` at `warrior_engine.py:204-235` uses only `logger.info` — no TML event:

```python
# warrior_engine.py line 231-234
logger.info(
    f"[Warrior Engine] {symbol}: Re-entry ENABLED after profit exit @ ${exit_price:.2f} "
    f"(attempt #{watched.entry_attempt_count})"
)
```

**No corresponding TML method exists** in `trade_event_service.py`:
- `log_warrior_entry` ✓
- `log_warrior_exit` ✓
- `log_warrior_scale_in` ✓
- `log_warrior_stop_moved` ✓
- `log_warrior_guard_block` ✓
- `log_warrior_reentry_enabled` ✗ ← **MISSING**

**Impact**: Low severity. Re-entry enablement is invisible in the TML audit trail. When debugging why a second entry happened, there's no TML event linking the profit exit to the re-entry decision.

### Fix

Add `log_warrior_reentry_enabled` to `trade_event_service.py` and call it from `_handle_profit_exit`.

### Verification Command

```powershell
Select-String -Path "nexus2\domain\automation\trade_event_service.py" -Pattern "reentry|re_entry|re.entry"
Select-String -Path "nexus2\domain\automation\warrior_engine.py" -Pattern "trade_event_service" -Context 0,2 | Select-String -Pattern "_handle_profit_exit" -Context 5
```

---

## C5: PSM Re-Entry Flow Integrity

**Verdict: SOUND — No issues found**

### Analysis

1. **`CLOSED` is terminal** (`position_state_machine.py:31`): No transitions out of `CLOSED`. Re-entry cannot mutate a closed position.

2. **Re-entry creates a new `position_id`**: `_handle_profit_exit` (line 222-223) resets `entry_triggered` and `position_opened` on the `WatchedCandidate`, not the position. The next entry creates a fresh position with a new UUID.

3. **Cooldown mechanisms exist**:
   - **Live mode**: `warrior_entry_guards.py:120-125` checks `_recently_exited` with wall-clock time
   - **Sim mode**: `warrior_entry_guards.py:128-137` checks `_recently_exited_sim_time` with sim clock
   - Both are properly wired and tested

4. **No race condition**: `handle_exit` flow at lines 1000-1037 is sequential:
   1. Track `_recently_exited` (line 1003)
   2. Save to disk (line 1004) — may crash in sim but caught
   3. Call `_on_profit_exit` callback (line 1019) — enables re-entry
   4. Count stop failures (line 1034)
   5. Remove position from monitor (line 1037)

   The re-entry enable happens *after* the cooldown is set and *before* position removal. This ordering is correct — the entry guard will check the cooldown before allowing re-entry.

5. **Entry guard protection**: Even after `_handle_profit_exit` resets `entry_triggered`, the next entry must pass all guards (MACD gate, technical validation, spread filter, cooldowns). This prevents immediate re-entry.

---

## Adversarial Checks

### A1: Fail-Closed Violation in Entry Spread Filter

**FOUND — Medium Severity**

`warrior_entry_guards.py:303-306`:
```python
elif bid <= 0 or ask <= 0:
    logger.warning(
        f"[Warrior Entry] {symbol}: No valid bid/ask data "
        f"(bid=${bid}, ask=${ask}) - proceeding with caution"  # ← VIOLATION
    )
```

**Violation**: The fail-closed mandate states *"Better to not trade than trade blind."* When bid/ask data is invalid (zero or negative), the function **proceeds** instead of blocking. This is a direct contradiction of the golden rule.

Lines 307-308 also violate:
```python
except Exception as e:
    logger.warning(f"[Warrior Entry] {symbol}: Spread check failed: {e} - proceeding")
```

Both cases should `return False, reason, None` instead of falling through to `return True`.

### A2: C3 Affects Entry Guards (Additional Impact)

**FOUND — High Severity (extension of C3)**

The C3 type mismatch also hits `warrior_entry_guards.py:281-283`:
```python
spread_data = await engine._get_quote_with_spread(symbol)
if spread_data:  # True (float is truthy)
    bid = spread_data.get("bid", 0)  # ← AttributeError: 'float' has no .get()
```

This crashes, gets caught by the `except` at line 307, and falls through to `return True, "", current_ask` — meaning the spread filter is **completely bypassed** in sim mode. Combined with A1, the entry spread guard has **two independent bypass paths**.

### A3: Crash Ordering in `handle_exit`

**FOUND — Medium Severity (theoretical)**

In `warrior_monitor_exit.py:1003-1037`, `_save_recently_exited()` at line 1004 runs **before** `remove_position()` at line 1037. If `_save_recently_exited` crashes *and* the `except` doesn't catch it (currently it does), position cleanup would be skipped.

Currently mitigated by the `try/except` in `_save_recently_exited()`, but the ordering is fragile. A safer pattern would be to move `_save_recently_exited()` after `remove_position()`, or use a `finally` block.

**Actual risk in sim**: The crash at line 1004 (from C2) is caught, so execution continues to line 1037 and position is properly removed. No actual bug today, but the ordering is a latent risk.

---

## Recommended Fix Priority

| Priority | Item | Effort |
|----------|------|--------|
| 1 | **C3 + A2**: Fix `sim_get_price` → `sim_get_quote_with_spread` returning dict | Small |
| 2 | **A1**: Make entry spread filter fail-closed on invalid data | Small |
| 3 | **C1/C2**: Add `if self._pending_entries_file is None: return` guard | Small |
| 4 | **C4**: Add `log_warrior_reentry_enabled` TML event | Small |
| 5 | **A3**: Reorder `_save_recently_exited` after `remove_position` | Small |

All fixes are small, isolated, and low-risk. C3+A2 is the highest priority because it silently disables three safety mechanisms in simulation mode.
