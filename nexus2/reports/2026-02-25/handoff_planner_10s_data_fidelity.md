# Handoff: Investigate 10s Bar Data Fidelity in Test Cases

**Agent:** Backend Planner
**Priority:** P2 — simulation fidelity investigation
**Date:** 2026-02-25

---

## Context

All 5 entry pattern toggle sweeps (hod_break, pullback, micro_pullback, vwap_break, dip_for_level) showed identical P&L ($164,421) whether enabled or disabled. This means none of these alternative patterns are firing in our 35 test cases.

Warrior Bot can see 10-second candles live, but test cases may use 1-minute candles. This granularity gap could affect:
- Entry timing precision
- Pattern detection (micro pullbacks, breakout confirmation)
- Whether alternative patterns would trigger with finer-grained data

Clay confirmed some test cases already use 10s bars (e.g., GRI).

## Open Questions (Investigate These)

1. **Which test cases have 10s bar data vs 1min?**
   - How are bar timeframes configured per case?
   - Where does the HistoricalBarLoader get its data?

2. **What does `entry_bar_timeframe` in warrior_settings.json actually control?**
   - Currently `"1min"` — does this affect simulation replay?
   - Does the sim engine use this to determine which bars to load?

3. **For cases WITHOUT 10s data, can we backfill from Polygon?**
   - Are 10s aggregates available for all our test dates (Jan-Feb 2026)?
   - What would the API cost be?

4. **Would 10s data change entry behavior?**
   - Does pattern detection (micro_pullback, vwap_break, etc.) use the entry bar timeframe?
   - Could finer granularity unlock entries that 1min bars miss?

5. **Are there any patterns that ONLY fire on sub-minute data?**
   - e.g., micro pullback checking for dips that happen within a single 1min candle

## Output

Write findings to: `nexus2/reports/2026-02-25/spec_10s_data_fidelity.md`

Include:
- Inventory of which cases have 10s vs 1min data
- How `entry_bar_timeframe` flows through the sim pipeline
- Recommendation on whether upgrading all cases to 10s would improve simulation fidelity
- Estimated effort to backfill 10s data for remaining cases
