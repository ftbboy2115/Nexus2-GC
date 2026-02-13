# Strategy Expert Handoff: Scanner Methodology Comparison

## Objective

Compare the Warrior scanner's filter criteria against Ross Cameron's actual stock selection methodology. Identify false disqualifiers (scanner rejects stocks Ross would trade) and missing criteria (things Ross checks that scanner doesn't).

## Context

The scanner implements "5 Pillars" but currently finds **zero** candidates while Ross trades 2-4 stocks daily. Ross's recent traded symbols don't even appear in the scan candidate list.

## Reference Materials

Read these FIRST:
- `.agent/strategies/warrior.md` — Ross Cameron strategy file
- Recent transcripts in `.agent/knowledge/warrior_trading/` (Feb 2026 files)
- `nexus2/domain/scanner/warrior_scanner_service.py` L85-167 (WarriorScanSettings)

## Tasks

### T1: Ross's Recent Trades — What Attracted Him

For each of these symbols, find the relevant transcript and document what Ross said about why he chose it:

| Date | Symbol | Transcript |
|------|--------|-----------|
| Feb 10 | EVMN | Check `.agent/knowledge/warrior_trading/2026-02-*` |
| Feb 10 | VELO | Same |
| Feb 11 | BNRG | Same |
| Feb 11 | PRFX | Same |
| Feb 12 | PMI | Same |
| Feb 12 | RDIB | Same |

Document: catalyst type, gap%, float estimate, volume comments, price range.

### T2: Threshold Comparison

Compare scanner settings vs Ross's actual criteria:

| Criterion | Scanner Threshold | Ross's Actual Practice | Aligned? |
|-----------|------------------|----------------------|----------|
| Float | max 100M | ? | ? |
| RVOL | min 2.0x | ? | ? |
| Gap % | ? | ? | ? |
| Price range | ? | ? | ? |
| Catalyst req | AI-validated | ? | ? |
| 200 EMA check | enabled | ? | ? |
| MACD check | enabled | ? | ? |

### T3: False Disqualifiers

Identify scanner filters Ross does NOT use. For example:
- Does Ross check MACD? 
- Does Ross check 200 EMA room?
- Is the negative_catalyst AI filter too aggressive?

### T4: Missing Criteria

Identify things Ross explicitly looks for that the scanner doesn't check.

## Deliverable

Write report to `nexus2/reports/2026-02-13/scanner_methodology_comparison.md`
