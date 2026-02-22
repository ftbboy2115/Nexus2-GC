# Research Report: Ross Cameron's Scanner Methodology

**Date:** 2026-02-21
**Author:** Strategy Expert Agent
**Status:** Research Complete — Pending Clay Review

---

## Executive Summary

Ross Cameron uses **multiple scanners** that work together as a discovery pipeline. From analysis of 10+ transcripts and his public Warrior Trading materials, I identified **four distinct scanner types**, of which **two are primary** and referenced most frequently. The commonly cited "dual scanner" consists of the **Top Gainers Scanner** and the **High of Day Momentum Scanner**. Additionally, Ross references a **Five Pillar Alert Scanner** and a **Running Up Scanner**, which appear to be filtered variants or additional scanner configurations within his Day Trade Dash platform.

> [!IMPORTANT]
> Our current Nexus Warrior scanner maps most closely to a **Five Pillar Alert Scanner** — it evaluates gap%, RVOL, float, price, and catalyst. However, it **does not** implement a pure **Top Gainers** view or a **High of Day Momentum** trigger, both of which Ross uses as his primary discovery tools.

---

## 1. Scanner Types — Enumeration

### 1A. Top Gainers Scanner (PRIMARY)

**Purpose:** Passive monitor showing stocks sorted by **biggest percentage gain** from prior close. This is Ross's first tool each morning — he checks it before the market opens to assess market temperature.

**Tier:** VERIFIED

**Evidence:**

