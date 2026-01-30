# Ross Cameron Trading Rules Extraction
## Warrior Bot Benchmarking Reference

**Source:** 60+ video transcripts (Nov 2025 - Jan 2026)  
**Purpose:** Verify Warrior bot implementation matches Ross's actual methodology  
**Last Updated:** 2026-01-30

---

## 1. Stock Selection (Five Pillars)

### Core Criteria
| Pillar | Requirement | Implementation Check |
|--------|-------------|---------------------|
| **Price** | $2-$20 | [ ] `price >= 2 AND price <= 20` |
| **Rate of Change** | Already up 10%+ | [ ] `change_percent >= 10` |
| **Relative Volume** | ≥5x average | [ ] `relative_volume >= 5` |
| **Float** | <20M shares | [ ] `float < 20_000_000` |
| **News/Catalyst** | Breaking news required | [ ] `has_catalyst = True` |

### Context Adjustments
| Condition | Adjustment | Source |
|-----------|------------|--------|
| Cold market | Float preference <5M | Nov 9 transcript |
| Small account ($2k) | Price preference $1.50-$5 | Nov 14, Nov 23 |
| Hot market | 4 of 5 pillars may work | Nov 17 transcript |
| Short squeeze hunt | Add short interest >20% | Nov 30 SMX profile |

---

## 2. Scanner Alert Priority

### Primary Scanners (Order of Importance)
1. **Ross' Five Pillars Scan** - Meets all 5 criteria
2. **Low Float Top Gainer** - Sub-1M float, biggest movers
3. **High Day Momo** - Breaking to new highs
4. **Recent Reverse Split** - Potential squeeze candidates
5. **After Hours Top Gainer** - Watch for pre-market continuation

### Scanner Signal Indicators
| Indicator | Meaning |
|-----------|---------|
| 🔥 Red flame | News 0-2 hours old (breaking) |
| 🔥 Orange flame | News 2-12 hours old |
| 🔥 Yellow flame | News 12-24 hours old |
| No indicator | News >24 hours old |
| ⬆️ Green arrow | Moving up the scanner |
| ⬇️ Red arrow | Falling on the scanner |

---

## 2.5. Technical Indicators (Always Check Before Trading)

*Source: "7 Candlestick Patterns I'm Actually Using Every Day" video*

### Moving Averages
| Indicator | Color | Usage |
|-----------|-------|-------|
| **9 EMA** | Gray | Primary intraday support - pullbacks here are ideal entries |
| **20 EMA** | Blue/Green | Secondary support level |
| **200 EMA** | Purple | Daily chart resistance/support - acts as ceiling until broken |

### Other Indicators
| Indicator | Green Light | Red Light |
|-----------|-------------|-----------|
| **VWAP** | Price above = bullish | Price below = bearish |
| **MACD** (12,26,9) | Positive = Trade | Negative = Don't trade |
| **Volume** | Increasing green = buying | High volume red = warning |

### Ross's Rules
- "Red light, green light" - MACD negative = don't trade
- Pullbacks to 9 EMA are ideal entries
- 200 EMA acts as ceiling until broken through with volume
- VWAP resets daily at 4am
- Light volume on pullbacks is ideal

---

## 3. Entry Rules

### Primary Entry Patterns
| Pattern | Description | Implementation |
|---------|-------------|----------------|
| **Pullback Entry** | Wait for surge, buy first candle making new high after pullback | [ ] Detect pullback from HOD |
| **Micro Pullback** | Small dip within uptrend, immediate reversal | [ ] <2% pullback from local high |
| **Red-to-Green** | Stock drops below previous close, reverses back | [ ] Detect R2G reversal |
| **Break of Resistance** | Clear trend line or level break | [ ] Breakout detection |
| **VWAP Break** | Stock consolidates below VWAP, then breaks above with momentum (Jan 20 2026: "I took this trade for the break through VWAP") | [x] Implemented |
| **MACD Gating** | Only enter when MACD positive | [ ] MACD > 0 |
| **Half-Dollar/Whole-Dollar** | Buy for break of round numbers ($6, $7, etc.) - best entry on fast moving stocks (Jan 28 GRI) | [ ] Round number breakout |
| **ABCD Pattern Breakout** | Classic technical pattern, wait for pattern to form then enter on breakout (Jan 29 DCX) | [ ] ABCD detection |
| **Cup & Handle VWAP Break** | Consolidate under VWAP with cup & handle, enter on VWAP break (Jan 30 LRHC) | [x] VWAP break implemented |

