# Backend Status: Trade Decision Logging (Option A)

**Date**: 2026-02-20
**Task**: Promote `log_warrior_guard_block` from TML-file-only to DB persistence
**Handoff**: `nexus2/reports/2026-02-20/handoff_backend_trade_decision_logging.md`

---

## Changes Made

### File 1: `nexus2/domain/automation/trade_event_service.py`

#### Change 1A: `WARRIOR_GUARD_BLOCK` constant — **ALREADY EXISTED**
- **File**: `trade_event_service.py:78`
- **Code**: `WARRIOR_GUARD_BLOCK = "GUARD_BLOCK"`
- No change needed.

#### Change 1B: Added `_log_event()` DB write to `log_warrior_guard_block()`
- **File**: `trade_event_service.py:976-1011`
- **What**: Added `self._log_event()` call after existing `self._log_to_file()` call
- **DB fields**:
  - `strategy="WARRIOR"`, `position_id="GUARD_BLOCK"`, `event_type="GUARD_BLOCK"`
  - `new_value=guard_name`, `reason=reason`
  - `metadata`: `{guard_name, trigger_type, price}`
- **Docstring**: Updated to reflect dual write (TML + DB)

### File 2: `nexus2/domain/automation/warrior_entry_guards.py`

#### Change 2A: Added guard block logging for live cooldown
- **File**: `warrior_entry_guards.py:119-127`
- **What**: The `RE-ENTRY COOLDOWN (LIVE mode)` block was the only guard (of 12) that did NOT call `tml.log_warrior_guard_block()`. Now it does, completing 12/12 coverage.
- **Guard name**: `"live_cooldown"`

### File 3: `nexus2/adapters/simulation/sim_context.py`

#### Change 3A: Added guard block count to batch results
- **File**: `sim_context.py:697-713`
- **What**: After trade extraction, queries `trade_events` DB for `WARRIOR_GUARD_BLOCK` events filtered by symbol. Adds `guard_blocks` list and `guard_block_count` to result dict.
- **Import path**: Uses `nexus2.db.database.get_session` + `nexus2.db.models.TradeEventModel` (verified — NOT `trade_event_db` as handoff suggested)

---

## Verification

| Check | Result |
|-------|--------|
| `WARRIOR_GUARD_BLOCK` constant exists (line 78) | ✅ Pre-existing |
| `log_warrior_guard_block()` calls `_log_to_file()` AND `_log_event()` | ✅ |
| Live cooldown path calls `tml.log_warrior_guard_block()` | ✅ |
| `_run_single_case_async` result includes `guard_blocks` + `guard_block_count` | ✅ |
| Import: `from nexus2.domain.automation.trade_event_service import TradeEventService` | ✅ OK |
| Import: `from nexus2.domain.automation.warrior_entry_guards import check_entry_guards` | ✅ OK |
| Test suite: `python -m pytest nexus2/tests/ -x -q` | ✅ 184 passed, 1 failed (pre-existing HIND RVOL boundary), 3 skipped |

---

## Testable Claims for Validator

1. **Claim**: `trade_event_service.py:78` contains `WARRIOR_GUARD_BLOCK = "GUARD_BLOCK"`
   - **Verify**: `Select-String -Path "nexus2\domain\automation\trade_event_service.py" -Pattern "WARRIOR_GUARD_BLOCK"`

2. **Claim**: `log_warrior_guard_block()` calls `self._log_event()` with `event_type=self.WARRIOR_GUARD_BLOCK`
   - **Verify**: `Select-String -Path "nexus2\domain\automation\trade_event_service.py" -Pattern "_log_event" -Context 0,5` (should show the call within `log_warrior_guard_block`)

3. **Claim**: Live cooldown at line ~119-127 of `warrior_entry_guards.py` calls `tml.log_warrior_guard_block(symbol, "live_cooldown", ...)`
   - **Verify**: `Select-String -Path "nexus2\domain\automation\warrior_entry_guards.py" -Pattern "live_cooldown"`

4. **Claim**: `sim_context.py` result dict includes `guard_blocks` and `guard_block_count`
   - **Verify**: `Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "guard_block"`

5. **Claim**: The pre-existing test failure (`ross_hind_20260127`) is unrelated to these changes
   - **Verify**: The failure is `RVOL: 2.0x < 2.0x` in scanner validation — no relation to trade event service or guard blocks
