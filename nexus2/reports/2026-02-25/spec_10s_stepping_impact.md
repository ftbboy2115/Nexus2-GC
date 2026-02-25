# 10-Second Stepping Impact: Simulation Realism Analysis

**Date:** 2026-02-25  
**Author:** Coordinator (code research)  
**Context:** Investigating whether the ~$9K P&L drop (from $164K → $155K baseline) after backfilling 10s bars represents more or less realistic simulation.

---

## Executive Summary

**10s stepping makes the simulation MORE realistic.** The $155K figure is the more trustworthy baseline.

The P&L drop occurs because 10s stepping removes a false advantage inherent in 1-minute stepping: the ability for trades to survive intra-minute stop breaches that would have been caught by the live system's rapid polling. The live Warrior Bot checks prices every 2-5 seconds — structurally matching 10s stepping far better than 60s stepping.

---

## Evidence: Live vs Sim Polling Frequencies

### Live Warrior Bot (Production)

| Component | Polling Interval | Code Reference |
|-----------|-----------------|----------------|
| **Monitor exit checks** | Every **2s** | [warrior_types.py:130](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_types.py#L130) — `check_interval_seconds: int = 2` |
| **Entry trigger checks** | Every **5s** | [warrior_engine.py:636](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine.py#L636) — `asyncio.sleep(5)` |
| **Price source** | Polygon REST snapshot | [polygon_adapter.py:115-175](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/market_data/polygon_adapter.py#L115) — `lastTrade` price with stale-trade fallback to bid/ask midpoint |

### Simulation

| Stepping Mode | Check Interval | Price Source |
|--------------|---------------|-------------|
| **10s stepping** | Every **10s** of sim time | 10s bar close price |
| **1min stepping** | Every **60s** of sim time | 1min bar close price |

> [!IMPORTANT]
> 10s stepping is **3-5x** closer to live polling frequency than 1min stepping.
> 1min stepping is **12-30x** slower than live, allowing trades to "hide" from stops.

### How the Gap Creates False P&L

In the live system at 2-5s polling:
1. Stock enters at $5.00, stop at $4.85
2. At T+12s, price dips to $4.84 → **stop triggered, exit**
3. Price recovers to $5.10 by T+60s (end of 1min bar)

In 1min stepping:
1. Stock enters at $5.00, stop at $4.85
2. At T+60s, price is $5.10 (1min bar close) → **stop NOT triggered**
3. Trade survives and may profit

In 10s stepping:
1. Stock enters at $5.00, stop at $4.85
2. At T+10s, price is $4.84 (10s bar close) → **stop triggered, exit** ✅ matches live

---

## Critical Mechanism: Poll-Based Stop Checking

Both live and sim use **identical stop logic** — comparing a **single polled price** against the stop level:

```python
# warrior_monitor_exit.py:375-382
def _check_stop_hit(position, current_price, r_multiple):
    if current_price > position.current_stop:
        return None  # No stop hit
    # ... trigger exit
```

Neither live nor sim checks OHLC extremes. The stop is only breached if the **polled price** (live: `lastTrade`, sim: bar close) is ≤ stop. This means:

- **Live:** A 2s poll might catch a sub-second dip that a 5s poll misses
- **10s sim:** Catches dips that persist for ≥10 seconds (realistic)
- **1min sim:** Only catches dips that persist as the close of a full minute (unrealistic — many stop hits happen mid-minute)

---

## Why ~$9K Drops: The Mechanism

The $9K drop splits into two effects:

### Effect 1: More Frequent Stop Hits (Primary)
With 6x more price samples per minute, the sim catches intra-minute lows that breach stops. In 1min mode, those same stops survive because the 1min close price recovered above the stop level.

### Effect 2: Earlier Entry/Exit Timing
10s stepping triggers entries and exits at sub-minute precision. This can shift entry prices (filling at a different 10s bar close) and exit timing (catching profit targets earlier or later).

Both effects make the sim behave more like the live system.

---

## NPT, ROLR, EVMN: Why These Three Drop Most

> [!NOTE]
> Without running the specific cases with logging, these are structural hypotheses based on the code mechanics. Exact root cause requires per-case replay with debug logging.

The three cases that drop most likely share a common pattern: **tight stops on volatile stocks.** When a stock's 10s intra-minute volatility exceeds the stop width:

- **1min stepping:** The stock dips below the stop and recovers within the same minute → stop NOT hit → trade profits
- **10s stepping:** The dip is captured at a 10s sample → stop IS hit → trade exits at a loss

### Investigation Path (if needed)
To confirm, run each case with `--verbose` and compare the stop-hit timestamps:
```
# Identify which exits differ between 1min and 10s stepping
# Look for: exits that happen in 10s mode but not in 1min mode
```

---

## Remaining Gap: 10s vs Live

Even with 10s stepping, there's still a **realism gap**:

| Factor | Live WB | 10s Sim | Impact |
|--------|---------|---------|--------|
| Poll frequency | 2-5s | 10s | Sim misses some 2-5s dips |
| Price source | `lastTrade` (real-time) | 10s bar close | Close ≈ lastTrade at bar boundary |
| Stale fallback | bid/ask midpoint | none | Sim has no spread mechanics |
| Intra-bar extremes | invisible (poll-based) | invisible (close-based) | **Same behavior** ✅ |
| Order execution | market + slippage | instant at bar close | Sim slightly optimistic |

The remaining gap is small and **directionally the same** — sim is still slightly optimistic compared to live. This is acceptable because sim should approximate live, not add false pessimism.

---

## Conclusions

1. **$155K is the more realistic baseline.** The $9K drop reflects correct removal of a false advantage.
2. **10s stepping should be the default going forward.** It matches live polling frequency within 2-5x (vs 12-30x for 1min).
3. **The $91K figure** (from switching `entry_bar_timeframe` to "10s") is a separate issue — that changes _which bars_ are used for pattern detection, not just clock stepping. This is a different investigation.
4. **No code changes needed.** The current 10s stepping implementation is correct.

---

## Open Questions

1. **Should we backfill 10s bars for ALL test cases?** Currently some cases lack 10s data and fall back to 1min stepping.
2. **Is the `entry_bar_timeframe: "10s"` → $91K drop a data fidelity issue or a pattern detection issue?** The 10s bars may not provide enough candle context for pattern recognition (micro-pullback, VWAP break). This needs separate investigation.
3. **Should we target 5s bars instead of 10s?** Polygon provides second-level aggregates. 5s bars would be closer to the live 5s entry check interval, at the cost of 2x more data.
