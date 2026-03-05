# Backend Planner Handoff: Entry Quality & Scoring Investigation

**Date:** 2026-03-03 10:33 ET  
**From:** Coordinator  
**To:** Backend Planner  
**Output:** `nexus2/reports/2026-03-03/research_entry_quality_gap.md`

---

## Context

The Warrior Bot's pattern scoring system (`warrior_entry_scoring.py`) is **blind to real-time price action**. In today's live PAPER session (18 closed trades, net ~-$2.60), the bot entered the same stock (RUBI) 3 times with nearly identical scores (~0.793) despite the setup visibly deteriorating on the chart between entries.

The scoring system uses 6 factors — 85% of weight comes from scanner metadata that never changes. The remaining 15% barely moves. **The bot cannot distinguish a fresh momentum breakout from a fading stock.**

Yet batch tests show $355,039 P&L across 39 test cases (79.5% capture). Clay asked: "How is the bot getting such PnL if it's so blind?" — and the coordinator's initial answer contained unverified claims.

---

## Verified Facts

1. **Scoring system is static** — Confirmed from `warrior_entry_scoring.py`. Factors: pattern_confidence (50%, hard-coded per pattern type), volume_ratio (20%, scanner metadata), catalyst_strength (15%, scanner metadata), spread (5%), level_proximity (5%), time_score (5%).

2. **PMH_BREAK score is ~0.793 consistently** — Confirmed from VPS server logs for RUBI today. Score was 0.789–0.797 across 40+ checks spanning 90 minutes.

3. **MIN_SCORE_THRESHOLD = 0.40** — Confirmed from code. A score of 0.793 always passes. The scoring effectively never blocks.

4. **Test suite includes winning AND losing Ross trades** — Confirmed from `warrior_setups.yaml`: BENF (-$2.3K), BNAI (-$7.9K), RVSN (-$3K), SXTC (-$5K), EVMN (-$10K), VELO (-$2K).

5. **All stop-tightening approaches were net negative** — From handoff doc `handoff_coordinator_bag_holding_complete.md`.

---

## Open Questions (Investigate From Scratch)

### Q1: How does `gc_quick_test.py` execute each test case?

- Does each case run in isolation (single stock, single day)?
- Or does it simulate a full day with multiple stocks?
- Does the TOP_3_ONLY guard apply in batch mode?
- Starting points: `scripts/gc_quick_test.py`, `nexus2/tests/test_cases/warrior_setups.yaml`

### Q2: What is the P&L distribution across the 39 test cases?

- How many are positive vs negative for the BOT (not Ross)?
- Are a few mega-winners carrying the total? (ROLR ross_pnl=$85K, NPT $81K, HIND $55K, PAVM $43K)
- What's the bot's P&L on those specific cases?
- Starting point: `nexus2/reports/gc_diagnostics/baseline.json`

### Q3: Does the bot face re-entry situations in batch mode?

- When the bot is stopped out in batch mode, does it re-enter the same stock?
- If yes, how do re-entry scores compare to first-entry scores?
- If no, why not? (cooldown, max entries, or single-pass simulation?)
- Starting points: `warrior_entry_guards.py` (re-entry cooldown logic), `sim_context.py`

### Q4: What differentiates winning entries from losing entries?

For each of the 39 test cases, capture (if logged):
- Bot entry price vs Ross entry price
- Pattern trigger type and score
- MACD value and EMA position at entry time
- Whether price was above/below VWAP at entry
- Hold time (entry to exit)
- Whether the bot caught the initial move or entered late

### Q5: What price-action factors COULD the scoring system use?

Based on the code in `warrior_engine_entry.py` and `warrior_entry_patterns.py`:
- What real-time data is already fetched but NOT used for scoring?
- MACD value, EMA positions, VWAP position — are these available at scoring time?
- What would it take to pass them into `score_pattern()`?

---

## Key Files

| File | Purpose |
|------|---------|
| `nexus2/domain/automation/warrior_entry_scoring.py` | Pattern scoring (202 lines) |
| `nexus2/domain/automation/warrior_engine_entry.py` | Entry trigger logic (1549 lines) |
| `nexus2/domain/automation/warrior_entry_patterns.py` | Pattern detection (1488 lines) |
| `nexus2/domain/automation/warrior_entry_guards.py` | Entry guards incl. cooldown |
| `scripts/gc_quick_test.py` | Batch test runner |
| `nexus2/tests/test_cases/warrior_setups.yaml` | Test case definitions |
| `nexus2/reports/gc_diagnostics/baseline.json` | Latest baseline results |
| `nexus2/domain/automation/trade_event_service.py` | What gets logged per entry |

---

## Deliverable

Write findings to `nexus2/reports/2026-03-03/research_entry_quality_gap.md` with:
1. Answers to Q1-Q5 with **code evidence** (file:line, exact snippets)
2. P&L distribution table (bot P&L per case)
3. Specific recommendations for price-action-aware scoring factors
4. Assessment of implementation complexity for each recommendation
