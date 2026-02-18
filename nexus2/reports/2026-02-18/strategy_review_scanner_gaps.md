# Strategy Review: Scanner Gaps

> **Methodology**: Ross Cameron / Warrior Trading
> **Reviewed by**: Strategy Expert Agent
> **Date**: 2026-02-18
> **Sources**: `.agent/strategies/warrior.md`, Ross transcripts (Jan–Feb 2026), `CHART_PATTERNS.md`, `ROSS_RULES_EXTRACTION.md`

---

## BNRG — VWAP Reclaim (Gap = -7%, Ross P&L +$271)

### Methodology Evidence

**1. Ross's own description of the BNRG trade (Feb 11 transcript):**

> "about 6:45 I'm sitting down and I saw that it was underneath the volume weight average price. And so initially my bias on this was, you know, that's a little bit weak, but it was our it was definitely our most obvious stock. And with that low float, you know, I kind of thought, look, **if this can reclaim VWAP, we get back over four, we're going right back to 450 and this could work.** So, uh, so that's kind of how I was looking at it. And I ended up taking a trade, uh, right here, right at 7 a.m."

> "I jumped into that and jumped out for a profit of $271.74. So you could more or less say that was a **break even trade** for me. That's a very small trade."

**Key context**: Ross himself describes this as a tepid, cautious trade — "break even" in his assessment. It was the only stock available on a very cold day ("this is about as cold as it gets"). He was not enthusiastic about it.

**2. VWAP reclaim is a documented Ross pattern:**

- `warrior.md` Section 4.1 (Re-Entry Conditions): "**VWAP reclaim** (breaks back above VWAP)" — listed as a valid re-entry signal
- `warrior.md` Section 2.1 (Entry Triggers): "**Break of VWAP** (Volume Weighted Average Price)" — listed as a primary entry trigger
- `CHART_PATTERNS.md`: "**First Pullback after VWAP Break**" and "**VWAP Breakout**" — documented chart patterns
- `ROSS_RULES_EXTRACTION.md` Section 3: "**VWAP Break** — Stock consolidates below VWAP, then breaks above with momentum" — documented entry pattern
- Multiple transcripts: VWAP reclaim referenced in Jan 14 (SOFI add at $9.50), Feb 6 (VWAP reclaim entry), and others

**3. VWAP reclaim is NOT a gap-up setup:**

- `IMPLEMENTATION_AUDIT.md` explicitly notes: "VWAP reclaim deferred to adds feature" — the implementation team already recognized this is a separate pattern
- The BNRG trade had a **negative gap** (-7%). Ross did not expect or require a gap. He expected a **VWAP reclaim** on a stock that was already trading below its previous close.

**4. Ross's quality assessment of BNRG:**

From the Feb 11 transcript, Ross noted BNRG met several pillars:
- ✅ Sub-1M float
- ✅ Recent reverse split
- ✅ Room to 200 MA
- ⚠️ Israeli company (sector skepticism, but not a hard skip)
- ❌ "Energy and renewable energy not my favorite sector"
- ❌ Below VWAP at 6:45 (weak start)

Ross treated this as a **B-quality / cold-market necessity trade**, not an A-quality setup.

### Recommendation: **FILTER_TEST** (near-term) + **NEEDS_RESEARCH** (long-term)

**Near-term**: The diagnosis report's Option 1 is correct. The gap-up scanner is working as designed. BNRG should be excluded from `get_ross_traded_winners()` by filtering out `setup_type: vwap_reclaim` test cases. The gap-up scanner should NOT be expected to catch VWAP reclaim setups.

**Long-term**: VWAP reclaim is a documented Ross Cameron pattern with multiple transcript references. It belongs on the roadmap as a separate scanner module — and in fact is **already acknowledged** in `IMPLEMENTATION_AUDIT.md` as "VWAP reclaim deferred to adds feature." When implemented, it would need:

- Stock already on watchlist (detected by gap scanner or other means)
- Trading below VWAP in pre-market
- Break above VWAP with volume as trigger
- Standard pillar checks (float, news, etc.) still apply

> [!IMPORTANT]
> **This should NOT be a high-priority item.** Ross himself called this a "break even trade" on the coldest possible market day. VWAP reclaim trades from a negative gap are low-conviction, cold-market necessity plays, not the bot's core edge.

**Confidence**: HIGH — The evidence is unambiguous. The scanner is correct; the test case is testing the wrong capability.

---

## VHUB — Icebreaker / Sub-Threshold Gap (Gap = 3.3%, Min = 4%, Ross P&L +$1,600)

### Methodology Evidence

**1. Ross's own description of the VHUB trade (Feb 17 transcript):**

