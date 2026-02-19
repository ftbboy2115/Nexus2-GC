# Backend Status: Trade Events Data Quality Fixes

**Date:** 2026-02-19  
**Agent:** Backend Specialist  
**Status:** ✅ COMPLETE

## Changes Made

### Task 1: Fix shares extraction in `data_routes.py` (L830)
- **Before:** Only checked `meta.get("shares")`
- **After:** `meta.get("shares") or meta.get("shares_added") or meta.get("shares_sold") or ""`
- Covers SCALE_IN (`shares_added`), PARTIAL_EXIT (`shares_sold`), and standard (`shares`)

### Task 2: Decimal rounding in `data_routes.py` (after L830)
- Added loop over `new_value`/`old_value` fields: `f"{float(val):.2f}"`
- Wrapped in try/except for non-numeric values (e.g., reason strings)

### Task 3: Enrich `log_warrior_breakeven` in `trade_event_service.py` (L729)
- Added optional `shares: int = None` and `old_stop: Decimal = None` params
- Builds metadata dict with `shares`, `old_stop`, `new_stop`
- Passes `metadata=metadata if metadata else None` to `_log_event`

### Task 4: Updated all 5 call sites in `warrior_monitor_exit.py`
- L853, L865, L1000, L1012, L1151 — all now pass `shares=position.shares, old_stop=position.current_stop`

### Task 5: Add `shares` to `log_warrior_exit` in `trade_event_service.py` (L830)
- Added optional `shares: int = None` parameter
- Conditionally adds `metadata["shares"] = shares` when provided

## Verification

| Check | Result |
|-------|--------|
| `from nexus2.domain.automation.trade_event_service import trade_event_service` | ✅ OK |
| `from nexus2.domain.automation.warrior_monitor_exit import evaluate_position` | ✅ OK |
| `pytest nexus2/tests/ -x -q --timeout=30` | ✅ 758 passed, 4 skipped, 0 failures |

## Testable Claims

| # | Claim | Grep Pattern | File:Line |
|---|-------|-------------|-----------|
| 1 | Shares extraction checks 3 keys | `shares_added.*shares_sold` | `data_routes.py:830` |
| 2 | Decimal rounding applied | `f"{float(val):.2f}"` | `data_routes.py:837` |
| 3 | Breakeven has shares param | `shares: int = None` | `trade_event_service.py:735` |
| 4 | Breakeven has old_stop param | `old_stop: Decimal = None` | `trade_event_service.py:736` |
| 5 | Breakeven passes metadata | `metadata=metadata if metadata` | `trade_event_service.py:761` |
| 6 | Exit has shares param | `shares: int = None` | `trade_event_service.py:837` |
| 7 | Exit includes shares in metadata | `metadata["shares"] = shares` | `trade_event_service.py:859` |
| 8 | Call site 1 passes shares+old_stop | `shares=position.shares` | `warrior_monitor_exit.py:857` |
| 9 | Call site 5 passes shares+old_stop | `shares=position.shares` | `warrior_monitor_exit.py:1157` |
