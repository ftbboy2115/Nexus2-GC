# Backend Planner Handoff: VCIG EMA Data Quality + Health Metrics Investigation

**Date:** 2026-03-04 11:41 ET  
**From:** Coordinator  
**To:** Backend Planner  
**Output:** `nexus2/reports/2026-03-04/research_vcig_ema_health.md`

---

## Context

VCIG is currently in a live trade. Scanner data shows clearly broken metrics:
- **EMA 200 = $665,900.34** — stock is trading at ~$9. This is obviously wrong.
- **room_to_ema_pct = -99.998%** — broken because EMA is wrong.
- **Dashboard health indicators show red** — but the bot entered anyway.

## Questions to Investigate

### 1. Why is EMA 200 = $665,900?
- Where does the scanner get the EMA 200 value? Which data source/endpoint?
- Is it using unadjusted historical data? Did VCIG have a reverse split?
- What does the actual API return for VCIG's EMA 200?

### 2. Where is room_to_ema_pct calculated?
- What file/function computes this?
- Is it purely derived from the broken EMA, or does it have its own data source?

### 3. Do health metrics gate entries?
- Does the scanner or entry engine check EMA 200, room_to_ema_pct, or "health" before entering?
- Or are these display-only metrics that show on the dashboard but don't affect decisions?
- If they don't gate entries, should they?

### 4. What safeguards exist for bad EMA data?
- Is there any sanity check for absurd EMA values (e.g., EMA > 100x price)?
- If not, what would be appropriate?

## Deliverable

Report answering each question with evidence (file paths, line numbers, code snippets). Recommend fixes.
