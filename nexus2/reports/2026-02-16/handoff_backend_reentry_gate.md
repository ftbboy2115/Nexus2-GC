# Backend Specialist Handoff: Re-entry Quality Gate Implementation

## Task

Implement the **Re-entry Quality Gate** per the technical specification at:
`nexus2/reports/2026-02-16/spec_reentry_quality_gate.md`

Read that spec thoroughly before writing any code. It contains verified code evidence, exact line numbers, and a wiring checklist.

---

## Summary

Add a guard in `check_entry_guards` that blocks re-entries on symbols where the last closed trade was a loss. This prevents "revenge trading" (re-entering a stock that already stopped out).

**Approach:** DB-query in the guard (lowest blast radius — 4 files, ~15 lines of new code, no callback signature changes).

---

## Implementation Checklist

### 1. Add DB Function — `get_last_trade_pnl`

**File:** `nexus2/db/warrior_db.py`

Add a function that queries the most recent closed trade for a symbol (today's session only) and returns its realized P&L. Filter by today's date to avoid stale data from prior sessions.

> [!IMPORTANT]
> Before implementing, run `SELECT * FROM warrior_trades LIMIT 1` (or check the ORM model) to verify the exact column names for symbol, P&L, status, and exit time. Do NOT guess column names.

### 2. Add Toggle — `block_reentry_after_loss`

**File:** `nexus2/domain/automation/warrior_types.py`
**Class:** `WarriorMonitorSettings` (around L115, in the "Re-Entry After Profit Exit" section)

```python
block_reentry_after_loss: bool = True  # Block re-entry if last exit was a loss (no revenge trading)
```

### 3. Wire Toggle Persistence

**File:** `nexus2/db/warrior_monitor_settings.py`

Add to `apply_monitor_settings` (deserialization, around L120):
```python
if "block_reentry_after_loss" in settings:
    monitor_settings_obj.block_reentry_after_loss = settings["block_reentry_after_loss"]
```

Add to `get_monitor_settings_dict` (serialization, around L160):
```python
"block_reentry_after_loss": monitor_settings_obj.block_reentry_after_loss,
```

### 4. Add Guard Clause

**File:** `nexus2/domain/automation/warrior_entry_guards.py`
**Function:** `check_entry_guards` (L35-149)
**Insert after:** Re-entry cooldown checks (around L137), before spread filter (L139)

```python
# RE-ENTRY QUALITY GATE: Block re-entry after loss (Ross: no revenge trading)
if watched.entry_attempt_count > 0 and engine.monitor.settings.block_reentry_after_loss:
    from nexus2.db.warrior_db import get_last_trade_pnl
    last_pnl = get_last_trade_pnl(symbol)
    if last_pnl is not None and last_pnl < 0:
        reason = f"Re-entry BLOCKED after loss (P&L=${last_pnl:.2f}) - no revenge trading"
        tml.log_warrior_guard_block(symbol, "reentry_loss", reason, _trigger, _price)
        return False, reason
```

> [!TIP]
> Guard with `entry_attempt_count > 0` to skip the DB query on first entries (optimization — no prior trade to check).

### 5. Add Unit Tests

Add to `nexus2/tests/unit/automation/test_warrior_monitor.py` (or create a new `test_reentry_quality_gate.py`):

1. **Test: re-entry blocked after loss** — Mock `get_last_trade_pnl` → `-100.0`, verify `check_entry_guards` returns `(False, "...BLOCKED...")`
2. **Test: re-entry allowed after profit** — Mock → `+50.0`, verify `(True, "")`
3. **Test: re-entry allowed when no prior trade** — Mock → `None`, verify `(True, "")`
4. **Test: gate disabled** — Set `block_reentry_after_loss=False`, verify entry proceeds regardless
5. **Test: gate skipped on first entry** — Set `entry_attempt_count=0`, verify no DB query

---

## Verification Commands

After implementation, run:

```powershell
# Settings persistence check
python -c "from nexus2.db.warrior_monitor_settings import get_monitor_settings_dict; from nexus2.domain.automation.warrior_types import WarriorMonitorSettings; d = get_monitor_settings_dict(WarriorMonitorSettings()); print('block_reentry_after_loss:', d.get('block_reentry_after_loss'))"
```
Expected: `block_reentry_after_loss: True`

```powershell
# Unit tests
python -m pytest nexus2/tests/ -v -k "reentry" 2>&1 | Select-Object -First 40
```

---

## Write Status Report To

`nexus2/reports/2026-02-16/status_reentry_quality_gate.md`
