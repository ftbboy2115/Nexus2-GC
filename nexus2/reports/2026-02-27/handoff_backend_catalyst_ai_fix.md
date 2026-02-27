# Handoff: Backend Specialist — Catalyst AI Fix (Phase 1 + Phase 3)

> **Date:** 2026-02-27
> **Assigned to:** Backend Specialist
> **Priority:** High — ship today
> **Approved plan:** `nexus2/reports/2026-02-27/plan_catalyst_ai_fix.md`

---

## Task Summary

Implement Phase 1 (strategy-specific AI prompts) and Phase 3 (3 regex additions) from the approved catalyst AI fix plan. Phase 2 (AI revocation) is **deferred** — do NOT implement it.

---

## Verified Facts

All verified via grep/view on 2026-02-27:

| Fact | File | Line | Verified |
|------|------|------|----------|
| `SYSTEM_PROMPT` constant (KK-biased) | `ai_catalyst_validator.py` | L316-349 | ✅ `grep_search` |
| `_validate_with_model()` uses `SYSTEM_PROMPT` | `ai_catalyst_validator.py` | L682 | ✅ `view_file` |
| `validate_sync()` signature (no strategy param) | `ai_catalyst_validator.py` | L848-855 | ✅ `view_file` |
| Stale docstring "Trading decisions still use regex only" | `ai_catalyst_validator.py` | L575-576 | ✅ `view_file` |
| `validate_sync` called from scanner | `warrior_scanner_service.py` | L1497 | ✅ `grep_search` |
| User prompt says "Qullamaggie EP catalyst" | `ai_catalyst_validator.py` | L676 | ✅ `view_file` |

---

## Changes Required

### File 1: `nexus2/domain/automation/ai_catalyst_validator.py`

#### Change 1a: Replace `SYSTEM_PROMPT` with two strategy-specific prompts (L316-349)

Replace the single `SYSTEM_PROMPT` constant with two new constants:

**`WARRIOR_SYSTEM_PROMPT`** — Ross Cameron methodology:
- Broader catalyst definition: "Is this headline a valid catalyst for a momentum day trade?"
- ALL earnings are VALID (beat, miss, or neutral) — the gap itself is the catalyst
- Few-shot headline format examples:
  - `"[Company] Q4 2025 Earnings Call Transcript"` → VALID: earnings
  - `"[Company]: Q4 Earnings Snapshot"` → VALID: earnings
  - `"[Company] Reports Q4 Results"` → VALID: earnings
  - `"[Company] Reports Strong Revenue Growth"` → VALID: earnings
- Entity matching rule: "Only validate if headline is ABOUT the queried symbol"
  - Example: `"Nasdaq Gains 1%; TJX Posts Earnings"` for symbol XWEL → INVALID (about TJX)
- Reject: `"Earnings Scheduled For [date]"` — future event, not results
- Include Ross-specific catalysts: crypto treasury, clinical study data, partnerships, FDA, contract wins

**`KK_SYSTEM_PROMPT`** — Keep existing Qullamaggie content (copy current `SYSTEM_PROMPT` text):
- Stricter: requires "earnings beat with strong reaction"
- Keep existing valid/invalid lists

**Also keep `SYSTEM_PROMPT = WARRIOR_SYSTEM_PROMPT`** as alias for backward compatibility with `AICatalystValidator` class (L352-471) which still references it.

#### Change 1b: Add `strategy` parameter to `_validate_with_model()` (L639-728)

Current signature at L639:
```python
def _validate_with_model(self, model_name: str, headline: str, symbol: str) -> ModelResult:
```

New signature:
```python
def _validate_with_model(self, model_name: str, headline: str, symbol: str, strategy: str = "warrior") -> ModelResult:
```

Inside the function:
- At L682, replace `"system_instruction": SYSTEM_PROMPT` with:
  ```python
  "system_instruction": WARRIOR_SYSTEM_PROMPT if strategy == "warrior" else KK_SYSTEM_PROMPT,
  ```
- At L673-676, update the user_prompt to be strategy-aware:
  - For warrior: `"Is this a valid catalyst for a momentum day trade?"`
  - For KK: `"Is this a valid Qullamaggie EP catalyst?"`

#### Change 1c: Add `strategy` parameter to `validate_sync()` (L848-855)

Current signature at L848:
```python
def validate_sync(self, headline, symbol, regex_passed, regex_type=None, article_url=None):
```

New signature:
```python
def validate_sync(self, headline, symbol, regex_passed, regex_type=None, article_url=None, strategy="warrior"):
```

