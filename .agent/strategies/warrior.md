# Ross Cameron (Warrior Trading) Strategy

> **Source**: 30+ daily recap transcripts, Jan–Feb 2026  
> **Bot**: Warrior  
> **Status**: Research-verified, pending Clay approval

---

## 1. Stock Selection — The Five Pillars

Ross explicitly references "five pillars of stock selection" across many recaps. A stock must meet most/all to qualify as an A-quality setup:

| # | Pillar | Criteria |
|---|--------|----------|
| 1 | **Price** | Preferred $4–$20 range. Avoids <$1 ("too cheap") and >$25 ("too expensive, can't manage risk"). Will trade outside range if other factors are very strong. |
| 2 | **Float** | Low float preferred. Sub-1M ideal. Sub-5M strong. >10M gets "thickly traded" label. >50M = "practically Bank of America" — skip. |
| 3 | **Rate of Change** | Fast price movement. "From $4 to $8 in 20 seconds" = exciting. Slow grinders = skip. |
| 4 | **News Catalyst** | Breaking news strongly preferred. No-news = "B-quality" (4/5 pillars). Specific catalysts valued: partnerships, FDA data, prediction markets, crypto treasury. Private placements can be bullish. |
| 5 | **Daily Chart / Technical Setup** | Recent reverse split with room to 200 MA. Blue sky (all-time highs). No heavy overhead supply. Clean daily without excessive red candle history. |

### Disqualifiers (Hard Skips)

- **Easy to borrow** + no news = guaranteed fade
- **Huge spread** (50¢–$1) = untradeable
- **Too thickly traded** (volume >> float by absurd amounts) = tug-of-war, grinder
- **Round-trip history** — if the ticker has popped and reversed multiple times recently, skip
- **Sector skepticism** — some sectors get lower conviction (e.g., "cannabis, not interested")
- **Charles Schwab blocked** — international stocks often restricted (Hong Kong, Israeli, Singapore, UAE)

### Bonus Signals (Increase Conviction)

- **Hard to borrow** (locate required) = shorts will cover = bullish
- **Recent reverse split** = company wants stock to run for liquidity/offering
- **Blue sky setup** = no overhead resistance
- **Scanner audio alert** = obvious to many traders = volume confirmation

---

## 2. Entry Rules

### 2.1 Primary Entry: First Pullback on Breaking News

> "My focus right now is catalyst-driven. Wait for a stock to hit the scanners, try to understand the catalyst, then jump on the first pullback."

**Sequence:**
1. Stock hits scanner with audio alert (ding ding ding)
2. Click ticker → chart loads → check news
3. Pull up Level 2 → check spread (bid/ask)
4. Hand on hotkey (Shift+1/2/3) → punch it

**Entry Triggers:**
- Break of half-dollar or whole-dollar level ($5.00, $5.50, $6.00)
- Break of VWAP (Volume Weighted Average Price)
- Break of pre-market high
- Break of high-of-day
- Micro pullback → curl back up (10-second chart)
- Inverted head-and-shoulders pattern on intraday

### 2.2 Entry Sizing: Starter → Full Position

| Phase | Description | Size |
|-------|-------------|------|
| **Starter** | Breaking the ice, testing the waters | ~5,000 shares |
| **Full position** | After confirmation (price holds, starts moving) | 10,000–15,000 shares |
| **Max position** | High conviction, all buying power | 20,000–50,000+ shares |

> "I break the ice with smaller positions. I'm nervous... so I'm just being cautious."
> "Once I have a cushion and I'm doing well, then I'm getting aggressive."

### 2.3 Adding to Winners

Ross adds on strength, never on weakness (with one exception: dip-buying the first pullback after an initial move).

**Add Triggers:**
- Every 50¢ higher ($6.00 → $6.50 → $7.00)
- Break of key levels (half-dollar, whole-dollar)
- Break of high-of-day
- After taking partial profit and stock holds the level

