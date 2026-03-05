# Backend Planner Handoff: Technical Indicators Audit

**Date:** 2026-03-04 13:27 ET (updated)  
**From:** Coordinator  
**To:** Backend Planner  
**Output:** `nexus2/reports/2026-03-04/research_technical_indicators_audit.md`

---

## MANDATORY: Read Strategy File First

**Before making ANY claims about what Ross does or doesn't use, read `.agent/strategies/warrior.md`.**

Key sections for this audit:
- **§8 (line 298)** — Intraday Technical Indicators: Used vs Not Used
- **§8.1 (line 313)** — MACD Ground Truth (verified from training video)
- **§1 Pillar 5 (line 19)** — Daily chart / 200 MA
- **§2.1 (line 51)** — Entry triggers (VWAP, PMH, HOD, etc.)

Do NOT invent or assume Ross's methodology. Cite the strategy file line numbers for all methodology claims.

---

## Task

Audit every technical indicator and data signal that the Warrior Bot computes at or before entry time. For each, determine:

1. **Where it's computed** (file, function, line)
2. **Whether it gates entries** (hard block), **feeds scoring** (penalty/bonus), or is **display-only** (dashboard/metadata)
3. **If display-only: should it gate or score entries?** (cite strategy file for rationale)

## Indicators to Check

| Indicator | What to find |
|-----------|-------------|
| MACD (status, value, histogram) | Is there a MACD gate? Does it hard-block or just log? Strategy says "hard binary gate" (§8.1) |
| VWAP (above/below) | Is above-VWAP required for entry? Strategy says "primary bias" (§8) |
| EMA 9 (above/below) | Is above-EMA9 required? Strategy does NOT list EMA 9 — where did this gate come from? |
| EMA 200 (value, room_to_ema_pct) | Confirmed display-only at entry. Strategy mentions "room to 200 MA" in Pillar 5 (scanner) |
| Volume / RVOL | Strategy says "5x RVOL prerequisite for MACD signals" (§8.1 line 322). Is this implemented? |
| Volume expansion | Was previously dead code — is it still? |
| Level 2 / Order flow | Strategy says "primary tool for reading supply/demand" (§8 line 305). **The platform has L2 built in** — is it used in entry decisions? |
| Position health composite | Display-only — verify |
| SPY context (above 20MA, 50MA, etc.) | Is SPY health used in entry decisions? |
| Spread (bid/ask) | Strategy says "check spread" (§2.1 line 48). Is spread checked before entry? |
| Falling knife / high-vol red candle | Which patterns does this guard? All or just VWAP break? |
| Any others discovered | |

## Deliverable

A matrix table showing each indicator with: computed (Y/N), gates entries (Y/N), feeds scoring (Y/N), display-only (Y/N), strategy file reference, and recommendation.
