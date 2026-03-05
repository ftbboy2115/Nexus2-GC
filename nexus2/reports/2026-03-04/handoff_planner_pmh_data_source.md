# Backend Planner Handoff: PMH Data Source Investigation

**Date:** 2026-03-04 11:03 ET  
**From:** Coordinator  
**To:** Backend Planner  
**Output:** `nexus2/reports/2026-03-04/research_pmh_data_source.md`

---

## Problem

PMH bar fix was deployed twice but Polygon still returns zero premarket bars:
```
[Warrior PMH] VCIG: No pre-market bars found in Polygon data (135 total bars)
[Warrior PMH] CANF: No pre-market bars found in Polygon data (156 total bars)
```

CANF clearly has premarket activity ($4→$15 on chart). FMP fallback gives $8.73 — possibly wrong (chart peak ~$15).

## Questions

1. **Does `_get_intraday_bars` request extended hours?** Check the Polygon adapter — many APIs default to regular-hours only. Look for `extended_hours=True` or `premarket=True` type params.

2. **What does Polygon actually return?** Write a quick diagnostic: fetch CANF 1-min bars via the adapter and log the first/last timestamps. Are they all after 9:30?

3. **Is FMP's premarket high accurate?** Compare FMP's $8.73 for CANF against the chart showing ~$15 peak. What endpoint does `get_premarket_high()` use?

4. **Polygon API docs:** What parameter enables premarket bar data? Check the Polygon aggregates endpoint documentation.

## Deliverable

Short report with: what's wrong, exact fix needed, and whether FMP fallback is reliable.
