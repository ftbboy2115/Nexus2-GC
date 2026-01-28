# Qullamaggie (Kristjan Kullamägi / KK)

## Overview

**Swing trading** growth stocks using momentum setups. Typically holds **2-20 days**, but can extend longer if the trend remains intact (rides winners).

**Bot**: NACbot  
**Primary Source**: KI "Nexus 2 Trading Methodologies" → `qullamaggie/strategy.md`

---

## Core Methodology

### Setup Types

| Setup | Description |
|-------|-------------|
| **Episodic Pivot (EP)** | Massive gap (>10%) on earnings/clinical news |
| **Breakout** | Break of tight consolidation on daily chart |
| **High Tight Flag (HTF)** | 90-100% move in <2 months, tight consolidation |
| **Flag** | Multi-day pullback/consolidation in uptrend |

### Entry Criteria

- Trend alignment on higher timeframes
- Volume contraction in consolidation → expansion on breakout
- RS strength vs SPY (NOT RSI indicator)
- Tightness in price action
- Clean chart structure

### Stop Logic

> [!IMPORTANT]
> **Two-tier stop hierarchy**

| Stop Type | Meaning | Used For |
|-----------|---------|----------|
| **Tactical Stop** | Opening range low OR flag low | Position sizing, risk calculation |
| **Setup Invalidation** | EP candle low | Determines if setup still valid |

- Position size based on **tactical stop**, not setup invalidation
- ATR constraint: Stop distance should be ≤ 1.0 ATR

> [!WARNING]
> **LoD Risk Mitigation**: If the Low of Day (LoD) creates a stop distance > 1.0 ATR, the trade is either:
> 1. Skipped (too much risk), or
> 2. Sized down proportionally to maintain fixed dollar risk

### Position Sizing

- Fixed dollar risk per trade
- Size = Risk ÷ (Entry - Tactical Stop)
- No wide stops, no averaging down

### Exit Rules

- Add only on strength (never on weakness)
- Sell into strength
- Hard stops only (no mental stops)
- **Partial exits**: Sell 1/3 to 1/2 of position after **3-5 days** to "finance" the trade and move remaining stop to breakeven
- **Trend extension**: Continue holding beyond 20 days if trend remains intact (EMA surfing)

---

## News and Catalysts

> [!NOTE]
> **KK DOES use news** - specifically for Episodic Pivots

From documentation:
> "Buying massive gap-ups (>10%) on institutional-quality news (Earnings, Clinical Data)"

### Earnings Filter (5-Day Rule)

**AVOID** technical entries (Breakouts/HTF) within 5 calendar days of scheduled earnings.

**Exception**: EP setups, which trigger **after** earnings news is released.

---

## What KK Uses

| Element | How Used |
|---------|----------|
| **RS (Relative Strength)** | Stock strength vs SPY - NOT RSI |
| **ATR** | Stop distance validation |
| **Daily/Weekly charts** | Primary timeframes |
| **Volume profile** | Contraction/expansion patterns |
| **Moving averages** | 10/20/50 EMA for trend |

---

## Terminology (CRITICAL)

> [!CAUTION]
> **Do NOT confuse these terms**

| Term | Correct Meaning | NOT This |
|------|-----------------|----------|
| **RS** | Relative Strength vs SPY | NOT RSI indicator |
| **EP** | Episodic Pivot (earnings gap) | NOT Entry Point |
| **ATR** | Average True Range | Used for stop validation |
| **HTF** | High Tight Flag | Chart pattern |

---

## Disqualifiers

| Red Flag | Reason |
|----------|--------|
| Low float junk | Too volatile, manipulation |
| Extended stocks (>20-30% above MAs) | Chase risk |
| Heavy overhead supply | Resistance problems |
| Choppy price action | No clean structure |
| Wide spreads / illiquid | Execution problems |
| Indicator-based patterns | RSI divergence, MACD crossovers, etc. |

---

## What KK Does NOT Use

- Intraday scalping (5-min charts)
- **RSI, MACD, Bollinger Bands** for entries
- Fixed dollar/cent stops
- Day trading timeframes
- Random TA patterns

---

## Primary Sources

| Source | Location |
|--------|----------|
| KI Strategy | `qullamaggie/strategy.md` |
| Literature | `qullamaggie/literature.md` |

---

## Implementation Notes

### NACbot Specifics

- Swing-focused position management
- ATR-based stop calculation
- RS calculation vs SPY
- Earnings calendar integration for 5-day filter
