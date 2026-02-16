# Strategy Expert: Ross Cameron's Position Building & Add Methodology

**Date:** 2026-02-16  
**Objective:** Extract Ross Cameron's exact behavior for adding to positions after entry  
**Purpose:** Design a proper "confirmation add" for Warrior bot scaling  

---

## Context

We discovered that the Warrior bot's current scaling module accidentally adds 50% shares to every position on the first eligible bar (near entry price). This accidental behavior adds +$3,681 (+38%) to batch P&L. But it's broken code, not intentional design.

We need to replace it with something intentional and methodology-aligned. Before building, we need to understand Ross's actual behavior.

## Research Questions

### Q1: Starter → Full Position Timing
When does Ross go from his "break the ice" starter to full position?
- How many seconds/minutes after initial entry?
- What confirms it for him? (Price holds? New high? Volume?)
- Does he ever skip the full position and stay small?

**Source to check:** `warrior.md` Section 2.2, transcript recaps

### Q2: What Triggers an Add vs. What Blocks It?
From `warrior.md:74-84`:
> - Every 50¢ higher ($6.00 → $6.50 → $7.00)
> - Break of key levels (half-dollar, whole-dollar)
> - Break of high-of-day
> - After taking partial profit and stock holds the level

**Need specifics:**
- Does the FIRST add require a new high, or just holding the entry level?
- How much of a pullback makes him NOT add?
- Does he add on the first candle after entry, or wait for a setup?

### Q3: Add Size Relative to Starter
Ross says he starts with ~5,000 shares and builds to 10,000-15,000.
- Is the first add typically 2x the starter? 1.5x?
- Are subsequent adds smaller ("progressively smaller if price is getting expensive")?

### Q4: Time Window for Adds
- Does Ross add within the first minute? First 5 minutes?
- Is there a point where he stops adding and just manages the position?
- Average hold time is ~2 minutes — how does add timing relate?

### Q5: First Pullback Exception
`warrior.md:72` says: "with one exception: dip-buying the first pullback after an initial move"
- How deep is "first pullback"? Back to entry? VWAP? 
- Does this only apply after an initial move UP, not immediately?
- Is this the ONLY pullback add, or does he add on subsequent pullbacks?

## Sources to Check

1. **Primary:** `.agent/strategies/warrior.md` (Sections 2.2, 2.3, 3.1)
2. **KI Artifact:** Trading methodologies KI → `warrior/strategy/warrior_master_strategy_and_architecture.md`
3. **KI Artifact:** `warrior/intelligence/master.md` (methodology extraction)
4. **Transcript archives:** `warrior/intelligence/transcripts/` for specific add examples
5. **Research doc from earlier today:** `nexus2/reports/2026-02-16/` — check for any scaling/home-run research

## Output Format

Write findings to: `nexus2/reports/2026-02-16/research_ross_add_methodology.md`

Structure:
1. **Verified Rules** — Things Ross explicitly states with quotes
2. **Observed Patterns** — Consistent behavior across examples
3. **Open Questions** — Ambiguities that need Clay's input
4. **Bot Design Implications** — What this means for the confirmation add feature

**IMPORTANT:** Cite transcript sources. No invented thresholds. If uncertain, say so.