### Entry Timing
| Rule | Specification |
|------|--------------|
| Best window | 7:00 AM - 10:00 AM ET |
| Strongest days | Monday, Tuesday (historically) |
| News timing | Top/bottom of hour (7:00, 7:30, 8:00, 8:30, 9:00) |
| Unusual timing | 7:56 AM EPWK was unusual but worked |

### Entry Execution
| Parameter | Value |
|-----------|-------|
| Order type | Limit at Ask + 10 cents |
| Hotkey | Shift+1 (or Turbo Trader button) |
| Size | 98% of buying power (small account) |

---

## 4. Exit Rules

### Profit Taking
| Rule | Trigger |
|------|---------|
| **Primary target** | Retest of HOD |
| **Base hit philosophy** | 18 cents/share average winner |
| **Take profit early** | Don't turn winners into losers |
| **Break-even = win** | On commission-free broker |

### Stop Loss
| Rule | Specification |
|------|--------------|
| **Max loss per trade** | Low of entry candle |
| **Max daily loss** | 10% of account |
| **Mental stop** | Bail if doesn't "pull away" |

### Exit Execution
| Parameter | Value |
|-----------|-------|
| Order type | Limit at Bid - 10 cents |
| Hotkey | Control+Z |
| Size | 100% of position |

---

## 5. Position Sizing

### Small Account Rules
| Account Size | Max Position | Daily Goal |
|--------------|--------------|------------|
| $2,000 | 100% (cash account) | +10% ($200) |
| $3,000 | 100% (cash account) | +10% ($300) |

### Big Account Rules
| Price Range | Typical Size |
|-------------|--------------|
| $2-$5 | 10,000-20,000 shares |
| $5-$10 | 10,000 shares |
| $10-$20 | 5,000-10,000 shares |
| $50+ | Much smaller (too risky) |

---

## 6. Trade Management

### Adding Rules
| Rule | Details |
|------|---------|
| Add only on strength | Never add to losers |
| "Pulling away" pattern | Add when stock separates from entry |
| Scale in small account | Can't - one shot with cash account |
| **Add every 50 cents** | During parabolic moves, add at $7.50, $8, $8.50, $9, etc. (Jan 28 GRI) |
| **Add on micro pullback holds** | Wait for dip, if it holds, add for next breakout |

### Session Management
| Rule | Details |
|------|---------|
| One trade per day (cash) | Preserve buying power for best setup |
| Done after recovery | If recovered from red, stop trading |
| Week declining pattern | Mon $65k → Tue $20k → Wed $10k → Thu $2k → Consider reducing risk |
| **25% giveback = hard stop** | Walk away green, don't give back 30-50% (Jan 28) |
| **Failed curl = stop trying** | If multiple pops don't work, stop buying dips |

---

## 7. Avoid Rules (Critical)

### Stock-Level Disqualifiers
| Avoid | Reason | Source |
|-------|--------|--------|
| **Chinese stocks** | Unreliable float, pump/dump risk. **ICEBREAKER EXCEPTION**: Score ≥10 = pass with 50% size (Jan 20 TWWG) | Nov 2, Nov 5, Jan 20 |
| **REITs** | Repeated losses on sector | Nov 12, Nov 13 |
| **Penny stocks (<$1)** | Churning, commissions eat gains | Nov 13 |
| **Float >20M** | Not enough squeeze potential | Multiple |
| **No news in cold market** | Moves don't sustain | Nov 2 |
| **Extended stocks** | >20-30% above MAs | Nov 30 |

### Pattern-Level Disqualifiers
| Avoid | Reason | Source |
|-------|--------|--------|
| **Wide spreads (20+ cents)** | Can't lock profit | Nov 17 |
| **Jack knife candles** | Stock is untradeable after | Nov 26 CLSK |
| **Hidden sellers not breaking** | Wait for resolution | Nov 10 |
| **Big red candles on resume** | Shorts in control | Multiple |
| **11+ green candles without pullback** | Too extended, false breakout risk | Jan 28 MRNO |
| **Easy to borrow + high float** | Shorts make it choppy, fake-outs | Jan 28 BDYN |
| **Grinding price action** | Not worth fighting | Nov 16 |
| **T12 Halt Risk** | If stock could get halted pending company info (light volume foreign parabolic), skip entirely | Jan 29 TCGL |
| **Day 2 with lower relative volume** | Continuation plays need volume; lower RVol = skip | Jan 29 FEED/XHLD |
| **Started below $0.50** | Too cheap, crowded, hard to trade well | Jan 30 FATBB |

