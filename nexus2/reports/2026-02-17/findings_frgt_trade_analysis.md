# FRGT Full Lifecycle Analysis — February 17, 2026

**Date:** 2026-02-17 | **Symbol:** FRGT | **Catalyst:** Acquisition (SemiCab AI Platform)

---

## Executive Summary

Two trades taken on FRGT today. Trade 1 lost -$125 via CUC exit. Trade 2 entered at 07:13 via vwap_break (live).
Price peaked at ~$2.00 but the trail activation threshold ($2.01) was missed by ~1¢.

**Root cause of Trade 1 loss:** Price peaked +14¢ above entry but the base_hit trail activation requires +15¢. The 1¢ gap prevented trail activation, and the subsequent reversal triggered a CUC exit at -$0.05 from entry.

---

## Trade 1: Bull Flag Entry → CUC Exit

### Scanner Discovery (04:01 EST)

| Field | Value |
|-------|-------|
| Gap | 16.3% |
| Scanner Score | 8 |
| Catalyst | acquisition (conf 0.90) |
| Float | 456,454 |
| RVOL | 3195x |
| PMH | $1.65 |
| Headlines | 7 found — "SemiCab's AI Platform Shown to Handle 400% More Freight Volume..." |

Scanner correctly identified FRGT premarket. Passed all 5 pillars on first scan.

### PMH Break Blocking (04:01–05:30)

The PMH break was blocked for **~90 minutes** by two guards:

1. **Bar count gate (04:01–04:06):** "Only N bars (need 5)" — waiting for premarket bars to accumulate
2. **Volume gate (05:05):** "Low volume (684 avg vs 1000 min)" — price crossed PMH but volume too thin

Market became active at **05:30:00** when volume cleared the 1000 minimum threshold.

### Entry Pipeline (05:30:10)

| Step | Detail |
|------|--------|
| Pattern | BULL FLAG — first green after 2 red candles, break of prev high $1.77 |
| Competition | BULL_FLAG won (score=0.701, threshold=0.4) |
| MACD | OK (histogram=0.0056) |
| Technicals | VWAP=$1.75, 9EMA=$1.78, MACD=neutral |
| Stop | $1.74 via `consolidation_low` (5-bar low=$1.76) |
| Exit Mode | `base_hit` (session setting) |
| Confidence | 0.70 |
| Intent Price | $1.84 |
| Fill Price | **$1.86** (+2¢ slippage) |
| Shares | 2,500 |

### Exit Monitoring (05:30–05:39)

```
Trail activation:  $2.01  (entry $1.86 + 15¢)
Flat fallback:     $2.04  (entry $1.86 + 18¢)
Stop:              $1.74  (consolidation_low)
```

**Price action during hold:**

| Time (EST) | Price | Δ from entry |
|------------|-------|-------------|
| 05:30:16 | $1.88 | +2¢ |
| 05:30:21 | $1.87 | +1¢ |
| ~05:33 | **~$2.00** | **+14¢** (peak, from scanner DB) |
| 05:39:02 | $1.81 | **-5¢** (CUC exit) |

The key moment: price peaked at ~$2.00 (+14¢) but never reached the trail activation at $2.01 (+15¢). **Missed by approximately 1¢.**

### Exit (05:39:02)

| Field | Value |
|-------|-------|
| Exit Reason | `candle_under_candle` |
| Exit Price | $1.81 (quote $1.82, fill $1.81, +1¢ better) |
| P&L | **-$125.00** |
| Hold Time | ~9 minutes |

### Fix 1 Impact Assessment

Fix 1 (Partial-Then-Ride) would have **no impact** — it only activates after an initial sell at the profit target.
Since price never reached the target, Fix 1 never engages.

### What Would Have Helped

- **Lower trail activation** (e.g., 12¢ instead of 15¢) would have activated at $1.98
- **Percentage-based activation** (e.g., 7%) = $0.13 = $1.99 activation — still missed
- The real issue: this was a marginal trade where the peak-to-entry spread was exactly at the threshold boundary

---

## Trade 2: VWAP Break Re-entry (LIVE)

### Entry (07:13:15)

| Field | Value |
|-------|-------|
| Trigger | `vwap_break` |
| Intent Price | $1.89 |
| Fill Price | $1.90 (+1¢ slippage) |
| Stop | $1.73 |
| Shares | 1,562 |

**Note:** Smaller position (1,562 vs 2,500) due to wider stop ($1.73 vs $1.74). This trade is currently live.

### Scanner Data Since Re-entry

FRGT continues to pass scanner (score=8). Price range since re-entry: $1.77–$1.90.

---

## Infrastructure Issues Found

### 1. `_get_intraday_bars` Not Set
- **Cause:** Stopping Engine Control via dashboard disables broker → clears callbacks
- **Fix:** Re-enabled via `POST /warrior/broker/enable`
- **Status:** ✅ Resolved — "got 10 candles" confirmed

### 2. VIX Data Source Bug
- **Bug:** Was querying `VIXY` ETF ($28 share price) instead of actual VIX index
- **Fix:** Changed to `^VIX` via FMP direct query
- **Status:** ✅ Deployed (commit `ed6579a`)

### 3. Technical Context Audit Gap
- Server log at 05:30:16: `[TradeEvent] FRGT: Technical context unavailable from live API - audit gap`
- This means the trade event was logged WITHOUT technical context (VWAP, EMA, MACD values)
- **Impact:** Telemetry record is incomplete — can't reconstruct exact technical state at fill time

### 4. `warrior_trades.db` Empty
- The VPS `warrior_trades.db` has no tables — trade records are not being persisted to the trade DB
- Trade data only exists in TML (log file) and telemetry events
- **Impact:** No queryable trade history for analysis — only log files available

---

## Telemetry Pipeline Status

| Component | Working? | Notes |
|-----------|----------|-------|
| Scanner DB | ✅ | FRGT passing consistently, score=8 |
| TML (trade log) | ✅ | Entry/exit/guard events recorded |
| Server Log | ✅ | Full pipeline tracing |
| Trade Events DB | ⚠️ | Table name mismatch — no `trade_events` table found |
| Warrior Trades DB | ❌ | Empty — no tables exist |
| Technical Context | ⚠️ | "audit gap" — not captured at fill time |
