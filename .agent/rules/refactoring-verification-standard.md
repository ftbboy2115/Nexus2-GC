# Refactoring Verification Standard

> **Rule version:** 2026-02-19T07:01:00

This standard defines mandatory verification steps after any refactoring that involves extracting code to new modules and wiring it back.

## Background: The ABCD Wiring Incident (Feb 3, 2026)

A pattern extraction refactoring claimed 95% code reduction success, but:
- The extracted `detect_abcd_pattern()` function was **imported but never called**
- 55 lines of duplicate inline code remained
- Runtime error `name 'should_check_abcd' is not defined` occurred in production
- Root cause: Agent reported success without verifying each function was wired

## Mandatory Verification Steps

After ANY refactoring that involves extraction → wiring:

### 1. Grep Verification (Required)
For each extracted function, verify it is **actually called** (not just imported):

```powershell
# BAD: Only checks import exists
Select-String -Path "target_file.py" -Pattern "from.*module import func_name"

# GOOD: Checks function is CALLED (with opening paren)
Select-String -Path "target_file.py" -Pattern "await func_name\(|func_name\("
```

### 2. Import + Call Matrix (Required)
Document each extracted function with both import AND call locations:

| Function | Imported At | Called At | Status |
|----------|-------------|-----------|--------|
| `detect_abcd_pattern` | Line 41 | Line 830 | ✅ WIRED |
| `detect_pmh_break` | Line 44 | Line 627 | ✅ WIRED |

If "Called At" is empty → **NOT WIRED (BUG)**

### 3. Runtime Smoke Test (Required)
After wiring, run the actual code path:

```powershell
# Minimum: Import check
python -c "from module import function; print('Import OK')"

# Better: Call the function (mock dependencies if needed)
python -m pytest tests/unit/relevant_test.py -v
```

### 4. Inline Code Removal Check (Required)
Search for residual inline code that should have been removed:

```powershell
# Search for patterns that indicate un-removed inline code
Select-String -Path "target_file.py" -Pattern "pattern_svc.detect_abcd|EntryTriggerType.ABCD"
```

If matches exist AFTER wiring → duplicate code remains

### 5. Wiring Report Requirements
Every wiring report MUST include:

```markdown
## Verification Matrix

| Function | Imported | Called | Verified By |
|----------|----------|--------|-------------|
| func_a   | ✅ L42   | ✅ L523 | grep + test |
| func_b   | ✅ L43   | ✅ L529 | grep + test |

## Code Reduction
- Before: 2182 lines
- After: 2127 lines
- Removed: 55 lines of duplicate inline code

## Runtime Test
- Command: `python -m pytest tests/unit/automation/test_warrior_engine.py`
- Result: 24/24 passed
```

## Red Flags (Block Merge)

Do NOT approve refactoring PRs if:

1. **Import without call**: Function imported but grep shows no call site
2. **Inline code remains**: Original code not deleted after wiring
3. **No runtime test**: Only import check, no actual execution
4. **Metrics without verification**: Claims "95% reduction" without line-by-line proof

## Enforcement

- [ ] Add this check to PR review checklist
- [ ] Wiring agents must produce Verification Matrix
- [ ] Validator agents must spot-check 2+ functions from matrix

---

*Created after ABCD wiring incident. The 5-minute production error could have been prevented with 30 seconds of grep verification.*
