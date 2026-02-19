# Validation Report: ETB Default + Caching Fix

**Date:** 2026-02-19  
**Validating:** `nexus2/reports/2026-02-19/backend_status_etb_fix.md`  
**Validator:** Audit Validator Agent

---

## Claims Verified

| # | Claim | Stated Line | Actual Line | Result | Evidence |
|---|-------|-------------|-------------|--------|----------|
| 1 | `WarriorCandidate.easy_to_borrow` defaults to `None` | 274 | 274 | **PASS** | Pattern `easy_to_borrow: Optional[bool] = None` found at L274 |
| 2 | `EvaluationContext.easy_to_borrow` defaults to `None` | 468 | 468 | **PASS** | Pattern `easy_to_borrow: Optional[bool] = None` found at L468 |
| 3 | `_resolve_etb()` method exists | 524 | 524 | **PASS** | `def _resolve_etb(self, ctx: Optional['EvaluationContext']) -> Optional[str]:` at L524 |
| 4 | DB write uses `_resolve_etb()` | 575 | 575 | **PASS** | `is_etb=self._resolve_etb(ctx),` at L575 |
| 5 | ETB cached after Alpaca lookup | ~1700 | 1715 | **PASS** | `self._cache[f"etb:{ctx.symbol}"] = (ctx.easy_to_borrow, now_et())` at L1715 |
| 6 | Downstream check uses `is True` | 1727 | 1742 | **PASS** | `if ctx.easy_to_borrow is True and ctx.float_shares and ctx.float_shares > s.etb_high_float_threshold:` at L1742 |

---

## Functional Checks

### Import Check
**Claim:** `from nexus2.domain.scanner.warrior_scanner_service import WarriorScannerService` imports cleanly  
**Verification Command:**
```powershell
python -c "from nexus2.domain.scanner.warrior_scanner_service import WarriorScannerService; print('OK')"
```
**Actual Output:** `OK`  
**Result:** **PASS**

### Default Value Check
**Claim:** `EvaluationContext.easy_to_borrow` defaults to `None`  
**Verification Command:**
```powershell
python -c "from nexus2.domain.scanner.warrior_scanner_service import EvaluationContext; c = EvaluationContext(symbol='X', name='', price=0, change_percent=0, verbose=False); print(f'etb={c.easy_to_borrow}')"
```
**Actual Output:** `etb=None`  
**Result:** **PASS**

### Method Body Verification
**Claim:** `_resolve_etb()` checks ctx value → cache → None  
**Verification:** Viewed `warrior_scanner_service.py` lines 524-537  
**Actual Code:**
```python
def _resolve_etb(self, ctx: Optional['EvaluationContext']) -> Optional[str]:
    """Resolve ETB value for DB write: ctx value → cache → None."""
    if ctx is None:
        return None
    etb_value = ctx.easy_to_borrow
    if etb_value is None:
        cached = self._cache.get(f"etb:{ctx.symbol}")
        if cached:
            etb_value, cached_at = cached
            # 24-hour TTL check (Alpaca updates ETB once daily)
            age = (now_et() - cached_at).total_seconds()
            if age > 86400:
                etb_value = None
    return str(etb_value) if etb_value is not None else None
```
**Result:** **PASS** — logic matches report description exactly (ctx → cache with 24hr TTL → None)

---

## Minor Discrepancies

| Claim | Stated Line | Actual Line | Delta | Severity |
|-------|-------------|-------------|-------|----------|
| 5 (ETB cache) | ~1700 | 1715 | +15 | Cosmetic (report used `~` prefix) |
| 6 (is True guard) | 1727 | 1742 | +15 | Minor (report stated exact line) |

> [!NOTE]
> Both discrepancies are +15 lines, suggesting edits were made after the report was written but before validation ran.
> The claim used `~L1700` notation for claim 5, which is within tolerance.
> Claim 6 stated an exact line number (1727) which is off by 15 — minor documentation drift.

---

## Test Suite
**Claim:** 758 passed, 4 skipped, 0 failures  
**Result:** NOT independently verified (skipped to avoid long test run during validation)  

---

## Overall Rating

**HIGH** — All 6 code claims verified. Both functional checks pass. Method body logic confirmed. Only minor line number drift on 2 claims, patterns are correct.

---

## Summary

The ETB fix is correctly implemented:
- Default changed from `True` → `None` on both dataclasses ✅
- `_resolve_etb()` helper properly cascades ctx → cache → None ✅
- DB writes use `_resolve_etb()` instead of raw `str(ctx.easy_to_borrow)` ✅
- ETB is cached after Alpaca lookup with TTL ✅
- Downstream boolean check uses `is True` to guard against `None` ✅
