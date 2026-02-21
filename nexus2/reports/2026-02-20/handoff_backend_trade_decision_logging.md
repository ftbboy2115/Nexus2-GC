# Handoff: Backend Specialist — Trade Decision Logging (Option A)

> **Task**: Promote `log_warrior_guard_block` from TML-file-only to DB persistence
> **Plan**: `nexus2/reports/2026-02-20/plan_trade_decision_logging.md`
> **Rules**: `@agent-backend-specialist.md`

---

## Context

Guard block rejections (when the bot chooses NOT to enter a trade) are currently logged to a flat TML file only — not to the database. This means we cannot query "why trades were NOT taken." The `log_warrior_guard_block()` method at `trade_event_service.py:976` already exists and is called by 10 of 12 guard categories, but it only writes to the TML file (no `_log_event()` call).

**Goal**: Add DB persistence to guard blocks so they appear in the Trade Events table (queryable via Data Explorer).

---

## Changes Required

### File 1: `nexus2/domain/automation/trade_event_service.py`

#### Change 1A: Add event type constant
- **Location**: Look for the block of `WARRIOR_*` event type constants (search for `WARRIOR_GUARD_BLOCK` — it may already exist as a string reference but not as a class constant)
- **Action**: Add `WARRIOR_GUARD_BLOCK = "WARRIOR_GUARD_BLOCK"` to the event type constants if not already present

#### Change 1B: Add DB write to `log_warrior_guard_block()` (line 976-998)
- **Location**: `log_warrior_guard_block()` method, line 976
- **Current behavior**: Only calls `self._log_to_file()`
- **New behavior**: Also call `self._log_event()` after the `_log_to_file()` call
- **Implementation**:
```python
# After the existing _log_to_file call, add:
self._log_event(
    strategy="WARRIOR",
    position_id="GUARD_BLOCK",
    symbol=symbol,
    event_type=self.WARRIOR_GUARD_BLOCK,
    new_value=guard_name,
    reason=reason,
    metadata={
        "guard_name": guard_name,
        "trigger_type": trigger_type,
        "price": price,
    },
)
```
- **Update the docstring** to reflect it now writes to DB + TML file

---

### File 2: `nexus2/domain/automation/warrior_entry_guards.py`

#### Change 2A: Add missing guard block logging for live cooldown (line 120-125)
- **Location**: `check_entry_guards()`, the `RE-ENTRY COOLDOWN (LIVE mode)` block at line 120-125
- **Current behavior**: Returns `False` with reason but does NOT call `tml.log_warrior_guard_block()`
- **New behavior**: Add `tml.log_warrior_guard_block(symbol, "live_cooldown", reason, _trigger, _price)` before the return
- **Implementation**:
```python
# Line 120-125 currently:
if not engine.monitor.sim_mode and symbol in engine.monitor._recently_exited:
    exit_time = engine.monitor._recently_exited[symbol]
    seconds_ago = (now_utc() - exit_time).total_seconds()
    cooldown = engine.monitor._recovery_cooldown_seconds
    if seconds_ago < cooldown:
        return False, f"Re-entry cooldown - exited {seconds_ago:.0f}s ago (waiting {cooldown}s)"

# Change to:
if not engine.monitor.sim_mode and symbol in engine.monitor._recently_exited:
    exit_time = engine.monitor._recently_exited[symbol]
    seconds_ago = (now_utc() - exit_time).total_seconds()
    cooldown = engine.monitor._recovery_cooldown_seconds
    if seconds_ago < cooldown:
        reason = f"Re-entry cooldown - exited {seconds_ago:.0f}s ago (waiting {cooldown}s)"
        tml.log_warrior_guard_block(symbol, "live_cooldown", reason, _trigger, _price)
        return False, reason
```

---

### File 3: `nexus2/adapters/simulation/sim_context.py`

#### Change 3A: Add guard block count to batch results (in `_run_single_case_async`, ~line 660-718)
- **Location**: Inside `_run_single_case_async()`, after the trade extraction block (after line 695), before the return dict
- **Action**: Query the in-memory DB for `WARRIOR_GUARD_BLOCK` events and add count + details to the result
- **Implementation**:
```python
# After the trades extraction block, before the return dict:
guard_blocks = []
try:
    from nexus2.db.trade_event_db import get_session
    from nexus2.db.trade_event_db import TradeEventModel
    with get_session() as db:
        blocks = db.query(TradeEventModel).filter(
            TradeEventModel.event_type == "WARRIOR_GUARD_BLOCK"
        ).all()
        for b in blocks:
            guard_blocks.append({
                "guard": b.new_value,
                "reason": b.reason,
                "symbol": b.symbol,
            })
except Exception as e:
    log.warning(f"[{case_id}] Failed to extract guard blocks: {e}")
```

- **Add to result dict**: Add `"guard_blocks": guard_blocks` and `"guard_block_count": len(guard_blocks)` to the return dict at line 697-708

> [!IMPORTANT]
> Verify the correct import path for `get_session` and `TradeEventModel`. Search for `TradeEventModel` in the codebase to find the right module.

---

## Verification Checklist

- [ ] `WARRIOR_GUARD_BLOCK` constant exists in `trade_event_service.py`
- [ ] `log_warrior_guard_block()` calls both `_log_to_file()` AND `_log_event()`
- [ ] Live cooldown path (line 120-125 of `warrior_entry_guards.py`) calls `tml.log_warrior_guard_block()`
- [ ] `_run_single_case_async` result dict includes `guard_blocks` and `guard_block_count`
- [ ] No import errors: `python -c "from nexus2.domain.automation.trade_event_service import TradeEventService; print('OK')"`
- [ ] No import errors: `python -c "from nexus2.domain.automation.warrior_entry_guards import check_entry_guards; print('OK')"`
- [ ] Full test suite: `python -m pytest nexus2/tests/ -x -q`

## Write Status Report

Write your status report to: `nexus2/reports/2026-02-20/backend_status_trade_decision_logging.md`
