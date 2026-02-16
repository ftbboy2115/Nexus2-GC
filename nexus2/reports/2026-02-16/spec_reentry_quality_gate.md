# Re-entry Quality Gate — Technical Specification

**Date:** 2026-02-16  
**Author:** Backend Planner (Research Agent)  
**Status:** READY FOR REVIEW  

---

## 1. Goal

Block re-entries after a losing exit on the same symbol. If the last exit for a symbol resulted in `pnl < 0`, the bot must refuse to re-enter that symbol for the remainder of the session, aligning with Ross Cameron's "no revenge trading" principle.

> [!IMPORTANT]
> This is a **single-loss block**, not cumulative P&L tracking. One loss → blocked forever (for that session).

---

## 2. Answers to Open Questions

### Q1: How do MNTS/MLEC re-enter after a loss?

**Finding:** There are **two independent re-entry paths**, not just one.

**Path A — `_on_profit_exit` callback** (profit exits only):
- Fires at [warrior_monitor_exit.py:1434-1443](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py#L1434-L1443)
- Only triggered when `signal.reason == PROFIT_TARGET`
- Calls `_handle_profit_exit` in engine which resets `entry_triggered = False` and `position_opened = False`

**Path B — PMH pullback reset** (any exit, including losses):
- At [warrior_engine_entry.py:548-550](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py#L548-L550):
```python
if watched.entry_triggered and watched.last_below_pmh:
    watched.last_below_pmh = False
    watched.entry_triggered = False  # Reset to allow new entry attempt
```
- This fires whenever price drops below PMH then re-breaks above — **regardless of whether the previous exit was a loss or profit**
- The `WatchedCandidate` remains in the watchlist after a stop-out (it's never removed)
- As price oscillates around PMH, this path automatically resets `entry_triggered`

**Conclusion:** MNTS and MLEC re-enter via **Path B**. After a stop-out, price drops below PMH, then when it breaks back above, `entry_triggered` resets and a new entry attempt fires — with zero P&L awareness.

---

### Q2: End-to-End Re-entry Flow

```
1. EXIT: evaluate_position() → signal(MENTAL_STOP) → handle_exit()
   ├── _recently_exited[symbol] = now                    [L1424]
   ├── _recently_exited_sim_time[symbol] = sim_time      [L1427-1429]
   ├── Does NOT call _on_profit_exit (loss exit)         [L1434-1437]
   ├── _record_symbol_fail(symbol)                       [L1454-1455]
   └── remove_position(position_id)                      [L1459]

2. WATCHLIST: WatchedCandidate remains in engine._watchlist
   ├── entry_triggered = True (still set from original entry)
   ├── position_opened = True (still set)
   └── Symbol stays in scan loop

3. PRICE DROPS BELOW PMH:
   └── check_entry_triggers → current_price < watched.pmh
       └── watched.last_below_pmh = True                 [L522]

4. PRICE BREAKS ABOVE PMH:
   └── check_entry_triggers → current_price >= watched.pmh
       ├── entry_triggered=True AND last_below_pmh=True  [L548]
       ├── entry_triggered = False  ← RE-ENTRY UNLOCKED  [L550]
       └── entry_attempt_count += 1                       [L551]

5. RE-ENTRY CHECK:
   └── Pattern competition → winner → enter_position()
       └── check_entry_guards() → checks cooldown, etc.
           └── NO P&L CHECK EXISTS → entry proceeds
```

---

### Q3: Will the gate accidentally block scale-adds?

**Answer: No. Scale-adds are completely independent.**

Scale-adds flow through:
```
_check_all_positions() → _check_scale_opportunity()
  → warrior_monitor_scale.check_scale_opportunity()     [L31-155]
  → warrior_monitor_scale.execute_scale_in()            [L163-333]
```

This path:
- Operates on `WarriorPosition` objects (in the monitor), NOT `WatchedCandidate` objects (in the engine)
- Never calls `check_entry_guards`
- Has its own independent guards (cooldown, stop buffer, pullback zone, PSM status)

**Verified at:** [warrior_monitor.py:583-589](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_monitor.py#L583-L589)

> [!TIP]
> The gate should ONLY be added to `check_entry_guards` in `warrior_entry_guards.py`, which is exclusively on the engine's entry path. Scale-adds are structurally safe.

---

### Q4: A/B Toggle Wiring Pattern

The established pattern for A/B toggles:

| Step | File | Example |
|------|------|---------|
| 1. Define field | [warrior_types.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_types.py) `WarriorMonitorSettings` | `enable_improved_scaling: bool = False` (L168) |
| 2. Serialize | [warrior_monitor_settings.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/db/warrior_monitor_settings.py) `get_monitor_settings_dict` | `"enable_improved_scaling": obj.enable_improved_scaling` (L160) |
| 3. Deserialize | Same file, `apply_monitor_settings` | `if "enable_improved_scaling" in settings: ...` (L120-121) |
| 4. Guard logic | Target file (e.g., `warrior_entry_guards.py`) | `if s.block_reentry_after_loss: ...` |

**Pattern for the new gate:**
- Field: `block_reentry_after_loss: bool = True` on `WarriorMonitorSettings`
- Default `True` (opt-out, since this is a safety gate)
- Persistent via the same JSON file at `data/warrior_monitor_settings.json`

---

### Q5: Exit Callback Extension — Best Approach

**Problem:** `_on_profit_exit` only fires for `PROFIT_TARGET` exits. The quality gate needs P&L info after ANY exit.

**Recommended approach: Store `last_exit_pnl` on `WatchedCandidate` from the handle_exit path.**

Two injection points are needed:

**Injection A — Profit exits (existing callback):**
Extend `_handle_profit_exit` at [warrior_engine.py:206-254](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_engine.py#L206-L254) to accept and store `exit_pnl`:
```python
def _handle_profit_exit(self, symbol, exit_price, exit_time, exit_pnl=None):
    ...
    if exit_pnl is not None:
        watched.last_exit_pnl = Decimal(str(exit_pnl))
```

**Injection B — Loss exits (PMH path reset):**
At [warrior_engine_entry.py:548-550](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py#L548-L550), we lack P&L data. But all exits log to `_recently_exited`, so we can look up the last trade's P&L from DB:
```python
# Before resetting entry_triggered, check last trade P&L
from nexus2.db.warrior_db import get_last_trade_pnl
last_pnl = get_last_trade_pnl(symbol)
if last_pnl is not None:
    watched.last_exit_pnl = Decimal(str(last_pnl))
```

**Alternative (simpler, fewer moving parts):**
Since the gate check happens in `check_entry_guards` AFTER `entry_triggered` is reset, skip storing on `WatchedCandidate` entirely and query the DB directly in the guard:
```python
# In check_entry_guards:
if engine.monitor.settings.block_reentry_after_loss:
    from nexus2.db.warrior_db import get_last_trade_pnl
    last_pnl = get_last_trade_pnl(symbol)
    if last_pnl is not None and last_pnl < 0:
        return False, f"Re-entry BLOCKED - last exit was a loss (${last_pnl:.2f})"
```

> [!IMPORTANT]
> **Recommended: DB-query approach in the guard.** This is the lowest blast-radius option — no changes to the exit callback signature, no changes to `WatchedCandidate`, no changes to `_handle_profit_exit`. Just one new guard clause + one new DB function.

---

## 3. Change Surface

### Component 1: Data Layer

#### [NEW] DB function — `get_last_trade_pnl`

**File:** [warrior_db.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/db/warrior_db.py)

Add a function to retrieve the P&L of the most recent CLOSED trade for a symbol:
```python
def get_last_trade_pnl(symbol: str) -> Optional[float]:
    """Get P&L of the last closed trade for this symbol (today's session)."""
    # Query warrior_trades WHERE symbol=? AND status='CLOSED'
    # ORDER BY exit_time DESC LIMIT 1
    # Return realized_pnl
```

> [!NOTE]
> Need to verify the exact column names in `warrior_trades` table before implementing. The implementer should `SELECT * FROM warrior_trades LIMIT 1` to confirm schema.

---

### Component 2: Guard Logic

#### [MODIFY] [warrior_entry_guards.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py)

**Function:** `check_entry_guards` (L35-149)

**Insertion point:** After the re-entry cooldown checks (around L120-130), before spread filter.

```python
# RE-ENTRY QUALITY GATE: Block re-entry after loss (Ross: no revenge trading)
if engine.monitor.settings.block_reentry_after_loss:
    from nexus2.db.warrior_db import get_last_trade_pnl
    last_pnl = get_last_trade_pnl(symbol)
    if last_pnl is not None and last_pnl < 0:
        return False, f"Re-entry BLOCKED after loss (P&L=${last_pnl:.2f}) - no revenge trading"
```

---

### Component 3: Settings & Toggle

#### [MODIFY] [warrior_types.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_types.py)

**Class:** `WarriorMonitorSettings` (L58-168)

**Add after L115 (Re-Entry section):**
```python
block_reentry_after_loss: bool = True  # Fix 6: Block re-entry if last exit was a loss
```

#### [MODIFY] [warrior_monitor_settings.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/db/warrior_monitor_settings.py)

**Function:** `apply_monitor_settings` (L64-122) — add:
```python
if "block_reentry_after_loss" in settings:
    monitor_settings_obj.block_reentry_after_loss = settings["block_reentry_after_loss"]
```

**Function:** `get_monitor_settings_dict` (L125-160) — add:
```python
"block_reentry_after_loss": monitor_settings_obj.block_reentry_after_loss,
```

---

## 4. Files Modified Summary

| File | Change | Lines |
|------|--------|-------|
| `warrior_types.py` | Add `block_reentry_after_loss` field | ~L116 |
| `warrior_entry_guards.py` | Add P&L guard clause | ~L120-130 |
| `warrior_db.py` | Add `get_last_trade_pnl()` function | New function |
| `warrior_monitor_settings.py` | Add serialization + deserialization | L122, L160 |

**Total blast radius: 4 files, ~15 lines of new code.**

---

## 5. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| DB query per entry check adds latency | Low | SQLite local query, <1ms. Same pattern as `_is_pending_exit` |
| Gate blocks legitimate re-entries (profit → loss → block) | Medium | This is **intentional behavior**. Ross: "if you lose on it, move on" |
| Scale-adds accidentally blocked | None | Scale path is completely separate (verified Q3) |
| `get_last_trade_pnl` returns stale data from prior day | Low | Filter by today's date in the query |
| Toggle default `True` changes behavior for existing users | Low | This is a safety gate, safe default. Users can opt out |

---

## 6. Expected Impact

Based on [findings_winner_to_loser.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/reports/2026-02-16/findings_winner_to_loser.md):

| Symbol | Entry 1 P&L | Entry 2 P&L | Entry 3+ P&L | Gate saves |
|--------|-------------|-------------|--------------|------------|
| MNTS | -$460 | -$220 | — | +$220 |
| MLEC | -$240 | -$100 | — | +$100 |
| FLYE | +$180 | -$350 | — | +$350 |

**Conservative estimate:** +$500-700 improvement from blocking losing re-entries.

> [!CAUTION]
> Some profitable re-entries (like ROLR) could also be blocked if a prior Entry 1 was a scratch loss. The A/B toggle lets us measure both sides. Start with `True` (gate ON) and compare via batch simulation.

---

## 7. Verification Plan

### Automated Tests

**Unit test for the new guard clause:**
```powershell
cd "c:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus"
python -m pytest nexus2/tests/unit/automation/test_warrior_monitor.py -v -k "reentry" 2>&1 | Select-Object -First 30
```

The implementer should add tests to the existing test file:
1. **Test: re-entry blocked after loss** — Mock `get_last_trade_pnl` to return `-100.0`, verify `check_entry_guards` returns `(False, "...BLOCKED...")`
2. **Test: re-entry allowed after profit** — Mock to return `+50.0`, verify `(True, ...)`
3. **Test: re-entry allowed when no prior trade** — Mock to return `None`, verify `(True, ...)`
4. **Test: gate disabled** — Set `block_reentry_after_loss=False`, verify entry proceeds regardless of P&L
5. **Test: scale-add unaffected** — Verify `check_scale_opportunity` does NOT query `get_last_trade_pnl`

**Settings persistence test:**
```powershell
python -c "from nexus2.db.warrior_monitor_settings import get_monitor_settings_dict; from nexus2.domain.automation.warrior_types import WarriorMonitorSettings; d = get_monitor_settings_dict(WarriorMonitorSettings()); print('block_reentry_after_loss' in str(d))"
```
Expected: `True`

### Batch Simulation (A/B)

```powershell
# Baseline (gate OFF):
python nexus2/scripts/run_batch.py --override "block_reentry_after_loss=false"

# Treatment (gate ON):
python nexus2/scripts/run_batch.py --override "block_reentry_after_loss=true"
```

Compare per-case P&L. MNTS, MLEC, FLYE should show improvement. ROLR should be monitored for regression.

---

## 8. Implementer Wiring Checklist

- [ ] Add `get_last_trade_pnl(symbol)` to `warrior_db.py`
- [ ] Verify `warrior_trades` table schema (column names for P&L, symbol, status, date)
- [ ] Add `block_reentry_after_loss: bool = True` to `WarriorMonitorSettings`
- [ ] Add guard clause to `check_entry_guards` after cooldown checks
- [ ] Add field to `apply_monitor_settings` deserialization
- [ ] Add field to `get_monitor_settings_dict` serialization
- [ ] Add 5 unit tests (block/allow/none/disabled/scale-safe)
- [ ] Run settings persistence verification command
- [ ] Run batch simulation A/B comparison
