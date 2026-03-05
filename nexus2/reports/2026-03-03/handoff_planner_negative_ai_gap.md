# Backend Planner Handoff: AI Tiebreaker Gap on Negative Catalysts

**Date:** 2026-03-03 15:41 ET  
**From:** Coordinator  
**To:** Backend Planner  
**Previous research:** `nexus2/reports/2026-03-03/research_offering_false_positive.md`  
**Output:** `nexus2/reports/2026-03-03/research_negative_catalyst_ai_gap.md`

---

## Problem

The multi-model catalyst pipeline (regex + Flash-Lite AI + Pro tiebreaker) was designed to catch regex mistakes. But it only runs for positive catalyst validation. When a negative catalyst is detected by regex, the scanner returns immediately at `warrior_scanner_service.py:1430` — the AI never gets a second opinion.

NPT 2026-03-03 was falsely rejected by the regex `offering` pattern matching "Initial Public Offering". The AI tiebreaker would likely have caught this, but it never ran.

---

## Questions to Investigate

1. **Was this intentional?** Review the multi-model pipeline design. Was the negative-only-regex behavior a deliberate safety choice ("better to miss a trade than take a bad one") or an oversight?

2. **How does `_run_multi_model_catalyst_validation()` work?** Trace through lines 1443+ of `warrior_scanner_service.py`. What exactly does it validate? How does the Flash-Lite AI assess headlines? Could the same mechanism work for negative catalysts?

3. **What would it take architecturally?** If we added AI review to negative rejections:
   - Would it require an API call for every rejected stock? (cost/latency concern)
   - Could we use the headline cache to avoid redundant calls?
   - Should AI override regex, or just flag disagreements for human review?

4. **Rate limits and latency.** The scanner runs every ~2 minutes and evaluates many stocks. Adding AI calls to the negative path could hit rate limits or slow down the scan cycle. Quantify: how many stocks get `negative_catalyst` rejections per day? (Check `data/telemetry.db` or scan logs.)

5. **Are there other negative false-positive scenarios?** Not just IPO → offering. What about:
   - "Settlement" in acquisition context → `sec_or_legal`?
   - "Warns of strong demand" → `guidance_cut`?
   - Review the negative regexes for similar ambiguity risks.

---

## Deliverable

A research report with:
- Whether the gap was intentional or an oversight
- Architecture options (with trade-offs: cost, latency, accuracy)
- Frequency of negative rejections (data-backed)
- Other regex false-positive risks in the negative patterns
- Recommended approach