### Behavioral Disqualifiers
| Avoid | Reason | Source |
|-------|--------|--------|
| **Forcing trades** | 4 red days > bad trades | Nov 2 |
| **Trading when discombobulated** | Mindset > opportunity | Nov 18 |
| **Chasing after-hours without confirmation** | Often fades by 7 AM | Nov 2 |
| **Reducing quality standards** | Accuracy cascade effect | Nov 17 |

---

## 8. Level 2 Signals

### Hidden Buyer Detection (Critical - Nov 10 Masterclass)
| Signal | Meaning |
|--------|---------|
| **Sitting size that refreshes** | Iceberg order, hidden buyer |
| **Price holds despite visible sellers** | Hidden support |
| **Big sellers but price rising** | Buyers absorbing |

### Hidden Seller Detection
| Signal | Meaning |
|--------|---------|
| **Resistance that keeps refreshing** | Iceberg seller |
| **Price failing despite visible buyers** | Hidden resistance |
| **RAIN -$30k lesson** | Hidden seller caused reversal |

---

## 9. Market Context Rules

### Hot vs Cold Market
| Condition | Strategy Adjustment |
|-----------|---------------------|
| Hot market | More aggressive, 4/5 pillars OK |
| Cold market | Only A+ setups, all 5 pillars required |
| Holiday week | Expect slow, consider no-trade days |
| Government shutdown | Certain catalysts won't hit |

### Sector Rotation
| Sector | Current Status (as of Jan 2026) |
|--------|-------------------------------|
| Biotech | Always reliable catalyst source |
| AI | Hot theme |
| Crypto treasury | **Exhausted** - no longer working |
| REITs | **Avoid** |

---

## 10. Short Squeeze Profile (SMX Template)

### Profile Criteria for 1000%+ Squeeze
| Criteria | Target |
|----------|--------|
| Price | $5-$10 |
| Float | <1M shares |
| Recent reverse split | Yes |
| Short interest | >20% (prefer 37%+) |
| Utilization | >80% |
| Cost to borrow | Elevated (100%+) |
| News | Present (creates initial demand) |
| Relative volume | ≥5x |

---

## 11. Metrics Benchmarks

### Ross's Performance Metrics (Self-Reported)
| Metric | Value | Source |
|--------|-------|--------|
| Average winner | 18 cents/share | Nov 20 |
| Accuracy target | 70-75% | Nov 14 |
| Profit/Loss ratio | 2:1 | Nov 14 |
| Best trading window | 7 AM - 10 AM | Multiple |

### Small Account Challenge Results
| Day | P/L | Cumulative |
|-----|-----|------------|
| Day 1 | +$759 (+37%) | $2,759 |
| Day 2 | +$50 | $2,809 |
| Day 3 | +$291 (+10%) | $3,100 |
| Day 4 | +$12 (break-even) | $3,112 |

---

## 12. Commission-Free vs Direct Access

### When to Use Each
| Scenario | Recommendation |
|----------|----------------|
| Account <$25k | Commission-free |
| Break-even trades | Commission-free (price improvement helps) |
| Hot market, big size | Direct access |
| Quick scalps | Commission-free |

### Price Improvement (Webull)
- ~1 cent/share improvement
- Break-even trade = small winner
- Same trade can be +$11 (Webull) vs -$2,600 (Lightspeed)

---

## Verification Checklist

### Stock Selection
- [ ] 5 pillars implemented and configurable
- [ ] Float threshold adjustable for market conditions
- [ ] Chinese stock filter active
- [ ] REIT sector filter active
- [ ] News catalyst validation working

### Entry Logic
- [ ] Pullback pattern detection
- [ ] MACD gating implemented
- [ ] Trading window enforced (7 AM - 10 AM default)
- [ ] Entry at Ask + offset

### Exit Logic
- [ ] Stop at candle low
- [ ] Daily max loss enforced
- [ ] Exit at Bid - offset

### Risk Management
- [ ] Position sizing based on account %
- [ ] One trade per day option (cash account mode)
- [ ] Weekly P/L tracking for aggression adjustment

---

## Next Steps

1. **Verify Implementation** - Check each [ ] item against current Warrior bot code
2. **Gap Analysis** - Identify rules not yet implemented
3. **Retrospective Testing** - Run bot against historical days from transcripts
4. **Alignment Scoring** - Measure % agreement with Ross's actual trades
