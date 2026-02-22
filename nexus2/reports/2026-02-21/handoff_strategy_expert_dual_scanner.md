# Handoff: Strategy Expert — Ross Cameron's Dual Scanner Research

**Date:** 2026-02-21
**From:** Coordinator
**To:** Strategy Expert (`@agent-strategy-expert.md`)
**Priority:** HIGH — blocks scanner architecture decisions

---

## Objective

Research and document Ross Cameron's scanner types. In the HIND video (Jan 27, 2026), Ross explicitly mentions using **two scanners**:

> "even before it hit my high of day momentum scanner, it was on my top gainers scanner"

We need to understand what these scanners are, how they differ, and what criteria each uses.

---

## Verified Facts

- **Transcript location:** `.agent/knowledge/warrior_trading/2026-01-27_transcript_RAJXknk-VI4.md`
- **Quote (from transcript, line 163):** Ross says HIND appeared on "top gainers scanner" before "high of day momentum scanner"
- **Current scanner:** Our Warrior scanner uses gap%, RVOL, float, catalyst as primary filters
- **HIND failure:** Scanner rejects HIND because RVOL 1.9x < 2.0x hard gate. Ross made $55k on HIND.

---

## Open Questions (Investigate These)

1. **What are Ross's scanner types?** Does he use exactly two, or more? Names?
2. **What criteria does each scanner use?** 
   - "Top Gainers" — is this purely % change? Volume? Time window?
   - "High of Day Momentum" — what triggers this? Price making new HOD? With what volume/momentum threshold?
3. **Which scanner surfaces stocks FIRST?** Does one act as an early warning and the other as confirmation?
4. **Does Ross mention scanner criteria in other transcripts?** Check the transcript vault for references.
5. **What is Ross's actual RVOL threshold?** Does he state one? Or is RVOL only relevant for certain scanner types?

---

## Research Sources (Priority Order)

1. **Ross's public teaching materials** (PRIMARY — start here):
   - **Article:** https://www.warriortrading.com/day-trading-watch-list-top-stocks-to-watch/
   - Search warriortrading.com for scanner setup, watch list criteria, gap scanner, momentum scanner
   - Ross publishes extensive free training — mine it thoroughly before looking elsewhere
2. **Internal transcripts:**
   - `.agent/knowledge/warrior_trading/2026-01-27_transcript_RAJXknk-VI4.md` (HIND/BCTX — dual scanner quote)
   - Transcript Vault: check all transcripts for scanner mentions
3. **Strategy file:** `.agent/strategies/warrior.md` — current documented methodology
4. **KI artifacts:** `trading_methodologies` KI for scanner-related documentation
5. **Other Ross sources:** YouTube channel descriptions, Warrior Trading blog posts, course previews

---

## 🚨 Anti-Hallucination Protocol 🚨

> [!CAUTION]
> The strategy docs and transcripts may NOT contain specific scanner specs.
> **Do NOT invent criteria to fill gaps.**

### Rules
1. **Research exhaustively FIRST** — read all transcripts, check all KI artifacts, search warriortrading.com
2. **Categorize every finding** into three tiers:
   - **VERIFIED** — Ross stated this explicitly (include direct quote + source)
   - **INFERRED** — Reasonable deduction from Ross's behavior (explain reasoning)
   - **UNKNOWN** — Cannot be determined from available sources (list as open question)
3. **If scanner criteria aren't documented**, it's acceptable to:
   - Propose plausible options based on observable behavior (labeled as INFERRED)
   - Note what we'd need to ask Ross or test empirically
   - **NOT** state inferences as facts

---

## Deliverable

Write a research report to: `nexus2/reports/2026-02-21/research_ross_dual_scanner.md`

The report should include:
1. **Scanner Types** — enumeration with names and purposes
2. **Criteria Matrix** — what each scanner filters on (gap%, RVOL, % change, HOD momentum, etc.)
3. **Discovery Timeline** — which scanner fires first and how Ross uses them together
4. **Evidence Table** — every claim with: tier (VERIFIED/INFERRED/UNKNOWN), direct quote, source URL/file
5. **Implications for Nexus** — what we'd need to change/add to match his scanner setup
6. **Open Questions** — anything that couldn't be determined, with suggested next steps