**Add Rules:**
- Each add raises cost basis — he is aware of this risk
- Adds are progressively smaller if price is getting expensive
- Never adds on weakness / never averages down
- Maximum position limited by buying power

---

## 3. Trade Management — Exit & Scaling

### 3.1 The "Take Profit → Add Back" Cycle

This is Ross's signature pattern and the most important behavioral model for the bot:

```
Entry at $6.00 (starter)
  → Add at $6.50 (full position)
  → Squeeze to $7.00 → TAKE PROFIT (10,000-15,000 shares off)
  → Stock holds $7.00 → ADD BACK at $7.01-$7.25
  → Squeeze to $7.50 → TAKE PROFIT (partial)
  → Stock holds → ADD BACK at $7.55
  → Squeeze to $8.00 → TAKE PROFIT (round number)
  → Repeat until failure...
```

> "I take the 10,000-15,000 shares off the table for $3,000 winner. And then it holds seven and I add back at 701 715 725. I take profit at 750. I add back at 755. It goes up to 8. I take profit at 8."

**Key: He is ALWAYS scaling in and out. Not a single exit event.**

### 3.2 Profit-Taking Targets

Ross does NOT use fixed percentage targets. He uses **structural levels**:

| Target Type | Examples | Notes |
|-------------|----------|-------|
| **Round numbers** | $7.00, $8.00, $10.00, $12.00 | Primary target type |
| **Half-dollars** | $7.50, $8.50 | Secondary targets |
| **Resistance levels** | 200 MA, double-top, pre-market high | Technical targets |
| **"Up $1/share"** | When up $1+ from avg entry | "Scale out on strength - take profit when up $1+/share" |
| **High-of-day retest** | Previous intraday peak | Often takes partial here |

### 3.3 Full Exit Triggers

Ross exits entirely (sells remaining position) on:

| Signal | Description |
|--------|-------------|
| **VWAP loss** | Falls below VWAP and can't reclaim |
| **High-volume red candles** | Multiple large-body red candles = sellers in control |
| **MACD goes negative** | Technical weakness confirmed |
| **Big seller on Level 2** | Large ask orders that keep reloading (20,000+ shares) |
| **Can't break key level** | Double-top rejection, resistance wall |
| **Spread widens** | Liquidity drying up |
| **Topping tails** | Multiple candles with upper wicks = rejection |
| **Tweezer top** | Two topping tail candles = reversal pattern |
| **Round-trip fear** | Stock has given up 50%+ of move |

### 3.4 "Give Back" Tolerance

Ross accepts giving back 10–25% off peak P&L before stopping:

> "Peaked at 22,000 on the day and I'm finishing at 20,000 — down 10% off my highs."
> "Gave back 25% off the top... I'm taking my hands off the keyboard."
> "Was up 13,000... gave back half my profit. I said 'That's it.'"

**Rules:**
- 10% give-back = "acceptable, means I pushed it"
- 25% give-back = "flew too close to the sun, stopping now"
- 50% give-back = "that's it, done for the day"

---

## 4. Re-Entry Logic

Ross frequently re-enters the same stock after exiting. This is a critical pattern:

### 4.1 Re-Entry Conditions

- Stock holds a key level after his exit (e.g., holds $5.00 support)
- VWAP reclaim (breaks back above VWAP)
- Micro pullback forms and curls back up
- New high-of-day attempt
- Inverted head-and-shoulders on intraday

### 4.2 Re-Entry Sizing

- Usually **smaller** than initial position
- Building back up if it works
- More cautious on re-entries after a failed first attempt

### 4.3 Re-Entry Limits

- Typically 3–5 trades on same stock per session
- After 2+ failed re-entries: "gave up on this one"
- If stock goes below VWAP with MACD negative: "I guess it's done"

---

## 5. Base Hit vs. Home Run Framework

This is the most important strategic decision Ross makes daily:

### Base Hit Mode (Default)

