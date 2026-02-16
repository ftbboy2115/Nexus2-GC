# Strategy Expert Handoff: Re-Entry Methodology Research

## Task
Research Ross Cameron's actual methodology for **re-entering trades** after a profitable exit.

## Context
Our Warrior bot currently allows unlimited re-entries after trades. A/B testing shows:
- **8 cases** benefit from re-entries (net +$5,466 value) — re-entry captured a "second wave"
- **6 cases** are hurt by re-entries (net -$1,660) — re-entry was into a fading stock

We need to understand **Ross's actual rules** for when he re-enters vs stays out.

## Research Questions

1. **When does Ross re-enter?** After a profitable exit, what conditions must be met?
2. **Quality gates**: Does he check momentum (MACD, volume), trend (VWAP), or price action?
3. **Timing**: Is there a cooldown? Does he wait for a new setup to form?
4. **How many times?** Max re-entries per symbol per day?
5. **What disqualifies re-entry?** When does Ross explicitly say "I'm done with this stock"?
6. **Base hit vs home run**: Does exit mode affect re-entry decisions?

## Source Materials
- Transcripts in `.agent/strategies/warrior.md`
- KI: `trading_methodologies` → `warrior/strategy/warrior_master_strategy_and_architecture.md`
- KI: `warrior_trading_automation` → `intelligence/methodology_extraction.md`
- Daily recap transcripts in KI: `trading_methodologies` → `warrior/intelligence/transcripts/`

## Deliverable
Write findings to: `nexus2/reports/2026-02-15/research_reentry_methodology.md`

Structure:
1. **Verified Rules** (explicit quotes from Ross)
2. **Observed Patterns** (inferred from behavior)
3. **Non-Rules** (things Ross does NOT check)
4. **Open Questions** (ambiguities needing Clay's input)
