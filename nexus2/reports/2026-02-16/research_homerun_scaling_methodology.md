# Home Run Riding & Scaling Methodology — Ross Cameron Research

> **Purpose**: Ground the Warrior bot's exit/scaling logic in verified Ross Cameron methodology.  
> **Problem**: Bot captures ~13% of Ross's P&L. Primary gap: early exits on big winners.  
> **Sources**: `.agent/strategies/warrior.md`, 8+ transcript recaps (Jan–Feb 2026), `TECHNICAL_ANALYSIS.md`

---

## 1. Base Hit vs Home Run — Mode Selection

### Verified Rules

| Factor | Base Hit (Default) | Home Run (Hot Market Only) |
|--------|-------------------|---------------------------|
| **Market temp** | Cold / normal | Hot (3+ stocks >100%, high volume across scans) |
| **Catalyst quality** | Standard news | Strong thematic catalyst (prediction markets, AI, crypto treasury) |
| **Hold time** | ~2 min avg | Minutes to tens of minutes |
| **Target** | 10–50¢/share, structural levels | $2–$5+/share, multi-dollar moves |
| **Pullback tolerance** | Exit on first weakness | Hold through pullbacks, add on strength |
| **Give-back tolerance** | Minimal | Accepts giving back 10–25% off peak P&L |

> **Source**: `warrior.md` §Base Hit vs Home Run, confirmed by multiple transcripts

### How Ross Decides (Verified from Transcripts)

1. **Pre-session assessment**: Ross evaluates scanner quality at ~6:30 AM. If leading gainer is only 40–50%, he calls it "cold" and defaults to base hit. If multiple stocks are up 100%+ with 20M+ shares volume each, he calls it "hot."

2. **In-trade escalation**: Ross does NOT pre-decide home run mode. He starts with base hit mechanics (get in, take profit at levels) and **only escalates** when:
   - The stock moves 100%+ in minutes with parabolic momentum
   - Volume is sustained and increasing
   - Short sellers appear scared (not leaning in)
   - A thematic catalyst drives broad market interest
   - He has built a cushion of realized profit

3. **Key quote** (2026-01-14 ROLR $85K day): *"We've got parabolic momentum. We have a stock that just went up 100% in 2 minutes. This is incredible."* — He added aggressively through the entire move from $5 to $18+.

4. **Key quote** (TECHNICAL_ANALYSIS.md §Small Account): *"My biggest challenge will be to avoid the temptation to swing for home runs. Home runs = cost of base hits."*

### Decision Framework

```
START → Base Hit Mode (always)
  │
  ├─ Stock moves 50¢–$1? → Take profit at structural level, add back if holds
  │
  ├─ Stock moves $1–$2 rapidly? → Continue take profit → add back cycle
  │     └─ If parabolic + hot market + strong catalyst → ESCALATE to Home Run
  │           └─ Larger adds, hold longer, wider trail tolerance
  │
  └─ Stock stalls / spreads widen / heavy sellers? → EXIT, do not escalate
```

> [!IMPORTANT]
> Ross does NOT use a binary switch. He **always starts base hit** and conditionally escalates based on real-time price action + market context. The bot should mirror this by never pre-selecting home run mode.

---

## 2. The "Take Profit → Add Back" Cycle (Signature Pattern)

This is Ross's **primary scaling mechanism** and distinguishes his methodology from simple "buy and hold." It functions as both a scaling and risk management technique.

### Verified Pattern (Multiple Transcripts)

```
1. ENTRY at level (e.g., break of $6.00)
2. Stock moves to $7.00 → TAKE PROFIT (10-15K shares off)
3. Stock HOLDS $7.00 → ADD BACK at $7.01–$7.25
4. Stock moves to $7.50 → TAKE PROFIT (partial)
5. Stock HOLDS $7.50 → ADD BACK at $7.55
6. Stock moves to $8.00 → TAKE PROFIT (round number)
7. Repeat until move exhausts
```

### Evidence Table

| Date | Ticker | P&L | Cycle Description |
|------|--------|-----|-------------------|
| 2026-01-14 | ROLR | +$85K | Entry $5.17 → profit at $7 → add back $7.01–$7.25 → profit at $7.50 → add back $7.55 → profit at $8 → add $8.50, $9 → profit at $10.50, $12 → add through $13–$18 |
| 2026-01-20 | TWWG | +$20K | Entry at VWAP break → profit at $7 → add back → profit at $8 → add at $8.50 → profit at $9.20 → add at $9.50 → profit → gave back $3K off top |
| 2026-01-28 | GRI | +$33K | Entry $5.97 at break of $6 → profit at $7 (70¢/share, ~$7K) → add back at $7.01–$7.25 → profit at $7.40 → add at $8.50, $9 → every 50¢ adding → peaked $12, gave back ~25% |
| 2026-02-06 | FLY | +$5.5K | Entry $6.32 → profit at $7 (10-15K shares, ~$3K) → add back $7.01–$7.25 → profit at $7.50 → add back $7.55 → profit at $8 → add back → gave back half profit |
| 2026-02-11 | PRFX | +$6K | Entry $4.15–$4.50 → add at $5.70 → add at $6.50 → add at $7.82 → peak $8; tried to take profit, didn't fill → gave back significantly on rollover |