> "7:38, 8:39. I'm just sitting here waiting for breaking news. And we had this stock VHub that came out with a headline and started to pop up right here. And I was a little unsure about it. The float was a little higher, but I noticed **it's a blue sky setup. Recent IPO above, well, it's not a blue sky yet, but it is a recent IPO with blue sky above 40.**"

> "initially I was like, I don't know, the float's a little higher, price is a little lower. It's not really my wheelhouse."

> "I decided to punch it. I got in at about 333. I was looking for the break through 345 and then 350. And with 20,000 shares, I was in, I was out, and I locked up $1600. **Was it a home run? No, it wasn't.**"

> "that was my **icebreaker** and it was not a big winner. So now I've got to take it slow."

**Key context**: Ross explicitly used the word "icebreaker" — this is his term for a small, cautious first trade of the day to test the waters. He was not enthusiastic. He took 20K shares for a quick $1,600 (8 cents/share profit — below his stated 18 cent average).

**2. Does Ross document exceptions to the 4% gap minimum?**

The 4% gap minimum comes from `warrior.md` Section 1 (Rate of Change pillar): "Fast price movement." The actual documented pillar in `warrior.md` says:

> | 3 | **Rate of Change** | Fast price movement. "From $4 to $8 in 20 seconds" = exciting. Slow grinders = skip. |

The 4% gap threshold is a **bot implementation parameter**, not a Ross-stated hard rule. Ross does not state a specific percentage for minimum gap in the transcripts I reviewed. His actual methodology is more nuanced:

- `warrior.md` Section 1 states: "A stock must meet **most/all** to qualify as an A-quality setup" — not ALL, most/all
- `ROSS_RULES_EXTRACTION.md` Section 9: "Hot market | More aggressive, **4/5 pillars OK**" — Ross explicitly drops requirements in hot markets
- Ross's comment about VHUB: "It's not really my wheelhouse" — he was aware it was sub-standard but took it anyway

**3. "Icebreaker" is a recognized Ross concept:**

- `ROSS_RULES_EXTRACTION.md` Section 7 documents an **ICEBREAKER EXCEPTION** for Chinese stocks: "Score ≥10 = pass with 50% size (Jan 20 TWWG)"
- `warrior.md` Section 5 (Base Hit Mode): Ross's entire cold-market strategy revolves around cautious "breaking the ice" trades
- Feb 17 transcript: Ross explicitly calls VHUB his "icebreaker"
- `warrior.md` Section 6.4: The "Cushion" Trading Psychology describes the icebreaker → cushion → aggressive cycle

**4. Was the 3.3% gap the real issue, or was it `dynamic_score`?**

Per the VHUB investigation (Feb 17 handoff), the bot actually **detected** VHUB as a valid BULL_FLAG with score 0.584 (above the 0.4 threshold). The bot rejected it because of the **TOP_3 concentration filter**, not the gap check. VHUB's `dynamic_score=2` vs LFS's `dynamic_score=11` caused it to be ranked 11th.

However, the gap check ALSO would have blocked VHUB since 3.3% < 4.0% at the scanner level. So both issues need addressing.

**5. What Ross actually valued in VHUB:**

| Factor | VHUB | In Bot? | Detail |
|--------|------|---------|--------|
| News catalyst (headline at 7:30) | ✅ | ✅ Scored | `catalyst_strength` in `score_pattern()` (15% weight) |
| Blue sky above $40 | ✅ | ✅ Scored | `blue_sky_pct` adds +0.10 bonus when ≤5% of 52w high (`warrior_entry_scoring.py:120`) |
| Recent IPO | ✅ | ✅ Scored | `get_ipo_score_boost()` adds +1 to +3 to quality in `unified_scanner.py:404-410` |
| Only interesting stock on cold day | ✅ | ❌ Missing | No market temperature awareness |

> [!WARNING]
> **The real problem**: IPO boost, blue sky bonus, and catalyst scoring all exist — but they never get a chance to run for VHUB. The **hard gap floor** (4.0%) rejects the stock at the scanner's `_calculate_gap_pillar` (line 1596) before entry scoring is ever invoked. These quality factors only matter for stocks that already pass the gap check.

Ross avoided RIME ("crowded/thickly traded"), SUNE ("thickly traded"), GXAI ("thickly traded") — his selectivity was based on **avoiding thick stocks**, not on gap percentage.

### Recommendation: **ADD_EXEMPTION** (with caveats)

> [!WARNING]
> I am recommending a mechanism but **I cannot invent the thresholds**. Ross does not state specific numbers for when to override the gap minimum. The following framework is grounded in documented behavior but the specific parameters require Clay's judgment.

**Proposed "Icebreaker Exemption" Framework:**

