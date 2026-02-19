# Backend Status: ETB Default + Caching Fix

**Date:** 2026-02-19
**File:** `nexus2/domain/scanner/warrior_scanner_service.py`
**Status:** ✅ Complete — all verification checks pass

## Problem

When a symbol fails an early pillar check (Float/RVOL/Price/Gap), the borrow check never runs, so `easy_to_borrow` stayed at its default `True`. This wrote misleading ETB data to telemetry.db — VPS data showed 251/261 MLEC rows with `etb=True` (default) vs only 10 with the real value `etb=False`.

## Changes Made

### Change 1 — Default to `None`
- **L274** (`WarriorCandidate`): `easy_to_borrow: bool = True` → `easy_to_borrow: Optional[bool] = None`
- **L468** (`EvaluationContext`): `easy_to_borrow: bool = True` → `easy_to_borrow: Optional[bool] = None`

### Change 2 — Cache ETB after Alpaca lookup (~L1700)
After the `get_asset_info()` call, the result is cached with a 24-hour TTL:
```python
self._cache[f"etb:{ctx.symbol}"] = (ctx.easy_to_borrow, now_et())
```

### Change 3 — `_resolve_etb()` helper method (L524–L537)
New method resolves ETB for DB writes: checks `ctx.easy_to_borrow` first, falls back to the 24-hour cache, returns `None` if neither is available. Used at DB write time instead of raw `str(ctx.easy_to_borrow)`.

### Change 4 — None guard on downstream boolean check (L1727)
```diff
-if ctx.easy_to_borrow and ctx.float_shares and ctx.float_shares > s.etb_high_float_threshold:
+if ctx.easy_to_borrow is True and ctx.float_shares and ctx.float_shares > s.etb_high_float_threshold:
```

## Verification Results

| Check | Command | Result |
|-------|---------|--------|
| Import | `python -c "from nexus2.domain.scanner.warrior_scanner_service import WarriorScannerService; print('OK')"` | ✅ OK |
| Default | `python -c "from nexus2.domain.scanner.warrior_scanner_service import EvaluationContext; c = EvaluationContext(symbol='X', name='', price=0, change_percent=0, verbose=False); print(f'etb={c.easy_to_borrow}')"` | ✅ `etb=None` |
| Tests | `python -m pytest nexus2/tests/ -x -q --timeout=30` | ✅ 758 passed, 4 skipped, 0 failures |

## Testable Claims (for Testing Specialist)

| # | Claim | File:Line | Grep Pattern |
|---|-------|-----------|-------------|
| 1 | `WarriorCandidate.easy_to_borrow` defaults to `None` | `warrior_scanner_service.py:274` | `easy_to_borrow: Optional[bool] = None` |
| 2 | `EvaluationContext.easy_to_borrow` defaults to `None` | `warrior_scanner_service.py:468` | `easy_to_borrow: Optional[bool] = None` |
| 3 | `_resolve_etb()` method exists | `warrior_scanner_service.py:524` | `def _resolve_etb` |
| 4 | DB write uses `_resolve_etb()` | `warrior_scanner_service.py:575` | `is_etb=self._resolve_etb(ctx)` |
| 5 | ETB cached after Alpaca lookup | `warrior_scanner_service.py:1700` | `self._cache[f"etb:{ctx.symbol}"]` |
| 6 | Downstream check uses `is True` | `warrior_scanner_service.py:1727` | `ctx.easy_to_borrow is True` |
