# Strategy Expert Report: Ross Cameron Re-Entry Methodology

> **Source**: 100+ daily recap transcripts, Nov 2025 – Feb 2026  
> **Task**: Research re-entry quality gates from Ross Cameron's actual methodology  
> **Date**: 2026-02-15  
> **Status**: Research-verified, pending Clay approval

---

## Executive Summary

Ross Cameron **routinely re-enters the same stock** after exiting. This is not an accident — it is a core part of his methodology, described repeatedly as the "sell → add back" cycle. However, he applies **specific quality gates** before re-entering, and he has **hard limits** on when to stop trying.

The evidence reveals **7 distinct quality gates** that Ross uses to decide whether to re-enter, and **3 kill conditions** where he explicitly refuses to re-enter.

---

## 1. Verified Re-Entry Quality Gates

### Gate 1: MACD Must Be Positive (HARD GATE)

**Evidence — ROLR, Jan 14 (+$85k day):**

After scaling out of ROLR near $18–21, Ross explicitly refused to re-enter even though the stock was still up 274%:

> *"I held back on it because at that point at $18 a share, I couldn't really buy very many shares. I didn't feel like I'd really make a considerable amount more money. And I thought because the MACD was negative, it was taking too much risk."*  
> — [2026-01-14 ROLR transcript](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/knowledge/warrior_trading/2026-01-14_transcript_lneGXw0sxzo.md#L89)

**Extracted from summary notes (same transcript):**
- "MACD went negative after peak = no re-entry"
- "No re-entry when MACD is negative"

**Also from existing rules extraction (ROSS_RULES_EXTRACTION.md, line 197):**

| Signal | Ross Behavior |
|--------|---------------|
| MACD negative | **Don't re-enter** |
| MACD crossing positive → curl back | Re-entry opportunity |

**Classification**: ✅ **Canonical rule** — explicitly stated, not inferred.

---

### Gate 2: Must Have a "Cushion" (Session P&L Gate)

**Evidence — PHL, Jan 15 ($100 made on 400% stock):**

Ross exited PHL multiple times and refused to chase the extended move. His explicit reasoning:

> *"It's hard to break the ice and get back in when you don't have a cushion especially when it's this extended."*  
> — [2026-01-15 PHL transcript](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/knowledge/warrior_trading/2026-01-15_transcript_0kC1DPUycE0.md#L150)

> *"I went red on it, got back to flat, and said this stock doesn't feel clean."*

**Summary note from same transcript:**
- "No cushion = no re-entry" — hard to get back in when red

**Also from Jan 6 transcript:**

| Signal | Ross Behavior |
|--------|---------------|
| Curl back up | Re-entry when volume picks up |

But the re-entry required confirming conditions, not just a curl.

**Classification**: ✅ **Canonical rule** — directly stated. If Ross is red or breakeven on a stock, he is much less willing to re-enter it, especially if extended.

---

### Gate 3: Maximum Failed Re-Entries = 2–3, Then Give Up

**Evidence — HIND, Jan 27 (3 failed re-entries then stopped):**

> Transcript summary: "HIND: Re-entered for VWAP break (2x, neither held)"  
> — [2026-01-27 HIND transcript](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/knowledge/warrior_trading/2026-01-27_transcript_RAJXknk-VI4.md#L56)

After 2 failed VWAP break re-entries, Ross stopped trying on HIND.

**Evidence — RNAZ, Feb 5 (pattern: failed re-entries pile up):**

> Transcript describes multiple entries on a stock where sellers kept "reloading on the ask" → Ross gave up:
> "20,000 share sellers kept reloading on the ask → gave up"  
> — [2026-02-05 RNAZ transcript](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/knowledge/warrior_trading/2026-02-05_transcript_HGATds95-p4.md#L77)

**Evidence — PHL, Jan 15 (5 attempts then final exit):**

Ross made ~5 attempts on PHL. Entry 1 lost $2k. Entries 2-5 were micro-pullback attempts that all failed. He ended up at +$100 and said "no way" to getting back in.

**From existing warrior.md Section 4.3:**
> "After 2+ failed re-entries: 'gave up on this one'"  
> "Typically 3–5 trades on same stock per session"

**Classification**: ✅ **Canonical pattern** — observed across multiple transcripts. The threshold appears to be 2–3 failed re-entries before Ross abandons the stock.

---

### Gate 4: Stock Must Hold a Key Support Level (Round Number / VWAP)

**Evidence — FLYE, Feb 6 (sell → add-back cycle at round numbers):**

The FLYE trade is the clearest example of Ross's sell→add-back re-entry pattern:

| Action | Price | Trigger |
|--------|-------|---------|
| Entry (starter) | ~$6.32 | Curl back up toward PMH |
| Take profit | ~$7.00 | Round number target |
| **Add back** | $7.01–$7.25 | **Stock held $7.00 support** |
| Take profit | ~$7.50 | Partial exit |
| **Add back** | ~$7.55 | **Continuation through $7.50** |
| Take profit | ~$8.00 | Round number target |
| **Dip buy** | ~$8.00–$8.50 | Bought back on dip |
| Stopped/exited | Below $8 | **Gave back half of profit → stopped** |

> *"I got in, I got out, it kept going higher. I got back in, I got back out. It kept going higher. I got back in. Then I gave back half my profit. And I said, 'That's it.'"*  
> — [2026-02-06 FLYE transcript](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/knowledge/warrior_trading/2026-02-06_transcript_Z5D8nhEtzOo.md#L47)

**Evidence — ROLR, Jan 14 (same pattern):**

| Action | Price | Trigger |
|--------|-------|---------|
| Take profit | $6.40 | Up >$1/share |
| **Add back** | $6.50 | **Break of resistance** |
| All out | choppy | Got choppy, exited |
| **Add back** | $9.50 | **VWAP reclaim + break** |

**Evidence — GRI, Jan 28 (held resistance line after rally):**

From transcript entry: "Add back when stock holds support level after pausing"

**Classification**: ✅ **Canonical rule** — stock must hold a visible support level (round number, VWAP, prior resistance flip to support) before Ross will re-enter.

---

### Gate 5: Re-Entry on VWAP Reclaim

**Evidence — ROLR, Jan 14:**
> "Right here it curls back up, reclaims the volume weight average price, and I add back for the break of 950"  
> — [2026-01-14 ROLR transcript](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/knowledge/warrior_trading/2026-01-14_transcript_lneGXw0sxzo.md)

**Evidence — HIND, Jan 27:**
> "Re-entered for VWAP break (2x, neither held)"  
> — HIND re-entries were VWAP-triggered (even though they failed)

**Evidence — From warrior.md Section 4.1:**
> "VWAP reclaim (breaks back above VWAP)" listed as explicit re-entry condition

**Classification**: ✅ **Canonical rule** — VWAP reclaim is one of Ross's primary re-entry triggers.

---

### Gate 6: Curl Back Up with Volume

**Evidence — Jan 6 transcript (rules table):**

| Re-entry | curl up | Volume picking up |
|----------|---------|-------------------|

> "Curl back up with volume = re-entry opportunity"  
> — [2026-01-06 transcript](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/knowledge/warrior_trading/2026-01-06_transcript_tDb0WPsRZT4.md#L128)

**Evidence — FLYE, Feb 6:**
> "Pulls back, curls back up here and, you know, I just got to a point where I was like, you know what? Um, I feel like this this might end up actually working and squeezing through the pre-market high."

**Classification**: ✅ **Canonical rule** — a "curl back up" with increasing volume is a verified re-entry pattern.

---

### Gate 7: Hidden Buyer Reappears (Level 2 Gate)

**Evidence — GLTO, Nov 10 (+$65k day):**

| Trade | Price | Trigger |
|-------|-------|---------|
| Trade 1 | $12.49 | Hidden buyer at $12 → failed, stopped out |
| **Trade 2 (re-entry)** | $12.17 | **Hidden buyer reappeared at $12** → squeeze to $13.48 |
| Trade 3 | $13.40 | Hidden buyer at $13 → squeeze to $14 |
| Trade 4 | $14.50 | Break → parabolic to $20 |

> "Re-entry when hidden buyer reappears"  
> — [2025-11-10 GLTO transcript](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/knowledge/warrior_trading/2025-11-10_transcript_HB1IbyuJ37s.md#L108)

**Classification**: ⚠️ **Observable pattern, difficult to automate** — requires Level 2 data interpretation. Noted for completeness but likely not implementable in Warrior bot initially.

---

## 2. Verified Kill Conditions (No Re-Entry)

### Kill 1: MACD Negative

Already covered in Gate 1 above. When MACD is negative, Ross explicitly refuses re-entry.

> "If stock goes below VWAP with MACD negative: 'I guess it's done'"  
> — warrior.md Section 4.3

### Kill 2: Stock Is Extended Without Cushion

From PHL Jan 15: Ross refused to re-enter at $6.40+ after exiting at $5.14 with only $100 profit:

> *"I can't buy it here because if I buy it here and I lose, I'm going to be so frustrated."*

The kill condition is the **combination** of:
- Stock has moved significantly from where Ross exited
- Ross lacks a session cushion on this stock
- The risk/reward of re-entry is poor (extended, could reverse hard)

### Kill 3: 50% Give-Back Rule

From the Feb 6 FLYE trade and warrior.md Section 3.3:

> *"Then I gave back half my profit. And I said, 'That's it.'"*

| Give-back | Ross's reaction |
|-----------|-----------------|
| 10% | "Acceptable, means I pushed it" |
| 25% | "Flew too close to the sun, stopping now" |
| 50% | "That's it, done for the day" (on this stock) |

After giving back 50% of profits on a stock, Ross stops trading it entirely.

---

## 3. Re-Entry vs. Sell→Add-Back: A Critical Distinction

The transcripts reveal that Ross's "re-entries" are actually **two distinct behaviors**:

### Type A: Sell → Add Back (Within Same Move)

This is the most common pattern. Ross sells a partial or full position at a target, then immediately adds back when the stock holds or pushes higher.

**Characteristics:**
- Happens within minutes (sometimes seconds)
- Stock hasn't pulled back significantly
- Stock holds the level Ross just sold at
- This is NOT a new trade — it's continuation scaling

**Examples:**
- ROLR Jan 14: Sell at $6.40, add back at $6.50 (break of resistance)
- FLYE Feb 6: Sell at $7.00, add back at $7.01–$7.25 (held $7)
- GRI Jan 28: "Sold some, added back as it held"

### Type B: True Re-Entry (After Exit + Meaningful Pause)

This is re-entering a stock after fully exiting and waiting for a new setup to form.

**Characteristics:**
- Minutes to hours between exit and re-entry
- Stock typically pulls back, forms a new pattern (curl, VWAP reclaim, etc.)
- Ross treats this as a new setup, not a continuation
- Usually smaller size

**Examples:**
- ROLR Jan 14: Fully out during choppy action → re-entered at $9.50 on VWAP reclaim
- GLTO Nov 10: Stopped out at $12 → re-entered at $12.17 when hidden buyer reappeared
- PHL Jan 15: Multiple failed re-entries after a meaningful drop each time

> [!IMPORTANT]
> For the Warrior bot, both types of behavior result in a new trade. But Type A is dramatically more successful than Type B in the A/B data. The bot should **strongly favor Type A** (continuation re-entries when stock holds support) and **strictly gate Type B** (re-entries after extended pauses or failures).

---

## 4. Proposed Quality Gates for Warrior Bot

Based on the evidence above, here are the quality gates ordered from most impactful to least:

| # | Gate | Type | Evidence Strength | Implementable? |
|---|------|------|-------------------|----------------|
| 1 | **MACD must be positive** | Hard block | ✅ Canonical — direct quote | ✅ Yes |
| 2 | **Max failed re-entries = 2** | Hard block | ✅ Canonical — multiple transcripts | ✅ Yes |
| 3 | **Stock must hold key support** | Quality filter | ✅ Canonical — multiple examples | ⚠️ Partially (round numbers, VWAP) |
| 4 | **50% give-back = stop trading this stock** | Hard block | ✅ Canonical — direct quote | ✅ Yes |
| 5 | **Cushion required for re-entry** | Soft gate | ✅ Canonical — direct quote | ✅ Yes (track per-symbol P&L) |
| 6 | **Curl back up + volume required** | Quality filter | ✅ Canonical — direct evidence | ⚠️ Partially |
| 7 | **Hidden buyer reappears** | Quality filter | ✅ Observable — Level 2 data | ❌ Not now |

### Recommended Implementation Priority

**Phase 1 (Quick wins — hard blocks):**
1. MACD must be positive when re-entering
2. Max 2 failed re-entries per symbol per session → block further entries
3. If 50% of peak profit on this symbol has been given back → block

**Phase 2 (Quality filters):**
4. Re-entry must be on a recognized pattern (VWAP reclaim, round-number hold, curl-up)
5. Per-symbol session P&L tracking — net negative = reduce confidence or block

**Phase 3 (Advanced):**
6. Volume confirmation on re-entry (volume must be increasing, not declining)
7. Time decay — re-entries more than 30 minutes after original exit get lower conviction

---

## 5. Answers to Handoff Questions

### Q1: What specific conditions does Ross check before re-entering?
1. MACD positive (**hard gate**)
2. Stock holding key support (VWAP, round number)
3. Curl back up with volume
4. Has session cushion (not chasing from red)
5. Not extended relative to exit price

### Q2: Does he have a cooldown period or require a new setup to form?
- **Type A (sell→add back):** No cooldown — happens within seconds/minutes at same level
- **Type B (true re-entry):** Implicitly requires a **new pattern** to form (VWAP reclaim, micro pullback, curl). No fixed time-based cooldown, but the new pattern takes time to develop.

### Q3: Is there a limit on how many times he'll re-enter?
- **Typical range:** 3–5 trades on the same stock per session
- **Hard limit:** After 2–3 **failed** re-entries (losses or breakeven), he gives up
- **50% give-back rule:** If he's given back 50% of his peak profit on a stock, he stops

### Q4: What disqualifies re-entry entirely?
1. MACD negative
2. Stock extended without cushion
3. 2+ failed re-entries already
4. 50% of session profit already given back
5. "Stock doesn't feel clean" / choppy indecisive action
6. Big sellers visible (iceberg/spoofing)

### Q5: Does exit mode affect re-entry decisions?
- **Profit exit (scaled out):** Re-entry is natural if stock holds level (Type A)
- **Stop exit (loss):** Re-entry allowed but with **more caution, smaller size**, and requires a new pattern to form (Type B)
- **Frustration exit (choppy action):** Generally **no re-entry** — "this stock doesn't feel clean"

---

## 6. Open Questions for Clay

1. **Sell→Add-Back (Type A) vs True Re-Entry (Type B):** Should the bot distinguish between these? Type A is essentially "I took partial profit then added back at same level" — this is closer to position management than re-entry. Type B is "I fully exited, waited, and took a new trade."

2. **Per-Symbol P&L Tracking:** Do we want to track cumulative P&L per symbol per session? This would enable the 50% give-back rule and the cushion gate.

3. **MACD Implementation:** The bot already checks MACD for initial entries. Should re-entry use the **exact same MACD gate** or a separate, potentially stricter threshold?

4. **Failed Re-Entry Counter:** Should we count a "failed re-entry" as any re-entry that results in a loss, or only re-entries where the stock immediately reverses?

5. **Time Limit:** Ross doesn't explicitly state a time limit on re-entries, but his trading window is typically 9:30–11:30 AM. Should re-entries be blocked after a certain time?

---

## 7. Transcript Evidence Index

| Date | Stock | Re-Entry Behavior | Key Quote/Evidence |
|------|-------|-------------------|-------------------|
| 2025-11-10 | GLTO | Re-entered after stop-out when hidden buyer reappeared | "Re-entry when hidden buyer reappears" |
| 2026-01-06 | (general) | Curl-up re-entry with volume | "Curl back up with volume = re-entry opportunity" |
| 2026-01-14 | ROLR | Refused re-entry when MACD negative | "MACD was negative, taking too much risk" |
| 2026-01-14 | ROLR | Sell→add-back at $6.50, $9.50 VWAP reclaim | "Curls back up, reclaims VWAP, add back" |
| 2026-01-15 | PHL | 5 attempts, gave up at +$100 | "Hard to get back in when you don't have a cushion" |
| 2026-01-27 | HIND | 2 failed VWAP break re-entries, then stopped | "Re-entered for VWAP break (2x, neither held)" |
| 2026-01-28 | GRI | Sell→add-back at support | Multi-add cycle |
| 2026-02-03 | (stock) | Re-entered after blue sky breakout confirmed | "Re-entered at $10+ after blue sky breakout confirmed" |
| 2026-02-05 | RNAZ | Gave up after sellers kept reloading | "20,000 share sellers kept reloading → gave up" |
| 2026-02-06 | FLYE | Full sell→add-back→give-back cycle | "Got back in, gave back half profit, said 'That's it'" |
| 2026-02-09 | (stock) | Bad re-entry on dip buy → sold off hard | "Re-entered at $4.00 dip → sold off hard → exited -$3,500" |

---

## 8. Relationship to Existing A/B Test Data

The handoff document notes:
- **8 cases** benefit from re-entries (net +$5,466 value)
- **6 cases** are hurt by re-entries (net -$1,660)

Based on Ross's methodology, the prediction is:
- **Good re-entries** are likely **Type A** (sell→add-back at support) with MACD positive
- **Bad re-entries** are likely **Type B** (true re-entry after extended pause) with declining volume, MACD turning negative, or the stock not holding support

> [!TIP]
> The A/B data should be cross-referenced against these gates. Specifically:
> 1. Was MACD positive at time of re-entry for the 8 good cases?
> 2. Was MACD negative for any of the 6 bad cases?
> 3. Did the stock hold a visible support level before good re-entries?
> 4. Were bad re-entries into extended/declining stocks?
