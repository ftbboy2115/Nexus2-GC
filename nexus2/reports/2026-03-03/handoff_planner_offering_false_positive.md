# Backend Planner Handoff: Offering False-Positive Investigation

**Date:** 2026-03-03 15:14 ET  
**From:** Coordinator  
**To:** Backend Planner  
**Output:** `nexus2/reports/2026-03-03/research_offering_false_positive.md`

---

## Problem

NPT 2026-03-03 was rejected by the scanner with `negative_catalyst:offering` despite having excellent metrics (25-31x RVOL, 2.9M float, ~25% gap). Ross traded it for +$8,312. The offering was HISTORICAL — no new negative catalyst today.

---

## Verified Facts (Coordinator)

1. **Negative catalyst check:** `warrior_scanner_service.py:1380` calls `classifier.has_negative_catalyst(headlines)` on whatever headlines are passed in
2. **`has_negative_catalyst()`:** `catalyst_classifier.py:322-334` — iterates headlines, returns True on first match with confidence ≥ 0.9. **No date filtering.**
3. **Offering regex:** `catalyst_classifier.py:179-181` — matches `\b(offerings?|public\s+offering|registered\s+direct|at-the-market|atm\s+offering|dilution)\b`
4. **Momentum override thresholds:** RVOL ≥ 50x AND gap ≥ 30% (lines 143-145). NPT had ~31x RVOL and ~25% gap — didn't qualify.
5. **Headlines source:** `catalyst_lookback_days` setting controls how far back FMP headlines are fetched

---

## Open Questions (Investigate)

1. **Where are headlines fetched?** Find the FMP call that provides `headlines` to `_evaluate_catalyst_pillar()`. Does it already filter by date? What is `catalyst_lookback_days` set to?

2. **Clay believes recency logic exists** — search the entire scanner pipeline for any date-based filtering of negative catalysts. Check:
   - `get_news_with_dates()` 
   - `get_headlines_with_urls()`
   - Any headline caching that might carry stale data
   - The AI catalyst validation pipeline (multi-model)
   - Headline cache (`get_headline_cache()`)

3. **What headlines did NPT actually have?** Check `data/catalyst_audit.log` for NPT entries from 2026-03-03. What was the actual headline that triggered the offering match?

4. **Is the recency gap in the NEGATIVE path specifically?** The positive catalyst path (line 1369) uses `get_news_with_dates()` with dates. Does the negative check use a different headline source?

5. **Is there a stale headline cache?** The scanner uses `self._cached()` for various data. Could old headlines be cached and served up on subsequent scans?

---

## Expected Research Output

- Exact flow: where headlines are fetched → what date range → how they reach `has_negative_catalyst()`
- Whether recency logic exists and where it breaks down
- The specific NPT headline that caused the rejection
- Recommended fix approach (with evidence, not speculation)