Pass `strategy` through to all internal `_validate_with_model()` calls within `validate_sync()`.

#### Change 1d: Fix stale docstring (L575-576)

Replace:
```python
    Used to train regex patterns by comparing regex vs AI results.
    Trading decisions still use regex only.
```

With:
```python
    Multi-model catalyst validation with tiebreaker system.
    Used for parallel assessment. AI can add catalysts regex missed
    (see warrior_scanner_service.py L1517).
```

#### Change 1e: Update internal callers

Search `_validate_with_model` within the same file — it's called from:
- `process_queue()` at ~L763, L774 — pass `strategy` (default "warrior" is fine for now)
- `validate_sync()` body — pass the `strategy` parameter through

### File 2: `nexus2/domain/scanner/warrior_scanner_service.py`

#### Change 2: Pass `strategy="warrior"` explicitly at L1497

Current call:
```python
final_valid, final_type, _, flash_passed, method = multi_validator.validate_sync(
```

Add `strategy="warrior"` as a kwarg to make it explicit.

### File 3: `nexus2/domain/automation/catalyst_classifier.py`

#### Change 3a: Add `exceeds expectations` to earnings pattern

In `CatalystClassifier.__init__()`, find the `earnings` regex pattern and add `exceeds\s+expectations` to the alternation.

#### Change 3b: Add `asset sale / divestiture` to acquisition pattern

Add `asset\s+sale|divestiture` to the `acquisition` regex pattern alternation.

#### Change 3c: Add `rebrands` as new corporate_action category

Add a new `corporate_action` pattern:
```python
"corporate_action": re.compile(
    r"\b(rebrands?|rebrand(s|ed|ing)?)\b",
    re.IGNORECASE,
),
```

Add `"corporate_action"` to the `positive_types` set (or wherever positive catalyst types are defined).

#### Change 3d: Add `earnings scheduled for` exclusion

Add an exclusion pattern so that `"earnings scheduled for"` does NOT trigger `earnings` regex (it's a future event, not actual results). This should be checked BEFORE the earnings pattern match.

---

## Open Questions (Investigate Before Implementing)

1. **Where are internal `_validate_with_model()` calls?** I confirmed L763 and L774 in `process_queue()` and calls within `validate_sync()`. Grep the file to find ALL call sites and pass `strategy` through each one.
2. **What are the `positive_types` for `catalyst_classifier.py`?** The plan says add `corporate_action` — verify how positive types are defined in `__init__()` and the `classify()` method to ensure it's handled as positive.
3. **Existing regex patterns:** Before adding, grep for `exceeds` and `divestiture` and `rebrand` to confirm they don't already exist.

---

## Testable Claims

After implementation, the following should be verifiable:

| # | Claim | How to Verify |
|---|-------|---------------|
| 1 | `WARRIOR_SYSTEM_PROMPT` exists with "momentum day trade" language | `Select-String "WARRIOR_SYSTEM_PROMPT" ai_catalyst_validator.py` |
| 2 | `KK_SYSTEM_PROMPT` exists with "Qullamaggie" language | `Select-String "KK_SYSTEM_PROMPT" ai_catalyst_validator.py` |
| 3 | `validate_sync()` has `strategy` parameter | `Select-String "def validate_sync" ai_catalyst_validator.py` |
| 4 | `_validate_with_model()` has `strategy` parameter | `Select-String "def _validate_with_model" ai_catalyst_validator.py` |
| 5 | Warrior scanner passes `strategy="warrior"` | `Select-String "strategy=" warrior_scanner_service.py` |
| 6 | Stale docstring is fixed | `Select-String "Trading decisions still use regex only" ai_catalyst_validator.py` should return 0 results |
| 7 | `exceeds expectations` in earnings regex | `Select-String "exceeds" catalyst_classifier.py` |
| 8 | `divestiture` in acquisition regex | `Select-String "divestiture" catalyst_classifier.py` |
| 9 | `rebrand` pattern exists | `Select-String "rebrand" catalyst_classifier.py` |
| 10 | `earnings scheduled` exclusion exists | `Select-String "earnings.scheduled" catalyst_classifier.py` |
| 11 | All existing catalyst tests pass | `pytest nexus2/tests/unit/automation/test_catalyst_classifier.py -v` |

---

## Do NOT

- ❌ Implement Phase 2 (AI revocation) — deferred
- ❌ Modify `warrior_types.py` — that's Phase 2
- ❌ Change any test files — Testing Specialist handles that
- ❌ Add new dependencies
