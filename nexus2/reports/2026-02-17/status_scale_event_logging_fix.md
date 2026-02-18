# Status: Scale Event Logging Fix

**Date:** 2026-02-17
**Agent:** Backend Specialist
**Handoff:** `nexus2/reports/2026-02-17/handoff_backend_scale_event_logging.md`

---

## Result: ✅ COMPLETE

All 4 changes applied to `warrior_monitor_scale.py`. Unit tests: **180 passed, 0 failed**.

---

## Changes Made

### `nexus2/domain/automation/warrior_monitor_scale.py`

**Change 1+2: Weighted-average entry price + risk/target recalc** (after L283)
- Added `old_cost + new_cost / new_total_shares` calculation (matches `_consolidate_existing_position` pattern)
- Updates `position.entry_price`, `position.risk_per_share`, `position.profit_target`
- Handles `profit_target_cents` vs `profit_target_r` branching

**Change 3: Pass `new_avg_price` to `complete_scaling()`** (L286)
- Changed from `complete_scaling(position.position_id, new_total_shares)` to include `new_avg_price=float(new_avg_entry)`

**Change 4: Add SCALE_IN event logging** (after `complete_scaling()`)
- Added `trade_event_service.log_warrior_scale_in()` call with `position_id`, `symbol`, `add_price=price`, `shares_added=add_shares`

**Bonus: Updated trace log** (L315)
- Changed `"entry_price was ${old_entry:.2f} (may change via consolidate)"` → `"entry_price ${old_entry:.2f} → ${position.entry_price:.2f} (weighted avg)"`

### `nexus2/tests/unit/automation/test_warrior_engine.py` (pre-existing bug fix)

- Added `mock_monitor.settings.max_reentry_count = 3` to 3 test fixtures (`TestEntrySpreadFilter`, `TestEntryFilterPriority`, `TestSpreadCalculation`) that were failing with `TypeError: '>=' not supported between instances of 'int' and 'MagicMock'`

---

## Verification

| Check | Result |
|-------|--------|
| Unit tests (`pytest nexus2/tests/unit/automation/ -x -q`) | ✅ 180 passed |
| uvicorn reload | ✅ No import errors |
| Pattern match with `_consolidate_existing_position()` | ✅ Identical formula |

---

## Testable Claims

| # | Claim | Verification |
|---|-------|-------------|
| 1 | `log_warrior_scale_in()` called in `execute_scale_in()` | `Select-String -Path "nexus2\domain\automation\warrior_monitor_scale.py" -Pattern "log_warrior_scale_in"` → line exists |
| 2 | `new_avg_price` passed to `complete_scaling()` | `Select-String -Path "nexus2\domain\automation\warrior_monitor_scale.py" -Pattern "new_avg_price"` → line exists |
| 3 | Weighted avg formula present | `Select-String -Path "nexus2\domain\automation\warrior_monitor_scale.py" -Pattern "new_avg_entry"` → multiple lines |
| 4 | Trace log updated | `Select-String -Path "nexus2\domain\automation\warrior_monitor_scale.py" -Pattern "weighted avg"` → line exists |

---

## Remaining Verification (Handoff)

- **Sim test**: Run ATOM test case → query `/data/trade-events?symbol=ATOM&limit=30` → verify SCALE_IN events appear
- **Frontend check**: Trade Events tab should show ➕ icon for scale events
- **Share count check**: Query `/warrior/positions` during sim → verify `shares` and `entry_price` reflect post-scale state
