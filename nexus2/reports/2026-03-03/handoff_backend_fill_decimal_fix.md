# Backend Specialist Handoff: Fix actual_fill_decimal Bug

**Date:** 2026-03-03 16:53 ET  
**From:** Coordinator  
**To:** Backend Specialist  
**Output:** `nexus2/reports/2026-03-03/backend_status_fill_decimal_fix.md`

---

## Task

Fix the `actual_fill_decimal` unbound variable bug in the fill update path.

## Problem

Batch test logs show this error on multiple symbols (LCFY, PAVM, BATL, BNKK):
```
[Warrior Entry] LCFY: DB fill update failed: cannot access local variable 'actual_fill_decimal' where it is not associated with a value
```

The variable `actual_fill_decimal` is referenced but never defined in at least one code path.

## Find the Bug

```powershell
Select-String -Path "C:\Dev\Nexus\nexus2\domain\automation\warrior_entry_execution.py" -Pattern "actual_fill_decimal" -Context 3,3
```

If not found there, search more broadly:
```powershell
Select-String -Path "C:\Dev\Nexus\nexus2\domain\automation\" -Pattern "actual_fill_decimal" -Include "*.py" -Recurse -Context 3,3
```

## Fix

Ensure `actual_fill_decimal` is defined before use in all code paths (likely a missing initialization or an early-return before assignment).

## Verification

```powershell
python scripts/gc_quick_test.py --all --diff
```

Expected: $0 regression, error messages no longer appear in batch logs.
