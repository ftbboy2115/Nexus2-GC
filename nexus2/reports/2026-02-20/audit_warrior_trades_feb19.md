# Warrior Bot Trade Audit — 2026-02-19

> **Auditor**: Coordinator Agent  
> **Source**: `warrior.db` → `warrior_trades` table  
> **Methodology Reference**: `.agent/strategies/warrior.md`

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Total trades | 23 |
| Winners | 5 (22%) |
| Losers | 18 (78%) |
| Total P&L | **-$25.00** |
| Unique symbols | 8 (CISS×5, KNRX×4, CDIO×4, BOXL×2, ELAB×2, AGIG×2, FJET×1, LEE×1, FLUX×1) |
| Trading window | 5:15 AM – 6:05 PM ET (13 hours) |
| Avg hold time | ~3 minutes |

> [!CAUTION]
> **Critical finding: The bot traded 13 hours straight with an 78% loss rate. Ross's prime window is 7–9AM.**

---

## 🚨 Critical Violations (vs. Warrior Strategy)

### 1. Massive Overtrading — 23 Trades in One Day

**Strategy says** (§5, §7):
- Cold market: 1–2 trades max
- Hot market: 5–10+ trades
- "Don't trade longer on a day that's not going well"

**Bot did**: 23 trades across 13 hours. After the first 5 trades (4 losses), the bot should have evaluated whether to continue. Instead, it kept trading through the afternoon and evening.

---

### 2. Trading FAR Outside Ross's Window

**Strategy says** (§9.3):
- 7:00–9:00 AM ET = **Prime window** (most profit here)
- 9:00–9:30 AM = **Caution, often stops**
- 9:30 AM+ = **Rarely trades this session**

**Bot did**:

| Time Window (ET) | Trades | P&L |
|-----------------|--------|-----|
| 5:00–7:00 AM (pre-market) | 2 | -$0.45 |
| 7:00–9:00 AM (**prime**) | 3 | -$2.70 |
| 9:00–10:00 AM (caution) | 6 | -$7.11 |
| 10:00 AM–6:05 PM (**should not trade**) | 12 | -$14.74 |

**78% of trades happened OUTSIDE the prime window.** The most damaging trades (AGIG -$6.96, FJET -$5.25, CISS -$3.02) all happened after 9:30 AM when Ross would have stopped.

---

### 3. No Red Day Rule / Daily Loss Max

**Strategy says** (§6.2):
- Walk away early when not working
- "No trade days are better than red days"
- Last trade typically before 9:00 AM on red days