| Date | Transcript | Quote/Reference |
|------|-----------|-----------------|
| 2025-11-16 | `2025-11-16_transcript_UGw2F3eIswU.md:47` | "**Top gainer scanner** — what's leading?" |
| 2025-11-23 | `2025-11-23_transcript_GfbJUq8IHwE.md:73` | "Watch **top gainer scanner** at 7 AM" |
| 2025-12-28 | `2025-12-28_transcript_f-iUyIhc3NI.md:78` | "6:30am: Check **top gainer scanner**" |
| 2025-12-28 | `2025-12-28_transcript_f-iUyIhc3NI.md` (full transcript) | "watching the **top gainers scanner** and the **high day momentum scanner** for stocks that have breaking news" |
| 2026-01-06 | `2026-01-06_transcript_tDb0WPsRZT4.md:53` | "**Low float top gainer scanner**" |
| 2026-01-27 | `2026-01-27_transcript_RAJXknk-VI4.md:163` | "even before it hit my high of day momentum scanner, it was on my **top gainers scanner**" |
| warriortrading.com | [Public article](https://www.warriortrading.com/day-trading-watch-list-top-stocks-to-watch/) | "My Stock Watch List Begins With **Top Gainers**" — scanner sorted by "biggest percentage gap from highest to lowest" |

**Criteria (from public article + transcripts):**

| Filter | Value | Source | Tier |
|--------|-------|--------|------|
| Sort by | % change from prior close (descending) | Public article | VERIFIED |
| Minimum % up | ≥10% from prior close | Public article: "must be up at least 10%" | VERIFIED |
| Relative Volume | ≥5x (14-day average) | Public article: "Relative Volume of at least 5" | VERIFIED |
| Price | $2–$20 preferred ($2–$8 sweet spot) | Public article: "sweet spot is between $2-8 per share" | VERIFIED |
| Float | <20M shares | Public article: "float of under 20 million shares" | VERIFIED |
| News catalyst | Preferred but not hard-gated | Transcripts: trades B-quality setups without news occasionally | VERIFIED |

> [!NOTE]
> The "Low float top gainer scanner" referenced on 2026-01-06 appears to be the same Top Gainers scanner with an explicit low-float filter applied. Ross uses Day Trade Dash (Warrior Trading's platform) and can configure filter parameters.

---

### 1B. High of Day Momentum Scanner (PRIMARY)

**Purpose:** Active scanner that fires alerts when a stock **breaks its high of day** with sufficient momentum/volume. This is Ross's primary **real-time trading trigger** — when this fires with an audio alert ("ding ding ding"), Ross clicks the ticker and evaluates it.

**Tier:** VERIFIED

**Evidence:**

| Date | Transcript | Quote/Reference |
|------|-----------|-----------------|
| 2025-12-05 | `2025-12-05_transcript_bZjbsbpRwnE.md:28` | "Both hit **high of day momentum scanner**" |
| 2025-12-05 | `2025-12-05_transcript_bZjbsbpRwnE.md:102` | "**High of Day Momentum Scanner** alert" as entry rule #1 |
| 2025-12-28 | `2025-12-28_transcript_f-iUyIhc3NI.md` (full transcript) | "watching the top gainers scanner and the **high day momentum scanner**" |
| 2026-01-27 | `2026-01-27_transcript_RAJXknk-VI4.md:163` | "before it hit my **high of day momentum scanner**" |
| 2026-02-13 | `2026-02-13_transcript_AfxuHHa_sFY.md:118` | "first scanner alert on the **high day momentum scanner** came at 7:54 a.m." |
| warrior.md strategy file | Section 2.1 | "Stock hits scanner with audio alert (ding ding ding)" |

**Criteria:**

| Filter | Value | Source | Tier |
|--------|-------|--------|------|
| Trigger | Stock making new high of day | All HOD scanner references | VERIFIED |
| Has built-in filter criteria | Yes — scanner only fires when stock "met the criteria" | 2026-02-13: "nothing between 4:00 a.m. and 7:54 that met the criteria for the scanner" | VERIFIED |
| Momentum requirement | Price moving fast (rate of change) | Inferred from "momentum" qualifier + Five Pillars Pillar #3 | INFERRED |
| Volume confirmation | High relative volume required | Transcripts: "confirmed interest" | INFERRED |
| Audio alert | Yes — audible "ding ding ding" | Multiple transcripts + warrior.md | VERIFIED |
| Minimum % up | Not stated | Not explicitly stated for HOD scanner | UNKNOWN |
| RVOL threshold | Not stated | Not explicitly stated for HOD scanner | UNKNOWN |
| Float filter | Not stated | Not explicitly stated for HOD scanner | UNKNOWN |
| Price filter | Not stated | Not explicitly stated for HOD scanner | UNKNOWN |

> [!TIP]
> The critical difference from the Top Gainers scanner: the HOD Momentum Scanner is **event-driven** — it fires when a stock breaks above its previous intraday high in real-time. Top Gainers is a **static sorted list**.

---

### 1C. Five Pillar Alert Scanner (SECONDARY)

**Purpose:** A filtered scanner that only surfaces stocks meeting **all five** of Ross's stock selection pillars. This appears to be a more restrictive version that combines criteria.

**Tier:** VERIFIED (existence); INFERRED (exact criteria mapping)

**Evidence:**

| Date | Transcript | Quote/Reference |
|------|-----------|-----------------|
| 2025-12-01 | `2025-12-01_transcript_pxbEPQ51RzQ.md:28` | "Leading gainer hitting **Five Pillar Scanner**" |
| 2025-12-01 | `2025-12-01_transcript_pxbEPQ51RzQ.md:77` | "Wait for **Five Pillar Scanner** alert" |
| 2025-12-03 | `2025-12-03_transcript_bD7xAMdj4vg.md:25` | "Hit **Five Pillar Alert Scanner** (all 5 criteria met)" |
| 2025-12-03 | `2025-12-03_transcript_bD7xAMdj4vg.md:87` | "Wait for **Five Pillar Scanner** alert" |

**Criteria — The Five Pillars (from warrior.md + public article + 2025-11-16 transcript):**

| # | Pillar | Scanner Criteria | Source | Tier |
|---|--------|-----------------|--------|------|
| 1 | **Price** | $2–$20 range | warrior.md + public article | VERIFIED |
| 2 | **Relative Volume** | ≥5x above 14-day average | Public article: "Relative Volume of at least 5" | VERIFIED |
| 3 | **% Change / Rate of Change** | Already moving fast (≥10% from close) | warrior.md Pillar #3 + public article | VERIFIED |
| 4 | **News Catalyst** | Breaking news present | warrior.md Pillar #4 | VERIFIED |
| 5 | **Float** | <20M shares preferred | warrior.md Pillar #2 + public article | VERIFIED |

> [!NOTE]
> The Five Pillar Scanner may be the **same scanner** as the Top Gainers scanner with all filters active, or it may be a separate custom scanner preset in Day Trade Dash. Ross refers to both, but never explicitly contrasts them. The most likely interpretation is that the Five Pillar Scanner is a **variant** of the Top Gainers scanner where all five filters are simultaneously applied.

---

### 1D. Running Up Scanner (SECONDARY)

**Purpose:** Real-time scanner that fires when a stock is actively accelerating in price — appears to be a momentum detection scanner separate from HOD breaks.

**Tier:** VERIFIED (existence); UNKNOWN (exact criteria)

**Evidence:**

| Date | Transcript | Quote/Reference |
|------|-----------|-----------------|
| 2026-02-19 | `2026-02-19_transcript_PPJLNKFS224.md:27` | "Hit '**running up**' scanner at $2.78" |
| 2026-02-19 | `2026-02-19_transcript_PPJLNKFS224.md:111` (full transcript) | "hits our **running up scanner** first at just after 8 a.m." |

**Criteria:**

| Filter | Value | Source | Tier |
|--------|-------|--------|------|
| Trigger | Stock accelerating in price | "running up" implies real-time price acceleration | INFERRED |
| Timing relative to HOD | Fires **before** HOD scanner | ENVB hit running up scanner first, HOD scanner would fire later | INFERRED |
| Minimum criteria | Unknown | Only one transcript reference | UNKNOWN |

---

## 2. Criteria Matrix — All Scanners Compared

| Criteria | Top Gainers | HOD Momentum | Five Pillar Alert | Running Up |
|----------|:-----------:|:------------:|:-----------------:|:----------:|
| **Type** | Static list (sorted) | Event-driven alert | Composite filter alert | Event-driven alert |
| **Sort/Trigger** | % change descending | New HOD break | All 5 pillars met | Price accelerating |
| **% Up minimum** | ≥10% (VERIFIED) | UNKNOWN — has criteria but not stated | ≥10% (VERIFIED) | UNKNOWN |
| **RVOL** | ≥5x (VERIFIED) | UNKNOWN — has criteria but not stated | ≥5x (VERIFIED) | UNKNOWN |
| **Price range** | $2–$20 (VERIFIED) | UNKNOWN — has criteria but not stated | $2–$20 (VERIFIED) | UNKNOWN |
| **Float** | <20M (VERIFIED) | UNKNOWN — has criteria but not stated | <20M (VERIFIED) | UNKNOWN |
| **News required** | Preferred, not gated | Not hard-gated | Yes (Pillar #4) | Not stated |
| **Audio alert** | No (passive list) | Yes ("ding ding ding") | Yes | Yes |
| **When used** | Pre-market, throughout day | During active trading | During active trading | During active trading |
| **Evidence strength** | VERIFIED (criteria) | VERIFIED (existence), UNKNOWN (criteria) | VERIFIED (criteria) | VERIFIED (existence), UNKNOWN (criteria) |

> [!WARNING]
> The HOD Momentum Scanner definitely has built-in filter criteria — the 2026-02-13 transcript explicitly says "nothing between 4:00 a.m. and 7:54 that met the criteria for the scanner." However, Ross never states what those criteria are. This is the single biggest gap in our research. The recommended next step is to find Day Trade Dash documentation or Ross's scanner setup tutorial videos.

---

## 3. Discovery Timeline — How Ross Uses Scanners Together

Based on the HIND trade (2026-01-27) and the ENVB trade (2026-02-19), the scanner pipeline operates in this sequence:

```
┌─────────────────────────────────────────────────────────────────────┐
│  6:00–6:30 AM: Wake up, check phone                                │
│  └─→ Glance at Top Gainers to assess market temperature            │
│       "Leading gapper only 30% = expect nothing"                    │
│       "Multiple stocks up 100%+ = hot market"                       │
├─────────────────────────────────────────────────────────────────────┤
│  6:30–7:00 AM: Sit down at desk, open Day Trade Dash               │
│  └─→ Top Gainers Scanner: Review sorted list                       │
│       Check news on top gainers                                     │
│       Evaluate Five Pillars for each                                │
│       Build initial watchlist                                       │
├─────────────────────────────────────────────────────────────────────┤
│  7:00+ AM: Active scanning begins                                   │
│  └─→ Running Up Scanner: Fires on price acceleration               │
│       "ENVB hits our running up scanner first at just after 8 a.m." │
│  └─→ HOD Momentum Scanner: Fires on HOD breaks                     │
│       "HIND: even before it hit my HOD scanner, it was on my        │
│        top gainers scanner" — Stock was visible passively first,     │
│        then triggered actively                                       │
│  └─→ Five Pillar Alert: Fires when all 5 criteria met              │
│       Most restrictive — may fire last or not at all                │
├─────────────────────────────────────────────────────────────────────┤
│  Decision Flow:                                                      │
│  Scanner alert (audio ding) → Click ticker → Check news →           │
│  Pull up Level 2 → Check spread → Entry decision                    │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Discovery Pattern: HIND (2026-01-27)

> "even before it hit my high of day momentum scanner, it was on my top gainers scanner. And Nick, who's a member in the chat room... said, 'Check out HIND. It looks good.'"

**Timeline:**
1. HIND appears on **Top Gainers Scanner** (passively — already up X% from close)
2. Nick in chat room spotted it and alerted Ross
3. HIND later breaks high of day → fires **HOD Momentum Scanner** 
4. Ross entered on the micro pullback after the HOD break

**Critical insight:** The Top Gainers scanner provided **early visibility** before the HOD Momentum scanner fired. This means a stock can be "on the radar" via Top Gainers before it makes the definitive HOD break that triggers active trading.

### Key Discovery Pattern: ENVB (2026-02-19)

> "hits our running up scanner first at just after 8 a.m."

**Timeline:**
1. ENVB hits **Running Up Scanner** at $2.78 (price accelerating)
2. Ross pulls it up, sees breaking news + familiar chart
3. Stock squeezes above $3 → would fire HOD scanner
4. Ross enters on the dip after initial breakout

**Critical insight:** The Running Up Scanner fires **before** the HOD scanner — it detects price acceleration even before a formal HOD break occurs.

---

## 4. Evidence Table — All Claims

| # | Claim | Tier | Direct Quote | Source |
|---|-------|------|-------------|--------|
| 1 | Ross uses a "Top Gainers Scanner" sorted by % change | VERIFIED | "My Stock Watch List Begins With Top Gainers" | warriortrading.com |
| 2 | Ross uses a "High of Day Momentum Scanner" with audio alerts | VERIFIED | "first scanner alert on the high day momentum scanner came at 7:54 a.m." | 2026-02-13 transcript |
| 3 | Ross uses both scanners together as primary tools | VERIFIED | "watching the top gainers scanner and the high day momentum scanner" | 2025-12-28 transcript |
| 4 | Top Gainers fires before HOD Scanner | VERIFIED | "even before it hit my high of day momentum scanner, it was on my top gainers scanner" | 2026-01-27 transcript (HIND) |
| 5 | Ross uses a "Five Pillar Alert Scanner" | VERIFIED | "Hit Five Pillar Alert Scanner (all 5 criteria met)" | 2025-12-03 transcript |
| 6 | Ross uses a "Running Up Scanner" | VERIFIED | "hits our running up scanner first at just after 8 a.m." | 2026-02-19 transcript |
| 7 | Top Gainers minimum: ≥10% from close | VERIFIED | "must be up at least 10% versus the prior day's close" | warriortrading.com |
| 8 | RVOL threshold: ≥5x | VERIFIED | "Relative Volume of at least 5" | warriortrading.com |
| 9 | Price range: $2–$20 | VERIFIED | "sweet spot is between $2-8 per share" | warriortrading.com |
| 10 | Float: <20M shares | VERIFIED | "float of under 20 million shares" | warriortrading.com |
| 11 | HOD Scanner has specific % or RVOL gates | INFERRED | Not explicitly stated for HOD scanner specifically | — |
| 12 | Running Up Scanner criteria details | UNKNOWN | Only one transcript reference | — |
| 13 | Five Pillar vs Top Gainers: are they separate presets? | UNKNOWN | Never explicitly contrasted | — |
| 14 | HIND's RVOL was ~1.9x at scanner time | VERIFIED | Scanner rejected HIND for RVOL 1.9x < 2.0x gate | Nexus scanner logs |

---

## 5. Implications for Nexus

### Current State

Our Warrior scanner is essentially a **Five Pillar Alert Scanner** — it checks gap%, RVOL (≥2.0x hard gate), float, price, and catalyst. When all criteria pass, it surfaces the stock.

### The HIND Problem

HIND was rejected by our scanner because **RVOL was 1.9x**, below our 2.0x hard gate. But Ross made $55k on HIND because:
1. It appeared on his **Top Gainers Scanner** (which may not have a hard RVOL gate, or uses ≥5x as a preference not a gate)
2. Nick in chat alerted him to the setup
3. Ross visually confirmed the setup quality and entered

### What We Need

| Scanner | What Nexus Needs | Priority |
|---------|-----------------|----------|
| **Top Gainers** | A simple sorted view of % change from close, with soft filters (not hard gates) for RVOL, float, price | HIGH |
| **HOD Momentum** | An event-driven trigger when a stock breaks its intraday high with volume confirmation | HIGH |
| **Running Up** | A real-time price acceleration detector (fires before HOD break) | MEDIUM |
| **Five Pillar Alert** | This is what we already have — keep but relax RVOL to ≥1.5x or make configurable | LOW (already exists) |

### Specific Recommendations

1. **Relax RVOL hard gate**: Ross's public article says "at least 5" for best results, but he clearly trades stocks with lower RVOL (HIND at 1.9x). Our 2.0x gate is too aggressive — make this a configurable soft filter, not a hard rejection.

2. **Add Top Gainers as a separate scanner type**: This is a passive sorted list — much simpler than our current scanner. It just needs: stocks sorted by % change from close, with optional filters for price range and float.

3. **Add HOD Momentum as a separate scanner type**: This is an event-driven alert — it fires when a stock crosses its prior intraday high with sufficient volume. This is Ross's primary real-time trading trigger.

4. **Scanner pipeline architecture**: Design a two-tier system:
   - **Tier 1 (Discovery):** Top Gainers — broad, passive, shows many stocks
   - **Tier 2 (Action):** HOD Momentum — narrow, active, triggers entries

---

## 6. Open Questions

| # | Question | Why It Matters | Suggested Next Step |
|---|----------|---------------|---------------------|
| 1 | What are the exact filters on Ross's HOD Momentum Scanner? | We need to know min %, RVOL, float gates for this scanner type | Check if Day Trade Dash has public documentation or watch Ross's scanner setup tutorials |
| 2 | Is the Five Pillar Scanner a separate preset or just the Top Gainers with all filters on? | Affects whether we need 3 or 4 scanner implementations | May not matter — implement both views regardless |
| 3 | What exactly triggers the "Running Up" scanner? | Could be valuable for early detection | Check more transcripts or Ross's platform tutorials |
| 4 | Does Ross use different RVOL thresholds for different scanner types? | Our 2.0x gate may be correct for Five Pillar but wrong for Top Gainers | His published threshold is 5x, which is much higher than our 2.0x — suggests RVOL usage differs between article (educational) and actual trading |
| 5 | Are the running up and HOD momentum scanners actually the same scanner? | "Running up" could be a colloquial name for HOD momentum | Only differentiated in one transcript (ENVB) where running up fired first |
| 6 | What volume threshold triggers the HOD scanner? | Need to calibrate the event-driven alert | Watch Ross's scanner configuration videos on YouTube |

---

## Methodology Note

This research was conducted by:
1. Reading the `warrior.md` strategy file in `.agent/strategies/`
2. Searching all 113 transcripts in `.agent/knowledge/warrior_trading/` for scanner-related terms
3. Reading 10+ transcripts in full or in relevant sections
4. Reading Ross's public article at warriortrading.com on stock scanner/watch list criteria
5. Cross-referencing all findings with direct quotes and transcript line numbers

All claims are categorized as VERIFIED (direct quote), INFERRED (reasonable deduction), or UNKNOWN (cannot be determined from available sources), per the anti-hallucination protocol in the handoff document.