### Critical Rules

1. **Profit-taking levels are structural**: Half-dollars ($X.50) and whole dollars ($X.00), round numbers, resistance levels — **never percentage-based or R-multiple based**
2. **Add back ONLY if stock holds the level**: "It holds seven and I add back" — the stock must demonstrate support at the profit-taking level before re-entry
3. **Add back quickly**: Adds happen within seconds of the hold confirmation, not after lengthy consolidation
4. **Each cycle resets risk**: By taking profit first, Ross locks in gains. The add-back is a new risk unit with a tight stop at the level that just held
5. **Position size may decrease on adds**: As price increases, he can afford fewer shares with same capital

> [!IMPORTANT]
> The bot currently lacks this "add back" capability entirely. This is likely the **single largest contributor** to the P&L gap. After a profit exit, the bot treats the trade as complete rather than continuing to manage the same stock through the cycle.

---

## 3. Scaling Into Winners — Mechanics

### Entry Sizing (Verified)

| Phase | Size | Trigger |
|-------|------|---------|
| **Starter** | Small (e.g., 5K shares on $5-7 stock) | Initial entry, breaking ice |
| **Full position** | 10–15K shares via hotkey adds | Confirmation — stock moving, level breaking |
| **Max position** | All available buying power | Parabolic move, high conviction, hot market, cushion built |

### Add Triggers (Verified from Transcripts)

1. **Half-dollar / whole-dollar breaks**: "I added at $8.50, $9, every 50 cents I'm adding"
2. **VWAP reclaim**: "I got back in there for the break through VWAP"
3. **Micro-pullback hold**: "It dips down for a second, then curls back up — I add back"
4. **High-of-day break**: "Looking for the breakthrough, the high of day. This is a micro pullback."
5. **Resistance level breaks**: "I added for the break of resistance at $6.50"

### Add Sizing Rules

- **With cushion**: Larger adds, up to full buying power. *"I used all of the buying power that I had in my account and I was all in"* (ROLR)
- **Without cushion / early in day**: Smaller, cautious adds. *"I was breaking the ice with smaller positions. I was nervous."* (TWWG)
- **As price rises**: Mechanical constraint — fewer shares per add as price increases. *"At $18 a share, I couldn't really buy very many shares"*
- **In cold market**: Significantly reduced sizing. *"I'm sizing down. I'm being more conservative."*

### Number of Adds (Observed)

| Scenario | Typical # Adds | Example |
|----------|---------------|---------|
| Base hit (cold market) | 1–2 adds total | FLY: 2 add-back cycles |
| Normal day | 3–5 add-back cycles | TWWG: ~4 cycles |
| Home run (hot market) | 5–10+ cycles | ROLR: 8+ add/profit cycles across $5→$18 |
| Parabolic squeeze | Continuous adding every $0.50 | GRI: "Every 50 cents I'm adding" from $6→$12 |

---

## 4. Trailing & Profit Protection

### Ross Does NOT Use Traditional Trailing Stops

There is **no evidence** of Ross using:
- Percentage-based trailing stops
- ATR-based trailing stops  
- Moving average trails
- Fixed-distance trails

### What Ross Actually Does

1. **Level-based profit-taking**: Takes partials at structural levels (half/whole dollars)
2. **Re-entry with tight stops**: After taking profit, adds back ONLY if level holds — stop on the add is the level that just held
3. **MACD as trend filter**: "The MACD was negative... taking too much risk" — uses MACD cross as a reason NOT to re-enter, not as a trailing stop
4. **Visual / level-2 exits**: Heavy selling on tape, big sellers on ask, widening spreads → full exit
5. **Give-back tolerance**: Accepts 10–25% drawdown from peak unrealized P&L before walking away

### Full Exit Triggers (Verified)

| Trigger | Evidence |
|---------|----------|
| **High-volume red candles** | "Hard to ignore those high volume red candles" |
| **MACD goes negative** | "MACD goes negative. Not surprising" → stops adding |
| **Topping tails / tweezer tops** | "Two little topping tail candles. That's a tweezer top — a reversal indicator" |
| **Big sellers on Level 2** | "18,200 shares on the ask... creates perception of upside resistance" |
| **Widening spreads** | "The spread was 50 cents, even a dollar a share. I'm not touching it" |
| **Stock can't break key level** | "Pops up, doesn't work. Pops up again, doesn't work" → walks away |
| **Round-trip fear** | "I've given back 25% of my day... that's it" |

---

## 5. Disqualifiers — When NOT to Hold for Home Run

### Verified Disqualifiers

