# Backend Status: AI Negative Catalyst Tiebreaker + Regex Fixes

**Date:** 2026-03-03  
**Agent:** Backend Specialist  
**Handoff:** `handoff_backend_negative_ai_tiebreaker.md`

---

## Summary

Implemented 3-party AI tiebreaker for negative catalyst rejections and tightened two risky regex patterns.

---

## Changes Made

### 1. `ai_catalyst_validator.py`

| Change | Details |
|--------|---------|
| `NEGATIVE_REVIEW_PROMPT` | Specialized prompt for reviewing negative catalyst false positives |
| `validate_negative_sync()` | 3-party method: Regex (Party 1) → Flash-Lite reviews (Party 2) → Pro breaks tie if disagree (Party 3) |

**Flow:**
- Regex says negative → Flash-Lite reviews
- If Flash **agrees** → `consensus_negative` → reject (Pro NOT called, ~300ms)
- If Flash **disagrees** → Pro tiebreaker called
  - Pro agrees with regex → `pro_confirmed` → reject
  - Pro agrees with Flash → `tiebreaker_override` → allow through (~5-7s)
- **Fail-closed at every level:** rate limited, empty response, error → defaults to regex rejection

**Fix applied during testing:** Pro model (`gemini-2.5-pro`) is a thinking model; `max_output_tokens: 60` caused empty responses. Increased to `1024` and added `response.candidates` fallback parsing.

### 2. `warrior_scanner_service.py`

| Change | Location |
|--------|----------|
| `enable_ai_negative_review: bool = True` | `WarriorScanSettings` (kill switch) |
| `ai_negative_override: bool = False` | `EvaluationContext` field |
| AI review wired into `_evaluate_catalyst_pillar()` | Before final rejection, after existing bypasses (RS, momentum) |

When AI overrides regex: `should_bypass = True`, size reduced to 75%.

### 3. `catalyst_classifier.py`

| Pattern | Before | After |
|---------|--------|-------|
| `guidance_cut` | `warns?` (bare) | `warns?\s+(of\s+)?(weak\|lower\|decline\|loss\|risk\|slowdown\|shortfall)` |
| `sec_or_legal` | `settlement`, `investigation` (bare) | `legal\s+settlement`, `regulatory\s+investigation`; added `sec\s+inquiry` |
| `offering` | *(unchanged)* | Kept broad intentionally — AI tiebreaker handles IPO vs secondary distinction |

---

## Verification

### Regex Fixes (9/9 pass)
```
Company warns of strong demand ahead of Q4              | PASS         | no_match     | OK
Company warns of weak demand                            | NEGATIVE     | guidance_cut | OK
Settlement of acquisition completed                     | PASS         | acquisition  | OK
Legal settlement reached in fraud case                  | NEGATIVE     | sec_or_legal | OK
FDA investigation shows promising results               | PASS         | no_match     | OK
Regulatory investigation launched by SEC                | NEGATIVE     | sec_or_legal | OK
Company receives subpoena                               | NEGATIVE     | sec_or_legal | OK
Class action lawsuit filed                              | NEGATIVE     | sec_or_legal | OK
Lowers guidance for Q4                                  | NEGATIVE     | guidance_cut | OK
```

### 3-Party AI Tiebreaker (6/6 pass, real Gemini API calls)
```
Case 1: "Initial Public Offering priced at $10"
  Regex: offering → Flash: FALSE_POSITIVE:IPO → Pro: FALSE_POSITIVE:IPO → ✅ Override (5.3s)

Case 2: "Settlement of $2B acquisition completed"
  Regex: sec_or_legal → Flash: FALSE_POSITIVE → Pro: FALSE_POSITIVE:m_and_a → ✅ Override (7.3s)

Case 3: "FDA investigation shows promising results"
  Regex: sec_or_legal → Flash: FALSE_POSITIVE → Pro: FALSE_POSITIVE:Scientific/FDA → ✅ Override (6.4s)

Case 4: "$50M registered direct offering"
  Regex: offering → Flash: NEGATIVE:direct offering → CONSENSUS → ✅ Blocked (0.4s)

Case 5: "SEC investigation accounting fraud"
  Regex: sec_or_legal → Flash: NEGATIVE:SEC → CONSENSUS → ✅ Blocked (0.5s)

Case 6: "Lowers guidance, warns of weak Q4"
  Regex: guidance_cut → Flash: NEGATIVE:guidance cut → CONSENSUS → ✅ Blocked (0.3s)
```

### Batch Test (no regression)
```
Improved:  1/40 (NPT — new test case, not caused by this change)
Regressed: 0/40
```

> **Note:** Batch tests bypass the scanner entirely (`sim_context.py` constructs `WarriorCandidate` from YAML). These changes affect the **live scanner only**.

---

## Kill Switch

Set `enable_ai_negative_review = False` in scanner settings to disable. No code changes needed.

---

## Test Script

`scripts/test_neg_tiebreaker.py` — runs 6 live API test cases. Can be used for future regression testing.

---

## Testable Claims for Validator

| # | Claim | How to Verify |
|---|-------|---------------|
| 1 | Consensus path (regex + Flash agree) does NOT call Pro | Run test case 4-6, check logs — no Pro HTTP call |
| 2 | Tiebreaker path (regex vs Flash disagree) calls Pro | Run test case 1-3, check logs — Pro HTTP call appears |
| 3 | `guidance_cut` no longer matches bare `warns` | `classifier.classify("Company warns")` → no negative match |
| 4 | `sec_or_legal` no longer matches bare `settlement` | `classifier.classify("settlement completed")` → no negative match |
| 5 | `offering` regex still catches secondary/direct offerings | `classifier.classify("direct offering")` → negative match |
| 6 | Fail-closed when Flash rate limited | Mock `_can_call_model` → False, verify returns `(True, ...)` |
| 7 | Fail-closed when Pro errors | Mock Pro to raise Exception, verify returns `(True, ...)` |
