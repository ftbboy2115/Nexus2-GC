# Handoff: Testing Specialist — Validate Catalyst AI Fix

> **Date:** 2026-02-27
> **Assigned to:** Testing Specialist
> **Depends on:** Backend Specialist completing `handoff_backend_catalyst_ai_fix.md`
> **Reference:** `nexus2/reports/2026-02-27/handoff_backend_catalyst_ai_fix.md` (11 testable claims)

---

## Task Summary

Validate the Backend Specialist's implementation of Phase 1 (strategy-specific AI prompts) and Phase 3 (regex additions) for the catalyst AI fix. Verify all 11 testable claims, run existing test suites, and report results.

---

## Validation Steps

### Step 1: Verify 11 Testable Claims

Run each command below. Report PASS/FAIL with actual output.

```powershell
# Claim 1: WARRIOR_SYSTEM_PROMPT exists
Select-String "WARRIOR_SYSTEM_PROMPT" nexus2\domain\automation\ai_catalyst_validator.py

# Claim 2: KK_SYSTEM_PROMPT exists
Select-String "KK_SYSTEM_PROMPT" nexus2\domain\automation\ai_catalyst_validator.py

# Claim 3: validate_sync has strategy parameter
Select-String "def validate_sync" nexus2\domain\automation\ai_catalyst_validator.py

# Claim 4: _validate_with_model has strategy parameter
Select-String "def _validate_with_model" nexus2\domain\automation\ai_catalyst_validator.py

# Claim 5: Warrior scanner passes strategy="warrior"
Select-String "strategy=" nexus2\domain\scanner\warrior_scanner_service.py

# Claim 6: Stale docstring removed (expect 0 results = PASS)
Select-String "Trading decisions still use regex only" nexus2\domain\automation\ai_catalyst_validator.py

# Claim 7: exceeds expectations in earnings regex
Select-String "exceeds" nexus2\domain\automation\catalyst_classifier.py

# Claim 8: divestiture in acquisition regex
Select-String "divestiture" nexus2\domain\automation\catalyst_classifier.py

# Claim 9: rebrand pattern exists
Select-String "rebrand" nexus2\domain\automation\catalyst_classifier.py

# Claim 10: earnings scheduled exclusion exists
Select-String "earnings.scheduled" nexus2\domain\automation\catalyst_classifier.py

# Claim 11: All existing catalyst tests pass
pytest nexus2\tests\unit\automation\test_catalyst_classifier.py -v
```

### Step 2: Run Broader Catalyst Test Suite

```powershell
# Run ALL catalyst-related tests
pytest nexus2\tests\ -k "catalyst" -v
```

All pre-existing tests must still pass. Report any failures.

### Step 3: Verify Import Integrity

```powershell
# Verify ai_catalyst_validator.py imports without error
python -c "from nexus2.domain.automation.ai_catalyst_validator import MultiModelValidator, WARRIOR_SYSTEM_PROMPT, KK_SYSTEM_PROMPT; print('OK')"

# Verify catalyst_classifier.py imports without error
python -c "from nexus2.domain.automation.catalyst_classifier import CatalystClassifier; print('OK')"
```

### Step 4: Verify Prompt Content (Spot Check)

```powershell
# WARRIOR_SYSTEM_PROMPT should mention "momentum day trade" (not "Qullamaggie")
Select-String "momentum day trade" nexus2\domain\automation\ai_catalyst_validator.py

# KK_SYSTEM_PROMPT should mention "Qullamaggie" (not "momentum day trade")
Select-String "Qullamaggie" nexus2\domain\automation\ai_catalyst_validator.py
```

---

## Report Format

Save report to: `nexus2/reports/2026-02-27/validation_catalyst_ai_fix.md`

Use this format:

```markdown
## Validation Report: Catalyst AI Fix (Phase 1 + Phase 3)

### Claims Verified
| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | WARRIOR_SYSTEM_PROMPT exists | PASS/FAIL | [command + output] |
| ... | ... | ... | ... |

### Test Suite Results
- catalyst_classifier tests: X passed, Y failed
- broader catalyst tests: X passed, Y failed

### Import Integrity
- ai_catalyst_validator: OK/FAIL
- catalyst_classifier: OK/FAIL

### Overall Rating
- **HIGH**: All claims verified, all tests pass
- **MEDIUM**: Minor issues
- **LOW**: Major issues (requires rework)
```

---

## Do NOT

- ❌ Edit any production code — READ ONLY
- ❌ Skip any of the 11 claims
- ❌ Paraphrase command output — include EXACT output
