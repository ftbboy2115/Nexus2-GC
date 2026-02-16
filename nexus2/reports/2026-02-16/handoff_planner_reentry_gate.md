# Backend Planner Handoff: Re-entry Quality Gate Spec

@agent-backend-planner.md

## Task

Research and write a technical specification for a **Re-entry Quality Gate** that blocks re-entries on symbols where the prior trade was a loss.

---

## Design Decisions (Approved by Coordinator)

### Gate Strictness: Block after ANY single loss

Block re-entry if `last_exit_pnl < 0` (any single losing exit on that symbol blocks re-entry). No cumulative P&L tracking needed.

**Rationale**: Ross doesn't revenge trade. If a trade stops out, the setup failed — re-entering is chasing a dead setup. Keeping it simple (single loss = blocked) avoids complexity and matches Ross methodology.

### Gate Scope: Central `check_entry_guards` (universal)

The quality gate must live in `check_entry_guards` ([warrior_entry_guards.py:119](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py#L119)) — this catches ALL entry paths uniformly (PMH, HOD_BREAK, DIP_FOR_LEVEL, MICRO_PULLBACK, etc.).

The existing DIP_FOR_LEVEL-specific re-entry guards (warrior_entry_patterns.py:423-457) can remain as defense-in-depth but the quality gate is centralized.

---

## Verified Facts

### 1. Re-entry callback only fires on PROFIT_TARGET exits

**File:** [warrior_monitor_exit.py:1432-1444](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py#L1432-L1444)

```python
profit_reasons = {
    WarriorExitReason.PROFIT_TARGET,
}
if signal.reason in profit_reasons and monitor._on_profit_exit:
    monitor._on_profit_exit(
        symbol=signal.symbol,
        exit_price=float(actual_exit_price),
        exit_time=now_utc(),
    )
```

### 2. Engine re-entry handler resets `entry_triggered`

**File:** [warrior_engine.py:206-254](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_engine.py#L206-L254)

```python
def _handle_profit_exit(self, symbol: str, exit_price: float, exit_time: datetime):
    watched = self._watchlist.get(symbol)
    # ... max re-entry check ...
    watched.entry_triggered = False
    watched.position_opened = False
    watched.last_exit_time = exit_time
    watched.last_exit_price = Decimal(str(exit_price))
    watched.entry_attempt_count += 1
```

### 3. WatchedCandidate re-entry fields exist but lack P&L tracking

**File:** [warrior_engine_types.py:167-173](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_engine_types.py#L167-L173)

```python
entry_attempt_count: int = 0
last_exit_time: Optional[datetime] = None
last_exit_price: Optional[Decimal] = None
entry_volume_ratio: float = 0.0
```

**Missing:** `last_exit_pnl` — no field tracks whether prior exit was profit or loss.

### 4. Entry guards have re-entry cooldown but no P&L check

**File:** [warrior_entry_guards.py:119-137](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py#L119-L137)

```python
# RE-ENTRY COOLDOWN (LIVE mode)
if not engine.monitor.sim_mode and symbol in engine.monitor._recently_exited:
    # ... time-based cooldown only ...

# SIM MODE COOLDOWN
if engine.monitor.sim_mode and symbol in engine.monitor._recently_exited_sim_time:
    # ... sim-time-based cooldown only ...
```

### 5. DIP_FOR_LEVEL has additional re-entry guards

**File:** [warrior_entry_patterns.py:423-457](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py#L423-L457)

Guards: cooldown, max attempts (2), price above last exit. **But:** these only apply to DIP_FOR_LEVEL, not other patterns (HOD_BREAK, MICRO_PULLBACK, etc.).

---

## Open Questions (Investigate These From Scratch)

### Q1: How are MNTS and MLEC re-entering after a loss?

MNTS data shows:
- Entry 1 at 08:40, $7.67 (dip_for_level)
- Entry 3 at 13:08, $6.90 (hod_break) — price is 10% BELOW first entry

Since `_on_profit_exit` only fires on `PROFIT_TARGET` exits, how is entry 3 triggered?
- Is entry 1 exiting via `PROFIT_TARGET` (meaning re-entry callback IS firing)?
- Or is entry 3 triggered through a different path that doesn't use `_handle_profit_exit`?

**Starting points:** 
- Run `ross_mnts_20260209` sim case and trace exit reasons
- Check `warrior_engine_entry.py` for any other paths that reset `entry_triggered`
- Check `check_entry_triggers` function flow

### Q2: What is the exact re-entry flow end-to-end?

Trace the complete sequence for a symbol that gets re-entered:
1. How does the exit propagate (monitor → engine)?
2. What resets `entry_triggered` and `position_opened`?
3. How does the next `check_entry_triggers` cycle pick up the symbol again?
4. Are there any hidden paths besides `_handle_profit_exit`?

### Q3: Will the gate accidentally block scale adds?

**Starting points:**
- `_check_position_guards` (warrior_entry_guards.py:210)
- `check_scale_opportunity` (warrior_monitor_scale.py)
- How does the code distinguish scale adds from true re-entries?
- Scale adds flow through `check_scale_opportunity` (triggered from monitor tick), NOT through `check_entry_guards`. Verify this assumption.

### Q4: A/B Toggle Wiring Pattern

Check how existing toggles are implemented for the wiring template:
- `enable_improved_scaling` → find in `warrior_monitor_settings.py`
- `enable_partial_then_ride` → find in `warrior_monitor_settings.py`
- How are they persisted (`get_monitor_settings_dict`, `apply_monitor_settings`)?
- Where are they read in guard logic?

### Q5: Exit callback signature — does it need extending?

Current callback: `_on_profit_exit(symbol, exit_price, exit_time)`

The quality gate needs `exit_pnl` (or `entry_price` to calculate it). Options:
- Extend `_on_profit_exit` with a `pnl` parameter (also extend to fire on ALL exits, not just profit)
- Create a separate `_on_any_exit` callback
- Calculate P&L from `watched.last_exit_price` vs the entry price already stored on the position

Which approach has the least blast radius?

---

## Deliverable

Write a technical specification to: `nexus2/reports/2026-02-16/spec_reentry_quality_gate.md`

The spec MUST include:
1. **Answers to Q1-Q5** with code evidence (file:line, pasted snippets, PowerShell verification commands + output)
2. **Exact change surface** (every file, function, and approximate line)
3. **Wiring checklist** (field add → populate → check → toggle → persist)
4. **Risk analysis** (what could go wrong, what could be accidentally blocked)
5. **Test scenarios** (MNTS blocked, ROLR not blocked, scale adds not affected)

> [!CAUTION]
> **Do NOT guess.** If you cannot verify a claim with actual code, say "UNVERIFIED" and explain what you couldn't confirm. Every finding must have file:line evidence.
