# Plan: Fix AI Catalyst Earnings Blind Spot + Enable Symmetric Pipeline

> **Date:** 2026-02-27  
> **Status:** Awaiting approval

---

## Problem

The AI catalyst validator (Flash-Lite + Pro) rejects ~85 valid earnings headlines because:

1. **Wrong methodology prompt:** The `SYSTEM_PROMPT` says "Qullamaggie EP catalyst" but the **Warrior (Ross Cameron) scanner** uses it. Ross and KK have different catalyst standards — Ross trades ANY earnings reaction; KK requires "earnings beat with strong reaction"
2. **No headline format examples:** The prompt says "Earnings beat" but doesn't show what real earnings headlines look like ("Q4 Earnings Call Transcript", "Reports Q4 Results")
3. **No entity matching guidance:** AI can't distinguish "TJX Posts Earnings" (about TJX) from a query about XWEL
4. **Single shared prompt:** Both Warrior and NAC scanners use the same KK-biased prompt — no strategy awareness

Current pipeline is also asymmetric: AI can add catalysts but cannot revoke regex false positives (~50 cases flow through unchecked).

---

## Proposed Changes

### Phase 1: Strategy-Specific AI Prompts (Priority 1)

#### [MODIFY] [ai_catalyst_validator.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/ai_catalyst_validator.py)

**Change 1a: Add strategy-specific prompt constants (replace single `SYSTEM_PROMPT` at L317-349)**

Create two prompts: `WARRIOR_SYSTEM_PROMPT` (Ross Cameron) and `KK_SYSTEM_PROMPT` (Qullamaggie).

**`WARRIOR_SYSTEM_PROMPT`** (new — Ross Cameron methodology):
- Broader catalyst definition: "Is this headline a valid catalyst for a momentum day trade?"
- Earnings are VALID regardless of beat/miss — the gap itself is the catalyst
- Explicit headline format examples (few-shot):
  - `"[Company] Q4 2025 Earnings Call Transcript"` → VALID: earnings
  - `"[Company]: Q4 Earnings Snapshot"` → VALID: earnings
  - `"[Company] Reports Q4 Results"` → VALID: earnings
  - `"[Company] Reports Strong Revenue Growth"` → VALID: earnings
- Entity matching: "Only validate if the headline is ABOUT the queried symbol"
  - `"Nasdaq Gains 1%; TJX Posts Earnings"` for symbol XWEL → INVALID: about TJX, not XWEL
- Reject: "Earnings Scheduled For [date]" — future event, not actual results
- Include Ross-specific catalysts: crypto treasury, clinical study data, partnerships, FDA

**`KK_SYSTEM_PROMPT`** (keep existing, refine later):
- Keep current Qullamaggie EP focus: "Earnings beat with strong reaction"
- Keep stricter standards — KK needs confirmed fundamental events
- Can be refined later when NAC bot is active again

**Change 1b: Add `strategy` parameter to `_validate_with_model()` and `validate_sync()`**

```python
def validate_sync(self, headline, symbol, regex_passed, regex_type=None, 
                  article_url=None, strategy="warrior"):
    ...

def _validate_with_model(self, model_name, headline, symbol, strategy="warrior"):
    prompt = WARRIOR_SYSTEM_PROMPT if strategy == "warrior" else KK_SYSTEM_PROMPT
    ...
    config={"system_instruction": prompt, ...}
```

Default to `"warrior"` since Warrior is the primary scanner. NAC scanner will pass `strategy="kk"`.

**Change 1c: Update caller in `warrior_scanner_service.py`**

Pass `strategy="warrior"` in the `validate_sync()` call at L1497 (explicit, for clarity).

**Change 1d: Fix stale docstring (L575-576)**

Replace "Trading decisions still use regex only" with accurate description:
"Used for parallel assessment. AI can add catalysts regex missed (L1517 in warrior_scanner_service.py)."

### Phase 2: Enable Symmetric Pipeline (Priority 2)

#### [MODIFY] [warrior_scanner_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py)

**Change 3: Add AI revocation capability (L1517 area)**

After Phase 1 is deployed and AI earnings accuracy is verified via monitoring, change the catalyst decision logic to:

```python
# Current (asymmetric):
if final_valid and not ctx.has_catalyst:
    ctx.has_catalyst = True
    ctx.catalyst_source = "ai"

# New (symmetric, behind settings flag):
if s.ai_can_revoke_regex and ctx.catalyst_source == "regex":
    if not final_valid and method in ("consensus", "tiebreaker"):
        ctx.has_catalyst = False
        ctx.catalyst_source = None
        logger.warning(f"[AI Revoke] {symbol}: AI revoked regex PASS (method={method})")
elif final_valid and not ctx.has_catalyst:
    ctx.has_catalyst = True
    ctx.catalyst_source = "ai"
```

