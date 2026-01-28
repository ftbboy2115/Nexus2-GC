# Warrior Trading (Ross Cameron)

## Overview

**Day trading** small-cap momentum stocks with catalysts. Ross trades the opening volatility window (typically first 1-2 hours: 7-10 AM ET).

**Bot**: Warrior Bot  
**Bot Trading Hours**: 4:00 AM - 7:30 PM ET (extended window)  
**Primary Source**: `.agent/knowledge/warrior_trading/` transcripts

---

## Core Methodology

### The 5 Pillars (Entry Criteria)

> [!NOTE]
> These are Ross Cameron's core stock selection criteria. The "Five Pillars" scanner finds stocks meeting all 5.

| # | Pillar | Requirement |
|---|--------|-------------|
| 1 | **Price** | $2-$20 sweet spot, $5-$10 ideal |
| 2 | **Gap/ROC** | 10-50%+ pre-market gap (Rate of Change) |
| 3 | **Float** | Sub-20M preferred, sub-5M ideal |
| 4 | **Volume** | High relative volume (5x+ average) |
| 5 | **Catalyst** | News required (except continuation squeezes) |

**Pattern** (entry trigger): PMH breakout, ORB, micro pullback, ABCD

### Stop Logic

> [!IMPORTANT]
> **Stop = LOW of the entry candle**  
> NOT a fixed 15-cent stop. NOT ATR-based.

Ross explicitly states: "Use the low of the entry candle as your stop."

### Position Sizing

- Risk fixed dollar amount per trade
- Size calculated from entry to candle low stop
- Scale in on confirmation, not all at once

### Exit Rules

- Scale out on strength (1/2 at first target)
- Trail remaining with candle lows
- Exit all on MACD cross negative

---

## Technical Indicators

### Uses

| Indicator | How Used |
|-----------|----------|
| **MACD (12,26,9)** | Hard gate: Only trade when MACD positive |
| **VWAP** | Support/resistance, trend confirmation |
| **9 EMA / 20 EMA** | Trend direction, pullback entries |
| **Volume** | Confirmation of breakouts |

### MACD Rules (CRITICAL)

> [!WARNING]
> **MACD negative = DO NOT TRADE**

From transcripts:
- "Red light, green light - MACD negative = don't trade"
- "Only add when MACD is positive"
- "MACD went negative → stopped adding"
- "MACD negative + declining volume = bull trap"

---

## Setup Types

### 1. PMH Breakout (Pre-Market High)
- Break above pre-market high
- Entry on break with volume confirmation
- Stop = candle low

### 2. ORB (Opening Range Breakout)
- First 5-min range forms
- Entry on break of high/low
- Stop = opposite side of range

### 3. Micro Pullback
- Within a strong move, small 1-3 candle pullback
- Entry on resumption
- Tight stops

### 4. ABCD Pattern
- A-B leg, consolidation, C-D continuation
- Entry at D breakout

---

## Disqualifiers (Do NOT Trade)

| Red Flag | Reason |
|----------|--------|
| Chinese company | Often manipulated, Schwab blocks |
| Cayman Islands | Schwab blocks, dilution risk |
| No catalyst | Pops reverse quickly |
| Heavy overhead supply | Resistance kills momentum |
| Easy to borrow | Shorts aggressive, squeezes fail (HTB = advantage) |
| MACD negative | Bull trap territory |
| Thick level 2 / big sellers | Absorption, hard to move |

---

## What Ross Does NOT Use

- RSI, Bollinger Bands, Fibonacci
- Swing trading timeframes
- ATR for stops (that's KK)
- Fixed 15-cent stops (misconception)

---

## Primary Sources

| Source | Location |
|--------|----------|
| Transcripts | `.agent/knowledge/warrior_trading/` |
| Ross Rules | `ROSS_RULES_EXTRACTION.md` |
| Implementation Audit | `IMPLEMENTATION_AUDIT.md` |
| KI | "Nexus 2 Trading Methodologies" → `warrior/strategy/` |

---

## Implementation Notes

### Warrior Bot Specifics

- **Trading Hours**: 4:00 AM - 7:30 PM ET (extended beyond Ross's 7-10 AM window)
- Scanner runs pre-market for gappers
- Catalyst detection via FMP + Yahoo + Finviz
- Stop method: `candle_low` (not `fallback_15c`)
- MACD gating implemented as hard gate
- Scaling enabled on strength

### Key Scanners

| Scanner | Purpose |
|---------|--------|
| **Five Pillars** | Meets all 5 core criteria |
| **Low Float Top Gainer** | Sub-1M float, biggest movers |
| **High Day Momo** | Stocks breaking to new highs (MOMO = momentum) |
| **Recent Reverse Split** | Squeeze candidates |
| **After Hours Top Gainer** | Pre-market continuation watch |

> [!NOTE]
> **MOMO** = Momentum trading - riding strong price movements (not fundamentals-based).
