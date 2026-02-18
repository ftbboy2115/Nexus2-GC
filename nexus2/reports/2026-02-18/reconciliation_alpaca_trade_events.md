# Trade Reconciliation: Nexus Events vs Alpaca Broker (2026-02-18)

**Date:** 2026-02-18  
**Alpaca Reported P&L:** -$513.51  
**Nexus Trade Event P&L:** +$0.45  

---

## Executive Summary

Three issues were identified:

1. **BUG: Exit fill polling falls back to limit price** — When the 2-second fill poll times out, Nexus records the *limit order price* as the actual fill instead of the real Alpaca fill. All 4 exit orders today show this pattern.
2. **P&L mismatch between Nexus and Alpaca fills** — Because of bug #1, Nexus consistently under-reports exit prices. Corrected P&L using Alpaca fills is **+$1.15**, not +$0.45.
3. **-$513.51 is unaccounted for by these trades** — These 3 trades can only produce a max P&L swing of ~$113 total. The -$513.51 likely includes other positions, unrealized losses, or prior-day carryover not tracked by the Warrior bot.

---

## Trade-by-Trade Reconciliation

### Trade 1: BENF (bull_flag, 10 shares)

| Event | Nexus | Alpaca |
|-------|-------|--------|
| **Entry** quote/limit | $5.53 / — | — / $5.61 |
| **Entry fill** | **$5.50** | **$5.50** ✅ |
| **Partial Exit 1** (5 shares) limit | — | $5.67 |
| **Partial Exit 1** fill | $5.67 ❌ | **$5.70** |
| **Partial Exit 2** (5 shares) limit | — | $5.72 |
| **Partial Exit 2** fill | $5.72 ❌ | **$5.75** |

**Nexus P&L:** ($5.67−$5.50)×5 + ($5.72−$5.50)×5 = $0.85 + $1.10 = **+$1.95**  
**Actual P&L:** ($5.70−$5.50)×5 + ($5.75−$5.50)×5 = $1.00 + $1.25 = **+$2.25**  
**Discrepancy:** $0.30 undercounted

---

### Trade 2: UGRO (vwap_break, 10 shares)

| Event | Nexus | Alpaca |
|-------|-------|--------|
| **Entry** quote/limit | $4.17 / — | — / $4.23 |
| **Entry fill** | **$4.18** | **$4.18** ✅ |
| **Exit** (10 shares) limit | — | $4.05 |
| **Exit fill** | $4.05 ❌ | **$4.08** |

**Nexus P&L:** ($4.05−$4.18)×10 = **-$1.30**  
**Actual P&L:** ($4.08−$4.18)×10 = **-$1.00**  
**Discrepancy:** $0.30 undercounted (loss looks worse than reality)

---

### Trade 3: AUUD (bull_flag, 10 shares)

| Event | Nexus | Alpaca |
|-------|-------|--------|
| **Entry** quote/limit | $1.61 / — | — / $1.63 |
| **Entry fill** | **$1.62** | **$1.62** ✅ |
| **Exit** (10 shares) limit | — | $1.60 |
| **Exit fill** | $1.60 ❌ | **$1.61** |

**Nexus P&L:** ($1.60−$1.62)×10 = **-$0.20**  
**Actual P&L:** ($1.61−$1.62)×10 = **-$0.10**  
**Discrepancy:** $0.10 undercounted

---

## P&L Summary

| | BENF | UGRO | AUUD | **Total** |
|---|---|---|---|---|
| **Nexus Recorded** | +$1.95 | -$1.30 | -$0.20 | **+$0.45** |
| **Alpaca Actual** | +$2.25 | -$1.00 | -$0.10 | **+$1.15** |
| **Discrepancy** | +$0.30 | +$0.30 | +$0.10 | **+$0.70** |

> [!WARNING]
> Nexus consistently under-reports profits / over-reports losses because it uses the limit price (which has a 0.5-1% aggressive offset) instead of the actual Alpaca fill.

---