**Bot did**: After being red by ~$3 at 8:28 AM (trade #5), it continued for 10 more hours and 18 more trades, deepening losses from -$3 to -$25. There appears to be **no circuit breaker**.

---

### 4. Repeated Re-entries on Failing Stocks

**Strategy says** (§4.3):
- 3–5 trades on same stock per session max
- After 2+ failed re-entries: "gave up on this one"
- Below VWAP + MACD negative → "it's done"

**Bot did**:

| Symbol | Trades | Wins | Losses | Total P&L |
|--------|--------|------|--------|-----------|
| CISS | 5 | 1 | 4 | -$5.81 |
| KNRX | 4 | 2 | 2 | -$1.53 |
| CDIO | 4 | 0 | 4 | -$4.00 |
| BOXL | 2 | 1 | 1 | +$0.45 |
| AGIG | 2 | 1 | 1 | -$6.64 |

CDIO had 4 attempts with zero wins. By strategy rules, the bot should have stopped after 2 failed attempts.

---

### 5. Position Sizing Issues

**Strategy says** (§6.3, §6.4):
- Start with small "break ice" position
- Size up only when you have a **cushion** (green on day)
- Reduce size if cushion disappears

**Bot did**: Position sizes actually get LARGER as the day goes on and losses mount:
- Early trades: 10 shares
- Mid-day: 18-20 shares  
- AGIG: 40 shares (while red on day)

The bot sized UP while losing, the exact opposite of Ross's "cushion" methodology.

---

### 6. Tiny Absolute Sizes

All positions are 3–40 shares. Ross trades 5,000–50,000 shares. If these are real (not paper), the P&L per trade is cents to single dollars. This suggests either:
- Intentionally micro-sized for testing (expected)
- Or sizing logic is disconnected from account equity

> [!NOTE]
> If these are intentional test sizes (is_sim=0 but micro-lot), this is understandable. But the RELATIVE sizing pattern (getting bigger while losing) is still wrong.

---

## Trade-by-Trade Summary

| # | Time (ET) | Symbol | Trigger | Shares | Entry | Exit | P&L | Exit Reason | Issue |
|---|-----------|--------|---------|--------|-------|------|-----|-------------|-------|
| 1 | 5:15 AM | CISS | vwap_break | 10 | $1.96 | $1.84 | -$1.20 | candle_under | ✅ Prime window |
| 2 | 6:00 AM | BOXL | bull_flag | 10 | $1.56 | $1.54 | +$0.75 | mental_stop | ✅ |
| 3 | 7:11 AM | CDIO | dip_for_level | 10 | $2.25 | $2.16 | -$1.00 | candle_under | ✅ |
| 4 | 7:38 AM | ELAB | vwap_break | 10 | $1.58 | $1.51 | -$0.70 | candle_under | ✅ |
| 5 | 8:28 AM | CDIO | dip_for_level | 20 | $2.54 | $2.51 | -$1.00 | candle_under | ⚠️ CDIO re-entry #2, home_run mode while red |
| 6 | 9:31 AM | CDIO | dip_for_level | 10 | $2.65 | $2.46 | -$1.90 | orphan_cleanup | ❌ 3rd CDIO attempt, past prime window |
| 7 | 9:34 AM | BOXL | bull_flag | 18 | $1.69 | $1.67 | -$0.30 | candle_under | ⚠️ Sized up while red |
| 8 | 9:36 AM | CISS | vwap_break | 18 | $2.19 | $2.25 | +$1.01 | topping_tail | ✅ Winner |
| 9 | 9:43 AM | AGIG | vwap_break | **40** | $4.50 | $4.37 | **-$6.96** | candle_under | ❌ Largest size while deep red |
| 10 | 9:44 AM | CISS | bull_flag | 12 | $2.26 | $2.22 | -$0.49 | candle_under | ⚠️ 3rd CISS trade |
| 11 | 9:52 AM | ELAB | bull_flag | 3 | $1.46 | $1.40 | -$0.17 | candle_under | ⚠️ |
| 12 | 10:03 AM | KNRX | vwap_break | 14 | $2.40 | $2.33 | +$1.34 | mental_stop | ⚠️ Winner but outside window |
| 13 | 10:06 AM | FLUX | bull_flag | 25 | $1.51 | — | -$0.09 | partial | ⚠️ |
| 14 | 11:27 AM | CISS | bull_flag | 20 | $2.34 | $2.25 | -$1.81 | candle_under | ❌ 4th CISS, midday |
| 15 | 11:36 AM | KNRX | bull_flag | 14 | $2.57 | $2.62 | +$0.73 | topping_tail | ⚠️ Winner but midday |
| 16 | 12:37 PM | CISS | vwap_break | 20 | $2.21 | $2.17 | -$0.80 | candle_under | ❌ 5th CISS attempt |
| 17 | 12:59 PM | KNRX | bull_flag | 14 | $2.35 | $2.30 | -$1.21 | candle_under | ❌ 3rd KNRX loss |
| 18 | 1:54 PM | FJET | vwap_break | 20 | $11.07 | $10.81 | **-$5.25** | topping_tail | ❌ Afternoon, big loss |
| 19 | 2:12 PM | LEE | bull_flag | 6 | $9.19 | $9.06 | -$0.76 | candle_under | ❌ Afternoon |
| 20 | 3:15 PM | AGIG | vwap_break | 20 | $4.73 | $4.75 | +$0.32 | topping_tail | ❌ Should not be trading |
| 21 | 3:30 PM | CISS | bull_flag | 10 | $2.44 | $2.37 | -$3.02 | topping_tail | ❌ 5th CISS, afternoon |
| 22 | 3:50 PM | KNRX | bull_flag | 20 | $2.45 | $2.33 | -$2.39 | candle_under | ❌ 4th KNRX, near close |
| 23 | 6:05 PM | CDIO | bull_flag | 10 | $3.09 | $3.08 | -$0.10 | mental_stop | ❌ After-hours trading |

---

## Recommendations

### Immediate (Non-Negotiable)

1. **Implement daily loss circuit breaker** — Stop trading after N consecutive losses or X% daily drawdown
2. **Enforce time window** — Hard-code 6:00 AM – 9:30 AM ET as the allowed trading window, with extension only if green on day
3. **Per-symbol re-entry limit** — Max 3 attempts on same symbol, max 2 failures before giving up on that ticker
4. **Reverse cushion sizing** — Position size should DECREASE when red on day, not increase

### Investigation Needed

5. **Home run mode triggers** — CDIO trade #5 used `home_run` mode while the bot was red. What triggers this?
6. **AGIG 40-share sizing** — Why did the bot size up to 40 shares on AGIG (its largest position) while deep red?
7. **Orphan cleanup exits** — CDIO trade #6 exited via `orphan_cleanup` — what does this mean?
8. **FJET at $11** — At the higher end of Ross's price range. Is the price pillar too loose?

---

## P&L Curve (Cumulative)

```
Trade  1: -$1.20  (cum: -$1.20)
Trade  2: +$0.75  (cum: -$0.45)
Trade  3: -$1.00  (cum: -$1.45)
Trade  4: -$0.70  (cum: -$2.15)
Trade  5: -$1.00  (cum: -$3.15) ← Should consider stopping here
Trade  6: -$1.90  (cum: -$5.05) ← RED DAY RULE should trigger
Trade  7: -$0.30  (cum: -$5.35)
Trade  8: +$1.01  (cum: -$4.34)
Trade  9: -$6.96  (cum: -$11.30) ← Biggest single loss, sized UP
Trade 10: -$0.49  (cum: -$11.79)
Trade 11: -$0.17  (cum: -$11.96)
Trade 12: +$1.34  (cum: -$10.62)
Trade 13: -$0.09  (cum: -$10.71)
Trade 14: -$1.81  (cum: -$12.52) ← Midday, should have stopped hours ago
Trade 15: +$0.73  (cum: -$11.79)
Trade 16: -$0.80  (cum: -$12.59)
Trade 17: -$1.21  (cum: -$13.80)
Trade 18: -$5.25  (cum: -$19.05) ← 2nd biggest loss, afternoon
Trade 19: -$0.76  (cum: -$19.81)
Trade 20: +$0.32  (cum: -$19.49)
Trade 21: -$3.02  (cum: -$22.51)
Trade 22: -$2.39  (cum: -$24.90)
Trade 23: -$0.10  (cum: -$25.00) ← AFTER HOURS (6:05 PM)
```

> [!WARNING]
> The bot's two largest losses (AGIG -$6.96, FJET -$5.25) account for 49% of the total loss and both occurred after 9:30 AM when Ross would have stopped trading.
