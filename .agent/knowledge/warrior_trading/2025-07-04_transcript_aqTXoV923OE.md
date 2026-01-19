# Ross Cameron - 7 Candlestick Patterns I'm Actually Using Every Day
**Video**: https://www.youtube.com/watch?v=aqTXoV923OE
**Published**: 2025-07-04

---

## Summary

Ross teaches the 7 candlestick patterns he uses daily, emphasizing simplicity for beginners. Focus on mastering 1-2 patterns first.

---

## Technical Indicators (Always Check Before Trading)

### 1. Volume Bars
- Look for increasing green volume (buying)
- High volume red candles = warning sign
- Light volume on pullbacks is ideal

### 2. Moving Averages
- **9 EMA** (gray) - Primary intraday support
- **20 EMA** (blue/green) - Secondary support
- **200 EMA** (purple) - Daily chart resistance/support
- Pullbacks to 9 EMA are ideal entries

### 3. VWAP (Volume Weighted Average Price)
- Above VWAP = bullish
- Below VWAP = bearish
- Breaks above/below are high-volume events
- Reset daily at 4am

### 4. MACD (12, 26, 9 settings)
- **Positive = Trade** (green light)
- **Negative = Don't trade** (red light)
- When negative, stay out completely
- Crossover signals trend exhaustion

---

## The 7 Candlestick Patterns

### 1. Candle Over Candle (Priority: Highest)
**Description**: Simplest pattern - two candles where second makes new high
- First candle establishes control (max loss = low of candle)
- Entry: Buy as second candle breaks high of first
- Works on breakouts OR change in direction
- First candle can be green OR red

**Entry**: Buy as price breaks high of control candle
**Stop**: Low of control candle
**Target**: 2:1 profit ratio

### 2. Micro Pullback (Priority: High)
**Description**: 1-3 candle pullback after initial squeeze
- Stock hits scanners, squeezing up fast
- Get 1-2 red candles on light volume
- First GREEN candle to make new high = entry
- Best on stocks up 50%+ with clear catalyst

**Entry**: First candle to make new high after pullback
**Stop**: Low of the pullback
**Target**: Continuation through previous high

### 3. Bull Flag (Priority: High)
**Description**: Like micro pullback but takes longer (3-5 candles)
- Price squeezes up, consolidates below high
- Forms pennant/flag shape
- Entry on first candle to break high of flag

**Entry**: Break of flag high
**Stop**: Low of the flag
**Target**: Measured move (height of pole)

### 4. ABCD Pattern (Priority: Medium)
**Description**: Failed bull flag that creates stair-step
- Pop up, dip down, pop up, dip down
- Critical: Must hold previous low (no lower lows)
- Best entry: Break through double-top resistance

**Entry**: Break of the "C" high (resistance)
**Stop**: Low of "D" point
**Target**: Continuation after resistance break

### 5. Cup and Handle (Priority: Medium)
**Description**: Double top with small bull flag handle
- Creates U-shaped formation with resistance
- Handle forms as small consolidation at resistance
- Entry on break of handle/resistance

**Entry**: Break of handle high (above double top)
**Stop**: Low of handle
**Target**: Measured move of cup depth

### 6. Inverted Head & Shoulders (Priority: Lower)
**Description**: Recovery pattern after selloff
- Left shoulder, head (lower), right shoulder
- Neckline = resistance
- Often combined with VWAP break

**Entry**: Break of neckline/VWAP
**Stop**: Below right shoulder
**Target**: Height of head to neckline

### 7. Break of VWAP (Priority: High)
**Description**: Price breaks above VWAP with volume
- Represents shift in control (shorts covering + longs buying)
- 2x volume on breaks (shorts cover = buy, longs enter = buy)
- Must have MACD positive

**Entry**: First candle to break and hold above VWAP
**Stop**: Below VWAP
**Target**: Previous high or next resistance

---

## Pattern Priority (Ross's Ranking)

1. **Candle Over Candle** - Fastest entry, best for catching moves early
2. **Micro Pullback** - Best risk/reward, primary setup
3. **Bull Flag** - Similar to micro pullback, takes longer
4. **Break of VWAP** - High-volume shift in momentum
5. **ABCD Pattern** - Only trade if holds previous low
6. **Cup and Handle** - Trade the bull flag within it
7. **Inverted H&S** - More complex, layer with other patterns

---

## Exit Indicators (When to Sell)

1. **Large sell orders on Level 2** - Big sellers stepping in
2. **Large topping tail candles** - Bearish rejection
3. **High volume red candles** - Sellers in control
4. **Buying slows on Time & Sales** - Momentum fading
5. **Price stops moving up** - "Break out or bail out"

---

## Key Quotes

- "The best trades work almost instantly"
- "Break out or bail out" - If it doesn't work right away, get out
- "Red light, green light" - MACD negative = don't trade
- "Nothing goes just straight up" - Trade the waves
- "I trade the first and second pullback on the 1-minute, then first and second on the 5-minute"
- "You want to see if this can actually break through the high and hold"

---

## Five Pillars of Stock Selection (Referenced)
Ross mentions his "Five Pillars of Stock Selection" multiple times - these patterns work ONLY on stocks meeting those criteria:
1. High relative volume
2. Strong catalyst (news)
3. Low float (for day trading)
4. Clean chart/range
5. Leading gainer (top of market)

---

## Implementation Notes for Nexus

### Pattern Alignment
- **PMH_BREAK** → Maps to "Candle Over Candle" at breakout
- **candle_under_candle exit** → VALID - Inverse of candle over candle (bearish signal)
- **EMA stops** → Matches Ross's 9 EMA support concept
- **VWAP entries** → Matches "Break of VWAP" pattern

### What Nexus Implements Correctly
- PMH breakout entries
- EMA-based mental stops
- Candle-under-candle exits (valid per this video)
- Volume confirmation

### Gaps to Address
- MACD confirmation (not currently checked before entry)
- Micro pullback pattern (not explicitly implemented)
- Bull flag detection (not implemented)
- More sophisticated exit indicators