1. **When**: Gap is between 3.0% and 4.0% (just below threshold)
2. **Requires**: Exceptionally high quality on other pillars:
   - News catalyst (required — Ross won't icebreak without news)
   - Low float (sub-5M — Ross values squeeze potential)
   - Blue sky / clean daily chart
3. **Effect**: Allow the stock into the scanner pipeline at reduced conviction
4. **Sizing**: Icebreaker size (starter position), not full position

**What I can document from Ross's behavior:**
- Ross states he needs 4-5 pillars for A-quality, but will trade 3-4 pillars in cold markets
- The icebreaker concept is documented — cautious entry, quick exit, testing the waters
- Ross's VHUB trade was exactly this: in at $3.33, out quickly, $1,600 profit, 8 cents/share
- The trade was NOT a home run attempt — it was a cold-market base hit

**What I CANNOT determine from documentation:**
- The exact gap floor for the exemption (3.0%? 2.5%? context-dependent?)
- The exact quality score threshold to trigger the exemption
- Whether the icebreaker should be market-temperature-dependent (Ross's behavior suggests yes)
- How much this actually matters for profitability — $1,600 is a typical base hit, not transformative

> [!IMPORTANT]
> **Risk/reward consideration**: Lowering the gap floor from 4% to 3% would let in more noise (stocks with small gaps that fail). The VHUB result (+$1,600) is a single data point. The 4% floor exists because most sub-4% gaps don't produce tradeable moves. Clay should decide whether the marginal benefit of catching VHUB-type trades outweighs the false positive cost.

**Confidence**: MEDIUM — The icebreaker concept is documented, but specific thresholds are not. This requires a design decision from Clay.

---

## Timezone — `datetime.now()` Violations

### Trading Impact: **LOW** (but fix anyway)

**Violation 1 — `scan_diagnostic.py:740`**: Diagnostic output timestamp only. **NO trading impact.**

**Violation 2 — `catalyst_search_service.py:53`**: Cache loaded timestamp. **NO trading impact.** Cache staleness check would be off by timezone offset, but this only affects whether cached catalysts are re-fetched — it doesn't block or enable trades.

**Violation 3 — `warrior_scanner_service.py:513`**: Cache TTL check. **LOW trading impact.** Using naive `datetime.now()` instead of `now_et()` could cause cache TTL miscalculation during DST transitions (spring forward/fall back). In practice:
- Spring forward: Cache expires 1 hour early (harmless — just re-fetches)
- Fall back: Cache lives 1 hour too long (could serve stale scanner results for 1 extra hour during DST transition night, which is outside trading hours)

**Violation 4**: False positive. The actual code uses `now_utc()` correctly; the regex matched the comment text.

### Strategy Relevance

None of these affect Ross-methodology decision-making (entry triggers, stop logic, pillar checks). However, timezone discipline is a general engineering hygiene issue.

From `warrior.md` Section 9.3, time-based behavior is critical to Ross's strategy (6:00–9:30 AM ET trading window). Any code that touches time should use timezone-aware utilities to prevent subtle bugs.

### Recommendation: **FIX**

- Replace the 3 `datetime.now()` calls with `now_et()` from `nexus2.utils.time_utils`
- Fix the false positive regex or add an exclusion for comment text
- Safe to implement, no risk of trading impact

**Confidence**: HIGH — This is an infrastructure fix with no strategy trade-offs.

---

## Summary

| Issue | Scanner Correct? | Strategy Evidence | Recommendation | Priority |
|-------|-----------------|-------------------|----------------|----------|
| **BNRG** (VWAP reclaim) | ✅ Yes | VWAP reclaim is documented but distinct from gap-up | **FILTER_TEST** — exclude `vwap_reclaim` cases from gap scanner tests | Low |
| **VHUB** (3.3% gap) | ⚠️ Partially | Icebreaker exception is documented concept; specific thresholds are not | **ADD_EXEMPTION** — Clay decides gap floor and quality thresholds | Medium |
| **Timezone** | N/A | No trading logic impact | **FIX** — replace `datetime.now()` with `now_et()` | Low |

### Open Questions for Clay

1. **VHUB exemption**: Should the scanner have an icebreaker mode that lowers the gap floor (e.g., to 3.0%) when quality score is high? If yes, what quality factors should qualify?
2. **VWAP reclaim scanner**: Is building a separate VWAP reclaim scanner module a priority for the roadmap, or should it remain deferred? (Ross's BNRG trade was +$271 on a cold day — not a strong profitability argument.)
3. **Market temperature**: Both BNRG and VHUB were cold-market trades. Should the scanner parameters (gap threshold, pillar requirements) adjust based on market temperature? This is documented in Ross's methodology but not implemented.
