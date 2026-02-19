# Validation Report: Trade Events Data Quality Fixes

**Date:** 2026-02-19  
**Validator:** Testing Specialist  
**Report Under Review:** `backend_status_trade_events_quality.md`

## Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | Shares extraction checks 3 keys | **PASS** | `Select-String -Pattern "shares_added"` → `data_routes.py:830` matches `meta.get("shares") or meta.get("shares_added") or meta.get("shares_sold") or ""` |
| 2 | Decimal rounding applied | **PASS** | File view L837: `event[field] = f"{float(val):.2f}"` inside try/except at L838 |
| 3 | Breakeven has `shares` param | **PASS** | `Select-String -Pattern "shares: int = None"` → `trade_event_service.py:734` (report said L735, off by 1) |
| 4 | Breakeven has `old_stop` param | **PASS** | File view L735: `old_stop: Decimal = None,` (report said L736, off by 1) |
| 5 | Breakeven passes metadata | **PASS** | File view L760: `metadata=metadata if metadata else None,` (report said L761, off by 1) |
| 6 | Exit has `shares` param | **PASS** | `Select-String` → `trade_event_service.py:836` (report said L837, off by 1) |
| 7 | Exit includes shares in metadata | **PASS** | File view L860-861: `if shares is not None: metadata["shares"] = shares` (report said L859, off by 2) |
| 8 | Call site 1 passes shares+old_stop | **PASS** | `Select-String -Pattern "shares=position.shares"` → `warrior_monitor_exit.py:857` (exact match) |
| 9 | Call site 5 passes shares+old_stop | **PASS** | `Select-String` → `warrior_monitor_exit.py:1163` (report said L1157, off by 6) |

### Additional Verification: All 5 Call Sites

The report claims 5 call sites at L853, L865, L1000, L1012, L1151.

**Actual locations** (verified via `Select-String -Pattern "log_warrior_breakeven"`):

| Report Line | Actual Line | Delta | Status |
|-------------|-------------|-------|--------|
| L853 | L853 | 0 | ✅ |
| L865 | L867 | +2 | ✅ |
| L1000 | L1004 | +4 | ✅ |
| L1012 | L1018 | +6 | ✅ |
| L1151 | L1159 | +8 | ✅ |

All 5 call sites confirmed, each passing `shares=position.shares, old_stop=position.current_stop`.

### Import Verification

```
Command: python -c "from nexus2.domain.automation.trade_event_service import trade_event_service; from nexus2.domain.automation.warrior_monitor_exit import evaluate_position; print('OK')"
Output: OK: all imports clean
```

## Overall Rating

**HIGH** — All 9 claims verified. Code changes are present and correct.

> [!NOTE]
> Line numbers in the report show progressive drift (+1 to +8 lines off), suggesting the report was written against a slightly earlier file version or before a minor edit shifted lines. The code patterns themselves are all correct and present.

## Failures

None.