> "Base hits absolutely pay the bills. I'm grateful for the base hits."
> "My average winners are only about 18 cents per share."

- Get in, take profit quickly (average hold: ~2 minutes)
- Scale in and out at half-dollar/whole-dollar levels
- Don't overstay
- 10–50¢ per share target
- Multiple trips in same stock = multiple base hits

### Home Run Mode (Hot Market Only)

> "Once it curled for that second move higher, I used all my buying power."
> "I added and I was looking for the squeeze through high of day."

- Hold through pullbacks
- Keep adding on strength
- Target multi-dollar moves ($2–$5+/share)
- Only when market is HOT and stock has strong catalyst

### When to Switch Modes

| Condition | Mode |
|-----------|------|
| Cold market, Bitcoin down, few scanners | Base Hit |
| Stock has no news | Base Hit |
| Red on the day, need to recover | Base Hit |
| Breaking news, stock squeezing 100%+ | Home Run |
| Multiple stocks up 100%+ on scanners | Home Run |
| Already have cushion on the day | Home Run |
| Wednesday (statistically best day) | Lean Home Run |

### The Danger

> "I was standing at home plate ready to hit a home run... I think that's one of the biggest dangers. When you start wanting to hit home runs, you get strikeouts."

---

## 6. Risk Management

### 6.1 Daily P&L Goals

| Market Temp | Daily Goal | Note |
|-------------|-----------|------|
| Cold | $5,000 | "Even $2,000–$3,000 is acceptable" |
| Hot | $20,000 | "Keeps the 9-to-5 away" |

### 6.2 Max Daily Loss / Stop Rules

- **Red day rule**: Walk away early when it's not working
- Last trade typically before 9:00 AM on red days
- "Don't trade longer on a day that's not going well"
- "No trade days are better than red days"

### 6.3 Position Sizing by Conviction

| Conviction | Size Example | When |
|------------|-------------|------|
| Low (breaking ice) | 3,000–5,000 shares | First trade of day, uncertain market |
| Medium | 10,000–15,000 shares | Good setup, some cushion |
| High | 20,000–45,000 shares | A+ setup, hot market, have cushion |
| Max (all-in) | All buying power | Once/twice per month on best setup |

### 6.4 "Cushion" Trading Psychology

This is Ross's core risk philosophy:

```
1. Start day with small position (break the ice)
2. Build cushion ($2,000–$5,000 green)
3. Now size up on next setup
4. If cushion disappears → reduce size
5. If deep green → can be aggressive
```

> "I'm not even trying to break the ice on something and build a cushion if I don't think it has the potential to really do something impressive."

---

## 7. Market Temperature Assessment

Ross explicitly classifies market conditions daily:

### Cold Market Indicators
- Leading gainer only up 40–50%
- Few stocks on scanner
- No fresh news catalysts
- Bitcoin down significantly
- Stocks popping and immediately reversing
- "Crickets" after initial pops
- Shorts more aggressive
- Spoofing algorithms visible

### Hot Market Indicators
- Multiple stocks up 100%+ on scanners
- 3+ stocks with >100M shares volume
- Stocks holding after initial squeeze (not round-tripping)
- Fresh catalyst/theme in play (prediction markets, crypto treasury, AI)
- Shorts afraid to touch stocks
- Parabolic moves of 300%+ happening

### Behavioral Adjustments

| Cold Market | Hot Market |
|-------------|-----------|
| Size down | Size up aggressively |
| Base hits only | Push for home runs |
| 1–2 trades max | 5–10+ trades |
| Walk away early | Stay aggressive, dig deep |
| Avoid high-price stocks | Trade the most obvious stock |
| Skip stocks without news | Any momentum works |
| Tighter stops | Give more room |

---

## 8. Intraday Technical Indicators