## Root Cause Analysis

### Bug: Exit fill polling fallback

**File:** [warrior_callbacks.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/api/routes/warrior_callbacks.py#L463-L479)

```python
# Line 463-479: Poll for actual fill price (up to 2 seconds)
actual_fill_price = None
order_id = str(order.id) if hasattr(order, 'id') else None
if order_id:
    for _ in range(4):          # 4 polls × 0.5s = 2 seconds max
        await asyncio.sleep(0.5)
        try:
            filled_order = alpaca.get_order(order_id)
            if hasattr(filled_order, 'filled_avg_price') and filled_order.filled_avg_price:
                actual_fill_price = float(filled_order.filled_avg_price)
                break
        except Exception as poll_err:
            break

exit_price = actual_fill_price if actual_fill_price else float(limit_price)  # ← FALLBACK TO LIMIT
```

**What happens:**
1. Exit order submitted as a limit sell at `current_price × 0.995` (aggressive offset)
2. System polls Alpaca 4 times (every 500ms) for filled_avg_price
3. If the poll doesn't find a fill within 2 seconds → **falls back to the limit price**
4. This limit price (which is lower than actual fill for sells) gets recorded as `actual_exit_price`

**Evidence from today's trades:**

| Symbol | Limit Price (Nexus used) | Actual Alpaca Fill | Difference |
|--------|-------------------------|-------------------|------------|
| BENF sell 1 | $5.67 | $5.70 | +$0.03 |
| BENF sell 2 | $5.72 | $5.75 | +$0.03 |
| UGRO | $4.05 | $4.08 | +$0.03 |
| AUUD | $1.60 | $1.61 | +$0.01 |

Every exit used the limit price, not the real fill. The 2-second polling window may be too short, or the `filled_avg_price` attribute may not be populated in time.

### Confusing metadata labels in EXIT_FILL_CONFIRMED

**File:** [trade_event_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/trade_event_service.py#L643-L696)

The `log_warrior_exit_fill_confirmed` function receives:
- `intended_price` = `signal.exit_price` (the price when exit was triggered)
- `actual_price` = `actual_exit_price` (what the broker returned — but actually the limit fallback)

The slippage calculation `(actual_price - intended_price) * 100` produces negative values and labels them "better", which is misleading for sells where a lower actual is actually worse.

---

## The -$513.51 Mystery

> [!IMPORTANT]
> These 3 Warrior trades produced a **maximum P&L of +$1.15** (Alpaca actual fills). The -$513.51 reported by Alpaca **cannot come from these trades**.

Possible sources of the -$513.51:
1. **Other open positions** with unrealized losses (not managed by Warrior bot)
2. **Prior-day positions** that carried over and were closed today
3. **NACbot trades** or other strategies running on the same account
4. **Account-level P&L** that includes all activity, not just Warrior
5. **The Alpaca P&L metric** may aggregate realized + unrealized across all positions

**Recommendation:** Check Alpaca dashboard for ALL positions and activity today, not just the 7 orders shown in the order history.

---

## Recommended Fixes

### 1. Improve exit fill polling (Priority: HIGH)
- Extend polling window to 5 seconds (10 polls × 500ms)
- Add a background fill reconciliation job that checks fills after 30 seconds
- If fill is confirmed later, update the trade event with corrected P&L

### 2. Add post-trade fill reconciliation (Priority: HIGH)
- After each trading session, compare all Nexus trade events against Alpaca order history
- Flag and correct any fill price discrepancies
- This catches cases where the 2-second poll missed the fill

### 3. Fix slippage direction for exits (Priority: MEDIUM)
- For sell orders, positive slippage (actual > intended) is BETTER, not worse
- The current formula `(actual - intended)` produces negative = "better" which is backwards for sells

### 4. Investigate the -$513.51 (Priority: HIGH)
- Check for non-Warrior positions in the Alpaca account
- Review if there are other bots or manual trades on this account
- Verify whether Alpaca's P&L includes unrealized losses on held positions
