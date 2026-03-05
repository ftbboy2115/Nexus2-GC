# Backend Planner Handoff: MOBX Entry Bug Investigation

**Date:** 2026-03-04 06:54 ET  
**From:** Coordinator  
**To:** Backend Planner  
**Output:** `nexus2/reports/2026-03-04/research_mobx_entry_bugs.md`

---

## Context

MOBX 2026-03-04 entered two losing trades. Both entries reveal multiple entry guard failures. Investigate all of the following.

**Trade data:**
- Trade 1: Entry $1.36 at 11:15 → Exit $1.34 at 11:31 (candle_under_candle, -$0.20)
- Trade 2: Entry $1.37 at 11:33 → Exit $1.35 at 11:36 (topping_tail, -$0.20)
- Both trigger: `pmh_break`
- Scanner: PASS score=8, gap=36%, catalyst=earnings

**Chart context:** Premarket high was ~$1.70. Stock faded to $1.35 area. Entries at $1.36/$1.37 are 20% below PMH.

---

## Questions to Investigate

### 1. PMH Value Bug
The entry triggered as `pmh_break` at $1.36, but the chart shows PMH at ~$1.70. 

- How is `watched.pmh` set? (`warrior_engine.py:561-565` shows `pmh or candidate.session_high` fallback)
- Did `_get_premarket_high()` return None for MOBX? If so, why?
- **Key insight from Clay:** Polygon (the primary data provider) already has premarket bar data. The PMH can be derived from max(high) of pre-9:30 bars. Why is the code calling FMP instead?
- What is the `session_high` fallback actually tracking? Is it being recalculated/reset as the stock moves?

### 2. Price Floor Missing at Entry
Scanner min_price is $1.50. MOBX entered at $1.36. The scanner checked price at scan time (~$1.80+), but the entry engine doesn't re-check before executing.

- Verify: is there ANY price check in the entry path (`warrior_engine_entry.py`)?
- If not, what's the right place to add one?

### 3. Re-entry Cooldown Failure
Trade 1 exited at 11:31. Trade 2 entered at 11:33 — only **2 minutes** later. The live re-entry cooldown should be 10 minutes.

- Check `warrior_entry_guards.py` for the live cooldown logic
- Was the cooldown bypassed, misconfigured, or not checked?

### 4. Sizing Configuration
What are the actual PAPER mode sizing parameters? Check:
- `max_shares_per_trade`
- `max_value_per_trade`
- `risk_per_trade`
- `max_capital`
- How these interact to produce 10 shares at $1.36

### 5. Dynamic Scoring Impact
Entry metadata shows: VWAP $1.36, MACD 0.005 (flat), above EMA9 ($1.34). 

- What score did the dynamic scoring produce for these entries?
- Should the below-VWAP, negative-MACD signals have blocked or penalized the entry?

---

## Deliverable

A research report documenting each bug with evidence (exact code paths, line numbers, config values). Recommend fixes in priority order.