> [!CAUTION]
> **Phase 2 should NOT be implemented until Phase 1 is deployed and we have verified the AI earnings blind spot is fixed.** At minimum 1 week of monitoring data showing AI correctly passes standard earnings headlines.

#### [MODIFY] [warrior_types.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_types.py)

**Change 4: Add `ai_can_revoke_regex` settings flag**

Add `ai_can_revoke_regex: bool = False` to WarriorSettings. Default OFF — only enabled after Phase 1 verification.

### Phase 3: Additional Regex Patterns (Priority 3, can be parallel)

#### [MODIFY] [catalyst_classifier.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/catalyst_classifier.py)

From the training analysis, 3 small patterns to add:
- `exceeds expectations` → earnings pattern
- `asset sale / divestiture` → acquisition pattern  
- `rebrands` → new `corporate_action` pattern

Also add an exclusion for `earnings scheduled for` to reduce regex false positives (~23 cases).

---

## User Review Required

> [!IMPORTANT]
> **Phase 2 (symmetric pipeline) is a significant architecture change.** It changes the catalyst decision logic from "regex-first, AI-additive" to "regex-and-AI-collaborative." This needs explicit approval.

Questions:
1. Should Phase 2 (AI revocation) be behind a settings flag (`ai_can_revoke_regex = False` by default)?
2. How long should we monitor Phase 1 before enabling Phase 2? (I suggest 1 week minimum)
3. Should we implement Phase 1 and Phase 3 together as a single deploy, or separate?

---

## Verification Plan

### Phase 1 Verification (AI Prompt Fix)

**Automated test:** Run the 85 known false-negative headlines through the updated AI validator and verify at least 80% now return VALID.

```powershell
# Test script that sends known earnings headlines through the AI validator
python -c "
from nexus2.domain.automation.ai_catalyst_validator import MultiModelValidator
v = MultiModelValidator(models=['flash_lite'])
headlines = [
    ('BWIN', 'Q4 2025 Earnings Call Transcript'),
    ('PRAA', 'PRA Group Reports Q4 and Full Year 2025 Results'),
    ('ACHC', 'Acadia Healthcare Q4 Earnings Call Highlights'),
    ('DNUT', 'Krispy Kreme Q4 Earnings Snapshot'),
    ('RXT', 'Rackspace Technology Q4 Results'),
]
for sym, h in headlines:
    r = v._validate_with_model('flash_lite', h, sym)
    print(f'{sym}: {\"PASS\" if r.is_valid else \"FAIL\"} | {r.reason}')
"
```

**Expected:** All 5 samples should return PASS/VALID with the updated prompt.

**Existing tests:** Run `pytest nexus2/tests/ -k "catalyst" -v` — 40 existing tests must still pass.

**Entity matching test:** Verify AI correctly rejects earnings about OTHER companies:
```powershell
# These should still FAIL — earnings are about TJX/Lowe's, not XWEL
python -c "
from nexus2.domain.automation.ai_catalyst_validator import MultiModelValidator
v = MultiModelValidator(models=['flash_lite'])
r = v._validate_with_model('flash_lite', 'Nasdaq Gains Over 1%; TJX Posts Upbeat Earnings', 'XWEL')
print(f'XWEL+TJX headline: {\"PASS\" if r.is_valid else \"FAIL\"} (expect FAIL)')
"
```

### Phase 2 Verification (deferred until Phase 1 monitoring complete)

Monitor `ai_comparisons` for 1 week after Phase 1 deploy. Check:
- Earnings PASS rate increases from ~47% to >90%
- Multi-company headlines still correctly rejected
- No increase in false positives

### Phase 3 Verification

Same pattern as the regex fixes earlier — run classifier against specific headlines, run `pytest -k catalyst`.

---

## Implementation Approach

| Phase | Agent | Scope | Timing |
|-------|-------|-------|--------|
| 1 | Backend Specialist | `ai_catalyst_validator.py` prompt + docstring | Now |
| 2 | Backend Specialist | `warrior_scanner_service.py` + `warrior_types.py` | After 1 week monitoring |
| 3 | Backend Specialist | `catalyst_classifier.py` small regex adds | Parallel with Phase 1 |
