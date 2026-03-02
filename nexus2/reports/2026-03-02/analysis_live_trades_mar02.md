# Live Trade Analysis — March 2, 2026 (Premarket)

**Total P&L:** -$7,039  |  **Trades:** 7  |  **Win Rate:** 2/7 (29%)  |  **Time:** 4:11–5:46 AM ET

---

## Trade Summary

| # | Time (ET) | Symbol | Shares | Entry | Exit | P&L | Exit Reason | Duration |
|---|-----------|--------|--------|-------|------|-----|-------------|----------|
| 1 | 4:11 | TMDE | 11,369 | $1.59 | $1.60 | **+$124** | topping_tail | 3 min |
| 2 | 4:16 | BATL | 3,164 | $10.55 | $10.00 | **-$1,742** | candle_under_candle | 3 min |
| 3 | 4:16 | TMDE | 12,847 | $1.64 | $1.50 | **-$1,742** | candle_under_candle | 1 min |
| 4 | 4:57 | CISS | 19,230 | $1.85 | $1.75 | **-$1,923** | candle_under_candle | 11 min |
| 5 | 5:10 | CISS | 22,727 | $1.86 | $1.79 | **-$1,591** | candle_under_candle | 36 min |
| 6 | 5:19 | BATL | 5,555 | $10.44 | $10.05 | **-$2,166** | candle_under_candle | 2 min |
| 7 | 5:34 | USEG | 16,666 | $1.57 | $1.69 | **+$2,000** | topping_tail | 5 min |

---

## Key Issues

### 1. Enormous position sizes on cheap stocks

The sizing formula (`risk_per_trade / stop_distance`) produces massive share counts on cheap stocks with wide stops:

| Symbol | Entry | Stop | Distance | Shares | Position Value |
|--------|-------|------|----------|--------|---------------|
| CISS | $1.86 | $1.36 | $0.50 (27%) | 22,727 | **$42,272** |
| CISS | $1.85 | $1.35 | $0.50 (27%) | 19,230 | **$35,576** |
| USEG | $1.57 | $1.40 | $0.17 (11%) | 16,666 | **$26,166** |
| TMDE | $1.64 | $1.14 | $0.50 (31%) | 12,847 | **$21,069** |
| BATL | $10.44 | $9.94 | $0.50 (5%) | 5,555 | **$57,994** |

With $2,500 risk and 27–31% stop distances, even small adverse moves cost thousands.

### 2. candle_under_candle exits far above stop

The `candle_under_candle` exit is saving the bot from the full stop loss, but with these position sizes, even a few cents against = big dollar losses:

| Trade | Stop Distance | Actual Loss/Share | % of Stop Used |
|-------|--------------|-------------------|----------------|
| BATL #1 | $0.50 | -$0.55 | 110% (below stop!) |
| TMDE #2 | $0.50 | -$0.14 | 28% |
| CISS #1 | $0.50 | -$0.10 | 20% |
| CISS #2 | $0.50 | -$0.07 | 14% |
| BATL #2 | $0.50 | -$0.39 | 78% |

BATL #1 actually exited BELOW the mental stop ($10.00 exit vs $10.05 stop). The candle_under_candle exit triggered at a worse level than the stop would have.

### 3. Re-entries after losses (no cooldown)

The bot entered the same symbol twice, losing both times:
- **CISS**: Lost $1,923 → re-entered 2 min later with **more shares** → lost $1,591 more
- **BATL**: Lost $1,742 → re-entered 1 hour later with **75% more shares** (5,555 vs 3,164) → lost $2,166 more
- **TMDE**: Won $124 → re-entered 5 min later → lost $1,742

### 4. All premarket, all penny/low-price stocks

Every trade was between 4:11–5:46 AM ET on stocks priced $1.50–$10.50. Premarket liquidity on these names is thin — getting 22,727 shares filled and exited cleanly is questionable.

### 5. Winners exited too early

The two winners (TMDE #1 and USEG) exited via `topping_tail`:
- TMDE: High was $1.68, exited at $1.60 (left $0.08/share × 11K shares = $908 on table)
- USEG: High was $1.73, exited at $1.69 (left $0.04/share × 16K shares = $667 on table)

---

## Root Cause: Sizing × Stop Distance

The fundamental issue isn't the entries or the exit logic — it's the **interaction between $2,500 risk, cheap stocks, and wide consolidation-low stops**:

```
$2,500 risk ÷ $0.50 stop = 5,000 shares × $1.85 entry = $9,250 position
$2,500 risk ÷ $0.17 stop = 14,705 shares × $1.57 entry = $23,087 position
```

Even when `candle_under_candle` exits early (saving from the full stop loss), a $0.10/share move against 19,000 shares = **$1,900 loss**.

---

## Recommendations

1. **Cap max_value_per_trade** — e.g., $5,000 to prevent $42K positions on penny stocks
2. **Per-symbol re-entry cooldown** — block re-entry on same symbol for N minutes after a loss
3. **Review candle_under_candle vs stop priority** — BATL #1 exited below its own stop, which shouldn't happen
4. **Consider premarket position size reduction** — thin liquidity makes large fills unreliable

---

> [!NOTE]
> Settings have been updated to safe testing levels (`risk_per_trade: $50`, `max_shares: 10`, `max_value: $100`).
> These issues only manifested at scale because the VPS had production-level settings ($2,500 risk, 40K max shares).
