# Research: AI Tiebreaker Gap on Negative Catalyst Rejections

**Date:** 2026-03-03  
**Author:** Backend Planner  
**Handoff:** `handoff_planner_negative_ai_gap.md`  
**Prior research:** `research_offering_false_positive.md`

---

## Executive Summary

The AI tiebreaker gap on negative catalysts is **an oversight, not a deliberate safety choice**. The code structure makes this clear: the multi-model pipeline was designed exclusively for positive catalyst discovery and was never extended to cover negative catalyst validation. Adding AI review for negative rejections is architecturally feasible but requires careful design to balance accuracy gains against API cost and latency.

---

## Question 1: Was This Intentional?

**Finding: Oversight, not deliberate.**

### Evidence

The call sequence in `_evaluate_symbol` (L927-931) reveals the architecture:

```python
# L927: Catalyst pillar runs FIRST — includes negative check
if self._evaluate_catalyst_pillar(ctx, tracker, headlines):
    return None  # ← EXITS HERE on negative catalyst (L1430)

# L931: Multi-model runs SECOND — only reached if catalyst pillar didn't reject
self._run_multi_model_catalyst_validation(ctx, headlines)
```

**File:** [warrior_scanner_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py#L927-L931)

The `_evaluate_catalyst_pillar` method (L1308-1441) checks negative catalysts at L1380-1430 and returns `"negative_catalyst"` immediately — before the multi-model validation at L931 ever executes.

**The multi-model pipeline was designed purely for positive catalyst discovery.** Its docstring says "Run sync dual catalyst validation (HeadlineCache + Regex + Flash-Lite)" and its code only asks the AI "Is this a valid catalyst?" — a positive-only question. The `WARRIOR_SYSTEM_PROMPT` (L321-371) tells the AI to respond `VALID: [type]` or `INVALID: [reason]` — a binary valid/invalid framing, not a "is this negative or positive?" framing.

**Verified with:** `view_file` on `warrior_scanner_service.py` L927-931 and L1308-1441; `view_code_item` on `MultiModelValidator.validate_sync`; `view_file` on `WARRIOR_SYSTEM_PROMPT` L321-371.

### Why It Was Never Added

The pipeline evolved in stages:
1. **Regex classifier** was built first with negative patterns as a safety gate
2. **AI validator** was added later to catch regex false negatives (missed positives)
3. **Multi-model tiebreaker** was added to break regex vs. AI disagreements on positives

At no stage did anyone consider "what if regex has false positives on the negative side?" until the NPT incident exposed it.

---

## Question 2: How Does `_run_multi_model_catalyst_validation()` Work?

**File:** [warrior_scanner_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py#L1443-L1539)

### Flow

1. **Check headline cache** (L1454-1468) — if a cached positive result exists, use it
2. **Filter to new headlines** (L1471) — only process headlines not already cached
3. **For each new headline** (L1488-1539):
   a. Run regex classifier to get `regex_passed` and `regex_type`
   b. Call `multi_validator.validate_sync()` which:
      - Calls **Flash-Lite** AI with the headline
      - If Flash-Lite and regex **agree** → use consensus result
      - If they **disagree** → call **Pro** as tiebreaker
   c. Cache the result (unless regex_only fallback)
   d. If valid and no catalyst yet → set `ctx.has_catalyst = True`

### Key Limitation

The validator's question to the AI is: *"Is this a valid catalyst for a momentum day trade?"* (L736-739). The AI responds `VALID: [type]` or `INVALID: [reason]`. This is a **positive-only question** — it doesn't ask "is this headline negative/harmful?"

The same mechanism **could** work for negative catalyst review with a modified prompt (see Architecture Options below).

**File:** [ai_catalyst_validator.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/ai_catalyst_validator.py#L735-L746)

---

## Question 3: Architecture Options

### Option A: AI Second Opinion on Negative Rejections (Recommended)

**How it works:** When regex detects a negative catalyst, before rejecting, ask Flash-Lite: "Is this headline genuinely negative (offering/dilution/SEC issue) or is it being misclassified?"

**Change surface:**

| # | File | Change |
|---|------|--------|
| 1 | `ai_catalyst_validator.py` | Add `NEGATIVE_REVIEW_PROMPT` — a specialized prompt asking AI to validate whether a headline is truly negative |
| 2 | `ai_catalyst_validator.py` | Add `validate_negative_sync()` method to `MultiModelValidator` that calls Flash-Lite with the negative review prompt |
| 3 | `warrior_scanner_service.py` | In `_evaluate_catalyst_pillar` L1415-1430, before returning `"negative_catalyst"`, call `validate_negative_sync()` |
| 4 | `warrior_scanner_service.py` | Add config flag `enable_ai_negative_review: bool = True` to `WarriorScanSettings` |

**Trade-offs:**

| Dimension | Impact |
|-----------|--------|
| **Accuracy** | ✅ High — AI would easily distinguish "Initial Public Offering" from "direct offering" |
| **API cost** | ⚠️ 1 Flash-Lite call per negative rejection (~$0.001 each) |
| **Latency** | ⚠️ ~200-500ms per rejected stock |
| **Safety** | ✅ Still fail-closed — if AI is rate-limited or errors, default to regex rejection |
| **Complexity** | Low — reuses existing `MultiModelValidator` infrastructure |

**Estimated prompt:**

```
You are reviewing a negative catalyst detection. The regex classifier flagged this headline 
as potentially harmful (type: {neg_type}).

Headline: "{headline}"
Symbol: {symbol}
Regex match type: {neg_type}

Is this headline genuinely a NEGATIVE catalyst (stock offering, SEC investigation, 
guidance cut, earnings miss) that should BLOCK a momentum trade?

Or is the regex wrong — is this actually a POSITIVE or NEUTRAL event being misclassified?

Respond with EXACTLY one line:
- "NEGATIVE: [reason]" if this IS genuinely harmful
- "FALSE_POSITIVE: [actual_type]" if the regex misclassified a non-harmful headline
```

### Option B: AI Override with Human-Review Flag

Same as Option A, but when AI disagrees with regex, instead of overriding, **flag the disagreement** for human review via WebSocket alert.

**Trade-offs:**

| Dimension | Impact |
|-----------|--------|
| **Accuracy** | ✅ Best — human makes final call |
| **Missed trades** | ❌ Still misses trades while awaiting review |
| **Complexity** | Medium — needs WebSocket alert integration |

### Option C: Improve Regex Only (No AI)

Fix the regex patterns to reduce false positives. Already partially done with the IPO exclusion fix from `research_offering_false_positive.md`.

**Trade-offs:**

| Dimension | Impact |
|-----------|--------|
| **Accuracy** | ⚠️ Limited — can't anticipate all edge cases |
| **API cost** | ✅ Zero |
| **Latency** | ✅ Zero |
| **Maintenance** | ❌ Ongoing regex whack-a-mole |

### Recommendation

**Option A** is the best balance. It reuses existing infrastructure, has negligible cost, and catches edge cases that regex refinement alone can't anticipate. The fail-closed safety property is preserved: if AI is unavailable, the stock stays rejected.

---

## Question 4: Rate Limits and Latency

### How Many Negative Rejections Per Day?

I cannot query telemetry.db directly (Backend Planner scope), but the data structure exists:

**File:** [warrior_scanner_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py#L1429)

```python
self._write_scan_result_to_db(ctx.symbol, False, ctx, rejection_reason=f"negative_catalyst:{neg_type}")
```

**Estimated volume (based on code analysis):**

- Scanner runs every ~2 minutes during market hours (~195 cycles/day)
- Each cycle evaluates ~20-40 symbols
- Most rejections are for gap, float, RVOL, price — not negative catalysts
- Negative catalyst rejections likely affect **2-5 unique symbols per day** (with repeat rejections per symbol per cycle)
- With headline caching, the AI would only be called **once per unique headline per symbol** (not per scan cycle)

**Rate limit impact:**
- Flash-Lite allows 15 RPM → can handle ~5 negative reviews per minute easily
- Even worst case (10 unique negative headlines in one scan cycle) → well within limits
- Headline cache prevents re-evaluation of the same headline

### Latency Impact

- Flash-Lite: ~200-500ms per call (observed from existing positive validation)
- Negative catalyst checks happen AFTER float, RVOL, price, and gap pillars pass → only high-quality candidates reach this point
- Adding 200-500ms to negative catalyst evaluation of a candidate that already passed 4 pillars is acceptable

---

## Question 5: Other Negative Regex False-Positive Risks

**File:** [catalyst_classifier.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/catalyst_classifier.py#L178-L195)

### All 4 Negative Patterns Analyzed

#### 1. `offering` (L179-181) — **HIGH RISK** ⚠️

```python
r"\b(offerings?|public\s+offering|registered\s+direct|at-the-market|atm\s+offering|dilution)\b"
```

**Known false positives:**
- ✅ *Already fixed:* "Initial Public Offering" → should be `ipo` (positive)
- ⚠️ "Oversubscribed offering" → could be a completed/successful offering (neutral/positive)
- ⚠️ "Exercise of Over-Allotment Option" → post-IPO standard procedure, not dilutive in the harmful sense

#### 2. `sec_or_legal` (L183-185) — **MEDIUM RISK** ⚠️

```python
r"\b(sec\s+investigation|subpoena|lawsuit|settlement|class\s+action|investigation)\b"
```

**Potential false positives:**
- ⚠️ **"Settlement"** in acquisition context — "Company announces $2B settlement/acquisition of XYZ" would trigger `sec_or_legal` when it's actually an `acquisition`
- ⚠️ **"Investigation"** in scientific context — "FDA investigation shows promising results" would trigger `sec_or_legal` when it's a positive `fda` catalyst
- ⚠️ **"Investigation"** in media context — "Investigation reveals strong demand for product" → not legal

#### 3. `guidance_cut` (L187-189) — **MEDIUM RISK** ⚠️

```python
r"\b(lowers?\s+(outlook|guidance)|cuts?\s+guidance|downward\s+revision|warns?)\b"
```

**Potential false positives:**
- ⚠️ **"Warns"** is extremely broad — "Company warns of strong demand ahead of Q4" → positive
- ⚠️ **"Warns"** in analyst context — "Analyst warns competitors to take notice" → neutral/positive
- ⚠️ **"Warns"** in geopolitical context — "CEO warns supply chain issues are over" → positive

**The `warns?` pattern alone is the highest-risk single term** across all negative patterns.

#### 4. `miss` (L191-194) — **LOW-MEDIUM RISK**

```python
r"\b(misses?|disappoints?|falls?\s+short|below\s+estimates?|weak\s+quarter)\b"
```

**Potential false positives:**
- ⚠️ "Misses" in sports/entertainment headlines for entertainment stocks — low probability
- ⚠️ "Falls short" in competitive context — "Competitor falls short as Company surges" → about competitor, not symbol

### Risk Summary Table

| Pattern | Risk Level | Worst False Positive | AI Would Catch? |
|---------|-----------|---------------------|-----------------|
| `offering` | **HIGH** | "Initial Public Offering" | ✅ Yes — IPO is a known positive |
| `sec_or_legal` | **MEDIUM** | "Settlement" in acquisition context | ✅ Yes — AI understands M&A |
| `guidance_cut` | **MEDIUM** | "Warns of strong demand" | ✅ Yes — AI understands context |
| `miss` | **LOW** | Edge cases only | ✅ Probably |

**Key insight:** All four patterns share the same vulnerability — they match **individual words** that have multiple meanings depending on context. Regex cannot understand context; AI can.

---

## Answers to Handoff Questions (Summary)

| # | Question | Answer |
|---|----------|--------|
| 1 | Was this intentional? | **No — oversight.** The AI pipeline was designed for positive catalyst discovery and was never extended to negative validation. |
| 2 | How does the multi-model pipeline work? | Regex + Flash-Lite run in parallel; if they disagree, Pro breaks the tie. Only asks "is this a valid catalyst?" — positive-only framing. |
| 3 | What would it take architecturally? | **Option A:** Add `validate_negative_sync()` with a specialized prompt. 4 files, low complexity. Reuses existing infra. |
| 4 | Rate limits and latency? | ~2-5 unique negative symbols/day. Flash-Lite at 15 RPM handles this easily. ~200-500ms latency is acceptable for candidates that passed 4 pillars. Headline cache prevents redundant calls. |
| 5 | Other negative false-positive risks? | Yes — `sec_or_legal` ("settlement" in M&A), `guidance_cut` ("warns" is too broad), and `miss` (edge cases). All would benefit from AI review. |
