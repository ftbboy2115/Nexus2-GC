# Live Session Review — 2026-03-03 Morning (Premarket)

**Mode:** PAPER | **Commit:** `7fd0d14` | **Session:** 6:06–8:45 ET (all premarket)

---

## Session Summary

| Metric | Value |
|--------|-------|
| Closed trades | 18 |
| Open positions | 2 (ANNA, EHTH) |
| Closed P&L | **-$2.60** (if P&L fields are accurate — see anomalies below) |
| Unique symbols | 10 |
| Win rate | 5W / 13L (28%) |
| Avg hold (losers) | ~2-4 min |
| Avg hold (winners) | ~12-30 min |

---

## Closed Trades (Chronological, ET)

| Time | Symbol | Entry | Exit | P&L | Exit Reason | Hold | Notes |
|------|--------|-------|------|-----|-------------|------|-------|
| 6:06 | RUBI | $1.48 | $1.49 | **+$0.36** | mental_stop | 30m | ✅ Partial at $1.62, high $1.72 |
| 6:12 | CISS | $1.73 | $1.79 | **+$0.60** | topping_tail | 17m | ✅ |
| 6:42 | TOPS | $5.52 | $5.42 | -$1.90 | orphan_cleanup | 12m | ⚠️ Orphan exit |
| 6:43 | RUBI② | $1.57 | $1.50 | -$0.70 | candle_under | 1m | Re-entry, immediate reversal |
| 7:03 | TOPS② | $5.57 | $5.21 | -$3.20 | technical_stop | 3m | Re-entry, gapped through stop |
| 7:13 | RPGL | $1.92 | $1.90 | -$0.20 | candle_under | 24m | Never moved, VWAP trigger |
| 7:25 | CISS② | $1.87 | $1.83 | -$0.40 | candle_under | 1m | Re-entry at higher price |
| 7:29 | RUBI③ | $1.55 | $1.53 | -$0.18 | candle_under | 5m | 3rd attempt on RUBI |
| 7:29 | ADIL | $2.80 | $2.75 | -$0.50 | candle_under | 4m | |
| 7:37 | BATL | $26.61 | $25.46 | -$3.45 | candle_under | 8m | 3 shares (price-tier sizing) |
| 7:56 | BATL② | $26.44 | $25.40 | -$3.12 | technical_stop | 4m | Re-entry, had $1.53 MFE! |
| 8:00 | ADIL② | $2.93 | $2.88 | -$0.50 | candle_under | 1m | Re-entry, 13¢ slippage |
| 8:01 | TMDE | $3.51 | $3.45 | **+$6.50** | candle_under | 8m | ⚠️ P&L anomaly — see below |
| 8:05 | TPET | $1.68 | $1.67 | **+$0.61** | mental_stop | 2m | ✅ Partial at $2.02, high $2.03 |
| 8:05 | MVO | $3.45 | $3.31 | **+$8.24** | candle_under | 12m | ⚠️ P&L anomaly — see below |
| 8:10 | TPET② | $1.75 | $1.73 | -$0.20 | candle_under | 2m | Re-entry |
| 8:11 | TMDE② | $3.47 | $3.42 | -$0.50 | candle_under | 1m | Re-entry |
| 8:21 | MVO② | $3.38 | $3.27 | -$1.10 | candle_under | 2m | Re-entry |
| 8:31 | ANNA | $4.34 | $4.01 | -$1.60 | technical_stop | 3m | Re-entered at $4.23 (open) |
| 8:37 | GWH | $1.93 | $1.79 | -$1.36 | candle_under | 2m | |

## Open Positions

| Symbol | Entry | Current | Stop | Target | P&L | Since |
|--------|-------|---------|------|--------|-----|-------|
| ANNA② | $4.23 | $4.14 | $4.00 | $4.69 | -$0.90 | 8:38 |
| EHTH | $1.50 | $1.51 | $1.44 | $2.47 | +$0.10 | 8:19 |

---

## 🚨 Key Issues

### 1. P&L Calculation Anomalies

Two trades show **positive P&L despite entry > exit**:

| Trade | Entry | Exit | Expected P&L | Reported P&L |
|-------|-------|------|-------------|-------------|
| TMDE #1 | $3.51 | $3.45 | -$0.60 | **+$6.50** |
| MVO #1 | $3.45 | $3.31 | -$1.40 | **+$8.24** |

> [!CAUTION]
> This is likely a P&L calculation bug. Needs investigation.

### 2. Excessive Re-entry (Same Session)

| Symbol | Entries | Net P&L |
|--------|---------|---------|
| RUBI | 3x | -$0.52 |
| BATL | 2x | -$6.57 |
| TOPS | 2x | -$5.10 |
| CISS | 2x | +$0.20 |
| ADIL | 2x | -$1.00 |
| MVO | 2x | +$7.14 (if P&L correct) |
| TPET | 2x | +$0.41 |
| TMDE | 2x | +$6.00 (if P&L correct) |
| ANNA | 2x+ | -$1.60 + open |

The `live_reentry_cooldown_minutes = 10` is being bypassed — most re-entries happen within 10 minutes. This setting may not be enforced in PAPER mode.

### 3. candle_under_candle Exits Very Quickly

11 of 18 exits were `candle_under_candle`, and most triggered within **1-4 minutes** of entry. This suggests:
- Either the entries are at extended price levels (buying the top of a move)
- Or `candle_under_candle` is too sensitive in premarket (thinner candles)

### 4. TOPS Orphan Cleanup

TOPS #1 exited via `orphan_cleanup` — this means the position was lost from in-memory tracking and cleaned up by the safety sweep. Potentially related to the ghost trade bug fix from yesterday.

### 5. BATL: Best MFE Wasted

BATL #2 had high_since_entry of $27.97 (MFE = +$1.53/share) but exited at $25.40 for a **-$1.04/share loss**. The base_hit target was $27.15 — it blew past the target and still lost. This is the exact scenario where partial profit-taking or trailing would help, but yesterday's sweep showed all trailing approaches were net negative across the full dataset.

---

## Overall Assessment

The bot is **over-trading in premarket** with rapid-fire entries and quick candle_under_candle exits. The pattern is: enter → immediate reversal → exit in 1-4 mins → re-enter same symbol → lose again.

The small 10-share PAPER sizing keeps dollar losses small, but the behavioral issues would scale with real sizing.
