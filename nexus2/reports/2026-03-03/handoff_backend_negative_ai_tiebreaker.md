# Backend Specialist Handoff: AI Tiebreaker for Negative Catalysts + Risky Patterns

**Date:** 2026-03-03 16:53 ET  
**From:** Coordinator  
**To:** Backend Specialist  
**Research:** `nexus2/reports/2026-03-03/research_negative_catalyst_ai_gap.md`  
**Output:** `nexus2/reports/2026-03-03/backend_status_negative_ai_tiebreaker.md`

---

## Task

Two related improvements to the catalyst classification pipeline:

1. Add AI tiebreaker review for negative catalyst rejections
2. Fix risky negative regex patterns

---

## Part 1: AI Tiebreaker for Negative Catalysts (P0)

**Problem:** When the regex classifies a headline as negative (offering, sec_or_legal, etc.), the scanner returns immediately at `warrior_scanner_service.py:1430`. The multi-model AI pipeline never runs — it only validates positive catalysts. This caused the NPT false-positive (now fixed via regex, but the architectural gap remains).

**Recommended approach (from planner research):**

Add a `validate_negative_sync()` call before the final rejection. Reuse existing Flash-Lite infrastructure.

**Files to modify:**
- `nexus2/domain/automation/ai_catalyst_validator.py` — Add `validate_negative_sync()` method
- `nexus2/domain/scanner/warrior_scanner_service.py` — Call it before returning `"negative_catalyst"` at line ~1415

**Key design constraints:**
- **Fail-closed:** If AI is unavailable (rate limit, error), default to regex rejection (safe)
- **Use headline cache:** Check `get_headline_cache()` before making API calls
- **Low volume:** Only ~2-5 unique negative symbols per day, well within rate limits
- **Log disagreements:** When AI overrides regex, log clearly for observability

**Flow:**
```
Regex says negative → Check headline cache → If no cache hit, call Flash-Lite →
  AI agrees → reject (negative_catalyst)
  AI disagrees → log disagreement, allow through with size reduction (like momentum override)
  AI unavailable → reject (fail-closed, safe default)
```

---

## Part 2: Fix Risky Negative Regex Patterns (P1)

The planner identified these patterns as false-positive risks:

### `guidance_cut` pattern (highest risk)
```python
# Current (line ~187-189):
r"\b(lowers?\s+(outlook|guidance)|cuts?\s+guidance|downward\s+revision|warns?)\b"
```
**Problem:** `warns?` is too broad. "Warns of strong demand" would match. 

**Fix:** Tighten to require negative context:
```python
r"\b(lowers?\s+(outlook|guidance)|cuts?\s+guidance|downward\s+revision|warns?\s+(of\s+)?(weak|lower|decline|loss|risk))\b"
```

### `sec_or_legal` pattern (medium risk)
```python
# Current (line ~183-185):
r"\b(sec\s+investigation|subpoena|lawsuit|settlement|class\s+action|investigation)\b"
```
**Problem:** `settlement` matches in M&A context ("settlement of acquisition"). `investigation` is too broad.

**Fix:** Tighten:
```python
r"\b(sec\s+investigation|sec\s+inquiry|subpoena|lawsuit|class\s+action|legal\s+settlement|regulatory\s+investigation)\b"
```

---

## Verification

```powershell
# Run scanner tests
python -m pytest nexus2/tests/unit/scanners/ -v

# Run batch test
python scripts/gc_quick_test.py --all --diff
```

Expected: $0 regression (these changes affect scanner, not entry execution). NPT should still pass.

---

## CLI Reference (verified)
```
gc_quick_test.py [cases...] --all --diff --trades --save --list
scanner_pulse_check.py <symbol> <date>
```
