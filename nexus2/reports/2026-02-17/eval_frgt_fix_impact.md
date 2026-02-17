# FRGT Fix Impact — Verified Analysis

**Date:** 2026-02-17
**Trade:** FRGT | bull_flag @ $1.86 × 2,500 | High: $2.01 | Exit: $1.81 (CUC) | P&L: -$125

---

## Which Fixes Are ON?

Verified from `warrior_types.py` defaults:

| Fix | Default | Status |
|-----|---------|--------|
| Fix 1: Partial-Then-Ride | `True` | ✅ ON |
| Fix 2: Proportional Trail | `0.0` | ❌ REJECTED (-10% P&L in batch) |
| Fix 3: Structural Levels | `False` | ❌ REJECTED (neutral, fewer winners) |
| Fix 4: Home Run Trail | `False` | ❌ REJECTED (-16% regression on 4c) |

**Only Fix 1 matters.** Batch test results (from `findings_exit_logic_optimization.md`):
- Baseline: $6,740
- Fix 1 alone: $13,298 **(+97%)**
- All other fixes: neutral or harmful

---

## Telemetry Evidence (Verified from VPS)

| Source | Key Data |
|--------|----------|
| `warrior.db → entry_validation_log` | **MFE = $0.15** (max gain: 15¢), **MAE = $0.08** (max drawdown: 8¢) |
| `warrior.db → warrior_trades` | `partial_taken = 0`, `exit_mode = base_hit`, `high_since_entry = 2.01` |
| `nexus.db → trade_events` | 5 events: ENTRY → FILL → CUC_EXIT → EXIT_FILL. **No trail or partial events** |
| `telemetry.db → warrior_scan_results` | Score 8, catalyst: acquisition (0.90 conf), RVOL: 3195x, float: 456K |

---

## Would Fix 1 Have Fired?

Fix 1 (Partial-Then-Ride) activates via the **candle trail stop** in `_check_base_hit_target`. Two paths exist:

### Path A: Candle Trail → Partial (the main Fix 1 path)

**Trail activation requires BOTH simultaneously:**
1. Profit ≥ 15¢ (activation threshold)
2. Lowest low of last 2 completed candles > $1.86 (entry price)

**Chart + telemetry analysis:**

- **MFE = 15¢** → profit hit exactly the threshold ($2.01)
- **MAE = 8¢** → price dropped to **$1.78** during the trade

From the chart, the price action was:
1. **5:28-5:30**: Massive spike from ~$1.73 to ~$2.06 (before/during entry)
2. **5:30 (entry)**: Bull flag triggers at $1.86 on the pullback
3. **5:30-5:32**: Volatile candles with deep lows (~$1.78-1.85) and highs near $2.00+
4. **5:33-5:38**: Price consolidates $1.85-$1.95, candle lows generally above $1.86
5. **5:39**: CUC exit at $1.81

**The problem:** When price was at $2.01 (steps 1-2), candle lows were deep ($1.78). When candle lows stabilized above $1.86 (step 4), price had already fallen below $2.01.

> **The two conditions never occurred simultaneously.**
> Trail NEVER activated. Fix 1 NEVER triggered.

### Path B: Flat Fallback → Partial

If trail doesn't activate, falls through to flat target:
- `base_hit_profit_pct = 0.0` (Fix 2 rejected) → uses fixed cents
- Target = $1.86 + $0.18 = **$2.04**
- High was $2.01 < $2.04 → **target never hit**

---

## Verdict: Fix 1 Would NOT Have Changed This Trade

The FRGT trade would still result in **-$125** with the new code because:

1. The candle trail never activated (spike + deep wicks = conditions never aligned)
2. The flat target ($2.04) was never reached
3. The CUC exit at $1.81 fires identically in both old and new code

**The root cause was the 5:30 AM entry in thin premarket**, not the exit logic. The premarket gate is the correct fix.

---

## ⚠️ LIVE ISSUE: VPS `_get_intraday_bars not set`

The server logs from RIGHT NOW (after this morning's restart) show:
```
06:46:22 | [Warrior Entry] FRGT: _get_intraday_bars not set
06:47:27 | [Warrior Entry] FRGT: _get_intraday_bars not set
```

This means the bar fetcher is **not wired up** on the restarted VPS. Without bars:
- No bull_flag detection (requires candle data)
- No candle trail stop (requires candle data)
- No candle-under-candle exit (requires candle data)

**This may need immediate attention if the bot is expected to trade today.**
