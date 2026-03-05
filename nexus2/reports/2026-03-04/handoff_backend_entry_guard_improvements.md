# Backend Specialist Handoff: Falling Knife Extension + RVOL Prerequisite

**Date:** 2026-03-04 13:48 ET  
**From:** Coordinator  
**To:** Backend Specialist  
**Audit:** `nexus2/reports/2026-03-04/research_technical_indicators_audit.md`  
**Validation:** `nexus2/reports/2026-03-04/validation_technical_indicators_audit.md`  
**Strategy:** `.agent/strategies/warrior.md`  
**Output:** `nexus2/reports/2026-03-04/backend_status_entry_guard_improvements.md`

---

## A/B Testing Protocol

> [!CAUTION]
> **DO NOT run `python scripts/gc_quick_test.py` yourself.** This script requires the uvicorn server running in Clay's terminal and will fail in your terminal. Instead:
> 1. Implement Fix #1
> 2. Tell Clay to run: `python scripts/gc_quick_test.py --all --diff`
> 3. Wait for Clay to paste results
> 4. Implement Fix #2
> 5. Tell Clay to run it again
> 6. Report per-fix P&L deltas in your status report

**Clay runs the batch tests. You implement the code changes.**

---

## Fix #1: Extend Falling Knife Guard to All Patterns (HIGH)

**Problem:** The falling knife and high-volume red candle quality checks only guard the VWAP_BREAK pattern. The other 10 entry patterns (PMH_BREAK, HOD_BREAK, ABCD, etc.) have no protection against entering during sharp selloffs.

**Fix:** Move the falling knife / high-vol red candle guard from inside the VWAP_BREAK pattern detection to the shared entry guard layer (`warrior_entry_guards.py`) so it protects ALL patterns.

**Important:** Check the audit report for exactly where this guard lives now and which function to extract it from.

---

## Fix #2: Add RVOL ≥ 5x Prerequisite for MACD Gate (HIGH)

**Problem:** The MACD gate (histogram < -0.02 = block) fires without checking RVOL. Per Ross's methodology (warrior.md §8.1 line 322):

> "Requires **5x RVOL** as a prerequisite for MACD signals to be meaningful"

This means the MACD gate should only fire when RVOL ≥ 5x. Below 5x RVOL, MACD signals aren't meaningful and shouldn't block trades.

**Fix:** Add RVOL check before the MACD gate:
```python
# MACD gate only applies when RVOL >= 5x (warrior.md §8.1 L322)
if rvol >= 5.0 and macd_histogram < -0.02:
    # Block entry
```

**Where to get RVOL:** Check how the scanner candidate's RVOL is passed to the entry engine. The audit report will have the data flow.

---

## Verification

Report per-fix P&L impact separately:
- Fix #1 alone: $X delta
- Fix #1 + #2 combined: $Y delta

Include per-case breakdowns for any changed cases.