### Used (with caveats)
| Indicator | How Used |
|-----------|----------|
| **VWAP** | Primary bias indicator. Above = bullish, below = bearish. Break of VWAP = entry trigger. |
| **MACD** | Confirmation only. "MACD goes negative" = caution / potential exit. |
| **Level 2 / Order Book** | Primary tool for reading supply/demand. Watches for big buyers on bid, big sellers on ask. |
| **10-second chart** | Entry timing. Micro pullback patterns. |
| **1-minute chart** | Intraday structure. Base patterns, candle patterns. |
| **5-minute chart** | Broader intraday context. |
| **Daily chart** | Float rotation, 200 MA position, recent history. |
| **Volume** | Relative volume vs 50-day average. Confirms interest. |
| **Spreads** | Tight = good liquidity. Wide = dangerous. |

### NOT Used
- RSI
- EMA crossovers  
- Bollinger Bands
- Fibonacci
- Any "indicator-based" system

---

## 9. Key Behavioral Patterns for Bot Implementation

### 9.1 Selling Behavior
1. **Never sells everything at once** — always partial exits
2. **Sells into strength** (at round numbers, resistance)
3. **Adds back after selling** if stock holds the level
4. **Gets out quickly** when thesis breaks (VWAP loss, big sellers)

### 9.2 Stop Behavior
- **No fixed stop-loss percentage** — uses technical levels
- **Mental stop** at entry candle low or support level
- **Hard stop** = account loss limit for the day
- **Never holds overnight** — pure intraday

### 9.3 Time-Based Behavior
| Time (ET) | Behavior |
|-----------|----------|
| 4:00–6:00 AM | Scan pre-market, check gaps. Building watchlist. |
| 6:00–7:00 AM | **Active trading possible.** Ross has traded as early as 6 AM on high-conviction setups. |
| 7:00–9:00 AM | **Prime trading window**. Most profit here. Recorded entries as early as 07:00 (BNRG, ROLR). |
| 9:00–9:30 AM | Caution. Often stops trading. "Am I done?" |
| 9:30 AM+ | Open bell. Rarely trades this session. |

### 9.4 The "All or Nothing" Approach
> "I'm either all in or I'm on the sidelines."
> "If I don't love it, I'm not going in. But if I love it, I'm going all in."

---

## 10. Common Mistakes (Self-Identified)

| Mistake | Quote |
|---------|-------|
| Adding too high without taking profit | "Added from $10–$10.80 — too aggressive, didn't take profit" |
| Trying for home run on first trade | "Diverted from typical base hit mentality" |
| Not selling at break-even on losing trade | "Was up $6,000, didn't take profit" |
| Overtrading on cold day | "This was not a day to overtrade. This was a day to take shelter." |
| Chasing after missing initial move | "Don't chase it. Don't chase it. The spreads are too big." |
| Trading without news | "No news... that's a risk factor" |
| FOMO on expensive stocks | "I can't manage my risk at $27–$30/share" |

---

## 11. Implementation Notes for Warrior Bot

### Critical Rules (Non-Negotiable)
1. **Catalyst required** for A-quality entries
2. **Never average down** — only add on strength
3. **Partial exits** at structural levels (not percentage-based)
4. **Re-entry allowed** if stock proves itself again
5. **Market temperature** should modulate all sizing
6. **Base hit default** — home run only in hot conditions
7. **Walk away mechanism** — stop trading after X% give-back from peak

### Parameters to Tune
- Starter size vs full position ratio
- Half-dollar/whole-dollar add levels
- Give-back tolerance (10%/25%/50% thresholds)
- Re-entry count limits
- VWAP break exit sensitivity
- Time-of-day aggressiveness curve

### What the Bot Currently Lacks (vs Ross)
1. **"Add back" after profit exit** — the cycle of sell → add back → sell
2. **Market temperature awareness** — adjusting all parameters
3. **Level 2 / order flow reading** — detecting big sellers
4. **Multiple trades on same stock** — re-entry capability
5. **Conviction scaling** — sizing based on setup quality
6. **"Cushion" awareness** — using day P&L to modulate risk
