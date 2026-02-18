# Handoff: Testing Specialist — Pre-Existing Test Failures

@agent-testing-specialist.md

## Context

The Audit Validator found 62 pre-existing test failures across the test suite. None are caused by recent exit fill changes. Your job is to fix the infrastructure failures and diagnose (NOT fix) the strategy-sensitive ones.

**Validation report:** `nexus2/reports/2026-02-18/validation_exit_fill_fixes.md`

---

## Tier 1: FIX — Async Event Loop Failures (55 tests)

These are all `RuntimeError: no current event loop` — a test infrastructure issue, not a code bug.

**Affected files:**
- `test_ma_check.py` (15 failures)
- `test_position_monitor.py` (10 failures)
- `test_warrior_engine.py` (14 failures)
- `test_warrior_monitor.py` (8 failures)
- `test_monitor_partials.py` (8 failures)

**Likely root cause:** Missing `pytest-asyncio` configuration. Check:
1. Is `pytest-asyncio` installed? `pip list | Select-String "asyncio"`
2. Is `asyncio_mode = "auto"` in `pyproject.toml` or `pytest.ini`?
3. Do test functions need `@pytest.mark.asyncio` decorators?
4. Are there missing event loop fixtures?

**Action:** Fix the infrastructure so async tests run. Do NOT change any test assertions or trading logic.

---

## Tier 2: DIAGNOSE ONLY — Strategy-Sensitive Failures (3 tests)

> [!CAUTION]
> **DO NOT change assertions for these tests.** They may be catching real bugs in scanner logic. Write a diagnosis report only.

### Scanner Validation (2 failures)
- `test_scanner_validation.py` — BNRG and VHUB rejected by scanner

**Diagnose:**
- What scanner criteria did BNRG/VHUB fail?
- Is the scanner correct to reject them, or is the scanner missing them?
- What was the expected vs actual behavior?

### Timezone Compliance (1 failure)
- `test_timezone_compliance.py` — Direct `datetime` usage violation

**Diagnose:**
- Which file/function has the violation?
- What should it use instead (`now_et()`)?
- Is fixing this safe or could it change trading behavior?

---

## Output

**For Tier 1:** Implement fixes. Run full test suite to confirm.

**For Tier 2:** Write diagnosis to: `nexus2/reports/2026-02-18/diagnosis_strategy_sensitive_failures.md`

Use this format:
```markdown
## Diagnosis: Strategy-Sensitive Test Failures

### BNRG Scanner Rejection
- **Test file:** [path:line]
- **What failed:** [assertion]
- **Scanner criteria failed:** [which check]
- **Is scanner correct?** [YES/NO/UNCLEAR]
- **Proposed fix:** [describe but do NOT implement]

### VHUB Scanner Rejection
[same format]

### Timezone Compliance
- **File with violation:** [path:line]
- **Current code:** [snippet]
- **Proposed fix:** [snippet]
- **Trading impact:** [YES/NO + explanation]
```

## Verification

After Tier 1 fixes:
```powershell
cd nexus2; python -m pytest tests/ -v --no-header --tb=short 2>&1 | Select-String "FAILED"
```

Expected: Failures drop from 62 to ~7 or fewer (only Tier 2 + any others discovered).