1. **Cold market**: "As cold as it gets... avoid higher price stocks... leave alone" → strict base hit only
2. **No fresh catalyst**: "No fresh news. I can't really trust it" → skip or small size
3. **Previous rejection on same ticker**: "It had popped up the other day. It didn't work. Why would it work today?" → skip
4. **Easy to borrow / short heavy**: "Easy to borrow, 35M share float. I think it's going to be choppy" → skip
5. **Shelf registration / offering risk**: Recognizes this as sell pressure but still trades the volatility — just with tighter exits
6. **Light volume / grinder**: "It felt too thickly traded, like it was just going to be too slow" → skip
7. **Extended stock (multiple green candles without pullback)**: "11 green candles in a row coming into this level. It hasn't even pulled back. I'm going to wait."
8. **Spoofing / predatory algorithms**: Big fake sell orders near ask suppress price → reduces conviction
9. **First trade of the day without cushion**: Does NOT swing for home run on first trade. Builds cushion first.

---

## 6. Give-Back Rules & Walk-Away Discipline

### Verified Pattern

| Rule | Evidence |
|------|----------|
| **Accept 10-25% give-back from peak** | "I gave back 25% of my day" → stopped trading |
| **Don't keep chasing after give-back** | "I didn't keep going back for it... which would have been a mistake" |
| **Platform-level walk-away** | After give-back, switches to teaching/classes or stops for the day |
| **Context-dependent tolerance** | In cold market: very tight give-back tolerance. In hot market: wider tolerance |

### P&L Curve Pattern (Verified from TWWG $20K day)

> "Small gains, small gains, and then a big jump and then a smaller jump and then a small jump and then a small draw down. $2,500 → $14,000 → $21,000 → $23,000 → $20,000. This is an acceptable way to walk away."

---

## 7. Key Implications for Bot Implementation

### What the Bot Should Do

| # | Capability | Priority | Notes |
|---|-----------|----------|-------|
| 1 | **"Add Back" after profit exit** | 🔴 Critical | Bot must be able to re-enter same stock after taking profit, if stock holds the level |
| 2 | **Structural profit-taking levels** | 🔴 Critical | $0.50 / $1.00 increments, not fixed ¢ targets or R-multiples |
| 3 | **Market temperature awareness** | 🟡 High | Cold → tight base hits. Hot → wider tolerance, bigger adds |
| 4 | **Cushion-aware sizing** | 🟡 High | Size up after building realized profit cushion |
| 5 | **MACD as re-entry gate** | 🟡 High | If MACD negative after big move, don't add back |
| 6 | **Give-back limit** | 🟢 Medium | Walk away after 20-25% unrealized draw-down from peak |
| 7 | **Escalation from base hit → home run** | 🟢 Medium | In-trade mode switch based on move magnitude + market temp |

### What the Bot Should NOT Do

- Pre-select home run mode before entry
- Use percentage-based or ATR-based trailing stops as primary exit
- Use fixed R-multiple targets (Ross never mentions R-multiples)
- Hold without partial profit-taking (Ross always takes partials at levels)
- Add on weakness / buy dips without level confirmation
- Continue adding once MACD is negative

---

## 8. Open Questions for Clay

1. **Add-back implementation scope**: The "take profit → add back" cycle is effectively a re-entry system. Should we treat it as an enhancement to the existing re-entry logic, or build a separate "scaling manager" that coordinates the cycle?

2. **Market temperature input**: Ross assesses this visually from scanners pre-market. Should we derive this from scanner data (e.g., count of gappers >50%, total pre-market volume) or make it a manual setting?

3. **Level 2 / tape reading**: Several exit triggers depend on Level 2 data (big sellers, widening spreads). Is this data available through current market data adapters, or is it out of scope?

4. **Give-back tolerance**: Should this be a global setting (e.g., 20% give-back from peak unrealized), or should it vary by market temperature / position size?

5. **Priority**: Given the bot currently lacks add-back capability entirely, should this be the next implementation focus before refining exit trailing logic?

---

## Source Citations

| Source | Location | Key Content |
|--------|----------|-------------|
| `warrior.md` | `.agent/strategies/warrior.md` | §Base Hit vs Home Run, §Trade Management, §Re-Entry Logic |
| 2026-01-14 ROLR | `2026-01-14_transcript_lneGXw0sxzo.md` | $85K day, full add cycle $5→$18, "all buying power" |
| 2026-01-20 TWWG | `2026-01-20_transcript_Uft2BuJpap8.md` | $20K day, 4 add-back cycles, acceptable give-back |
| 2026-01-28 GRI | `2026-01-28_transcript_WYB5jmTDBO4.md` | $33K day, "every 50¢ adding", 25% give-back limit |
| 2026-02-03 | `2026-02-03_transcript_eGai4gYuo0Y.md` | "Take profit, add back, take some" pattern |
| 2026-02-06 FLY | `2026-02-06_transcript_Z5D8nhEtzOo.md` | $5.5K day, 2 add-back cycles, cold market discipline |
| 2026-02-11 PRFX | `2026-02-11_transcript_HYK2eKkViJs.md` | $6K day, aggressive adding, cold market round-trip |
| TECHNICAL_ANALYSIS.md | `.agent/knowledge/warrior_trading/` | "Home runs = cost of base hits", 2:1 profit target |
