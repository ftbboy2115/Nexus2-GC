# Plan: 10-Second Bar Support for Live Warrior Bot

> **Status**: Draft — awaiting Clay's review  
> **Priority**: High — directly impacts entry timing and profitability  
> **Triggered by**: SPAI missed trade on 2026-02-20 (PMH break blocked for 5+ min due to insufficient 1-min bars)

---

## Problem Statement

The live Warrior bot uses **1-minute bars exclusively** for all entry decisions. This creates two critical issues:

1. **Slow activation**: The `check_active_market` gate requires 5 bars = 5 full minutes of 1-min data before any entry. In fast pre-market scenarios (like SPAI), the best entry happens in the first 30-60 seconds.
2. **Coarse pattern detection**: VWAP breaks, micro pullbacks, and PMH breaks happen on the 10-second chart. A VWAP break at 8:57:40 is invisible on 1-min bars until the 8:58 candle closes.
3. **Phantom quote divergence**: With 1-min bars, the live price can diverge 5-7% from the candle close (a full minute of lag). With 10s bars, max lag is 10 seconds.

**The sim/mock market already supports 10s bars** — the `HistoricalBarLoader` has `has_10s_bars()` and `get_10s_price_at()` methods. The live bot just doesn't use them.

---

## Architecture Overview

### Current Flow (Live)

```
Entry patterns → engine._get_intraday_bars(symbol, "1min", limit=N)
                    ↓
              create_get_intraday_bars() in warrior_callbacks.py
                    ↓
              Polygon → /v2/aggs/ticker/{SYM}/range/1/minute/{date}/{date}
                    ↓
              Returns Bar(open, high, low, close, volume) objects
```

**Problem**: Every call site hardcodes `"1min"` — there are **~30 call sites** across:
- `warrior_entry_patterns.py` (17 sites)
- `warrior_entry_helpers.py` (3 sites)
- `warrior_entry_guards.py` (2 sites)
- `warrior_engine_entry.py` (3 sites)
- `warrior_vwap_utils.py` (1 site)
- `warrior_entry_sizing.py` (1 site)

### Proposed Flow (Dual Timeframe)

```
Entry patterns → engine._get_intraday_bars(symbol, "10s", limit=N)   ← NEW: micro timing
               → engine._get_intraday_bars(symbol, "1min", limit=N)  ← KEEP: structure/MACD

              create_get_intraday_bars()
                    ↓
              if timeframe == "10s":
                  Polygon → /v2/aggs/ticker/{SYM}/range/10/second/{date}/{date}
              else:
                  Polygon → /v2/aggs/ticker/{SYM}/range/1/minute/{date}/{date}
```

---

## Configuration-Driven Approach

> [!IMPORTANT]
> **Per Clay's direction**: The bar timeframe should be a **dashboard-editable setting**, not a hardcoded change. This enables easy A/B testing and instant rollback if 10s bars hurt performance.

### New Setting: `entry_bar_timeframe`

Add to `WarriorEngineConfig` (or `WarriorMonitorSettings`):

```python
entry_bar_timeframe: str = "1min"  # Options: "10s", "1min"
```

- **Default: `"1min"`** — current behavior, zero risk
- **Toggle to `"10s"`** from dashboard → bot switches to 10s bars for entry timing
- **Toggle back** instantly if results degrade

This setting flows through `_get_intraday_bars` calls at the entry pattern layer. Structural indicators (MACD, consolidation, flags) always use 1-min regardless.

### How It Propagates

```python
# In each entry pattern, instead of hardcoded "1min":
tf = engine.config.entry_bar_timeframe  # "10s" or "1min"
candles = await engine._get_intraday_bars(symbol, tf, limit=N)
```

The `check_active_market` thresholds also adapt:
```python
if tf == "10s":
    min_bars, min_vol = 18, 200    # 18×10s = 3 min of data
else:
    min_bars, min_vol = 5, 1000    # 5×1min = 5 min (current)
```

---

## What Uses 10s vs 1-min Bars (Strategy-Aligned)

From `warrior.md` §8, Ross uses:

| Chart | Purpose | Bar Source |
|-------|---------|-----------|
| **10-second** | Entry timing, micro pullbacks | → **10s bars** |
| **1-minute** | Intraday structure, base patterns | → **1-min bars** |
| **5-minute** | Broader context | → **1-min bars** (enough) |

### Proposed Mapping

| Function | Current | Proposed | Rationale |
|----------|---------|----------|-----------|
| `check_active_market()` | 5 × 1-min bars | 15-30 × 10s bars | Market active in ~30s, not 5 min |
| PMH break detection | 1-min bars | **10s bars** | Catches break within seconds |
| VWAP break detection | 1-min bars | **10s bars** | Ross acts on 10s VWAP cross |
| Micro pullback / curl | 1-min bars | **10s bars** | Matches Ross's 10s chart |
| Phantom quote check | 1-min candle close | **10s candle close** | 10s max lag vs 60s current |
| MACD calculation | 1-min bars | **1-min bars** (keep) | MACD is structural indicator |
| Volume expansion | 1-min bars | **1-min bars** (keep) | Minute-level volume more meaningful |
| Consolidation / flag patterns | 1-min bars | **1-min bars** (keep) | Multi-minute structures |
| Technicals (EMA, etc.) | 1-min bars | **1-min bars** (keep) | Standard timeframes |

---

## Implementation Phases

### Phase 1: Polygon 10s Bar Adapter (Foundation)

**File**: `polygon_adapter.py`

Modify `get_intraday_bars()` to support sub-minute timeframes:

```python
# Current: always /range/{tf}/minute/
# Proposed:
if timeframe_seconds and timeframe_seconds < 60:
    url = f"/v2/aggs/ticker/{symbol}/range/{timeframe_seconds}/second/{from_date}/{to_date}"
else:
    url = f"/v2/aggs/ticker/{symbol}/range/{timeframe_minutes}/minute/{from_date}/{to_date}"
```

> [!IMPORTANT]
> Verify Polygon Advanced tier includes sub-minute aggregates. The endpoint exists (`/range/10/second/`) but may need to confirm it returns pre-market data.

---

### Phase 2: Callback Layer (Routing)

**File**: `warrior_callbacks.py`

Update `create_get_intraday_bars()` to route 10s requests:

```python
async def get_intraday_bars(symbol: str, timeframe: str = "1min", limit: int = 50):
    if timeframe in ("10s", "10sec"):
        polygon_tf = "10"
        polygon_unit = "second"
    else:
        polygon_tf = timeframe.replace("min", "").replace("Min", "")
        polygon_unit = "minute"
    # ... rest of routing
```

---

### Phase 3: Entry Patterns (Surgical Updates)

Only change the **specific call sites** where 10s resolution matters:

| File | Call Site | Change |
|------|-----------|--------|
| `warrior_entry_patterns.py:395` | `check_active_market` activity candles | `"1min"` → `"10s"`, `min_bars=5` → `min_bars=18` |
| `warrior_entry_patterns.py:561` | `check_active_market` activity candles | Same |
| `warrior_entry_patterns.py:534` | PMH break confirmation candle | `"1min"` → `"10s"` |
| `warrior_engine_entry.py:376` | Phantom quote sanity check | `"1min"` → `"10s"` |

**Leave on 1-min**: MACD checks, consolidation detection, volume expansion, bull flag structure, technicals.

---

### Phase 4: `check_active_market` Tuning

With 10s bars, adjust thresholds:

```python
# Current (1-min bars):
check_active_market(candles, min_bars=5, min_volume_per_bar=1000, max_time_gap_minutes=15)

# Proposed (10s bars):
check_active_market(candles, min_bars=18, min_volume_per_bar=200, max_time_gap_minutes=5)
# 18 × 10s = 3 minutes of activity (vs 5 minutes before)
# Volume threshold lower per 10s bar (200 vs 1000 per minute)
```

---

## API Rate Limit Considerations

> [!WARNING]
> Polygon Advanced tier allows high rate limits but 10s bars return 6x more data points per request.

- Current: ~1 API call per check (50 × 1-min bars)
- Proposed: Same 1 call but returns 50 × 10s bars (still within limits)  
- The bot checks ~6 watchlist symbols every ~7 seconds = ~50 bar requests/minute
- This should be well within Polygon Advanced tier limits

**Mitigation**: Add a brief cache (5-10s TTL) for 10s bar requests per symbol to avoid redundant fetches within the same check cycle.

---

## Verification Plan

### Automated
1. Confirm Polygon `/range/10/second/` returns pre-market data for a known symbol
2. Run existing batch test cases (they already use 10s bars via mock market — should be unaffected)
3. Unit test `check_active_market` with 10s-spaced candles

### Manual
1. Deploy and watch next pre-market session
2. Compare logs: does bot enter faster on gapping stocks?
3. Check phantom quote frequency — should drop significantly with 10s bars

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Polygon doesn't return 10s pre-market data | Medium | Test with real API call before implementing |
| 10s bars have low/no volume in thin pre-market | Medium | Fall back to 1-min if 10s returns empty |
| Rate limiting from increased granularity | Low | Cache + Polygon Advanced tier |
| Entry patterns break with different bar count | Low | Only change 4 call sites, rest stay 1-min |
| 10s noise causes false triggers | Medium | Only use 10s for activity + PMH/VWAP breaks, not structure |

---

## ✅ API Validation Results (2026-02-20)

> [!TIP]
> **Confirmed: Polygon returns 10s pre-market bars on the Advanced tier.**

| Test | Result | Details |
|------|--------|---------|
| SPAI today (2026-02-20) | ✅ 30 pre-market bars | Starting 8:55 ET, 10s cadence with volume |
| SPAI yesterday (2026-02-19) | ✅ 4 PM + 114 regular bars | Sparse PM (low-volume day), full regular hours |
| AAPL yesterday (2026-02-19) | ✅ 46 pre-market bars | Starting 4:00 AM ET (extended hours) |

**Key findings:**
- Pre-market 10s bars are available with volume data
- Bars start as early as 4:00 AM ET for active tickers
- For gapping small-caps (the Warrior target), bars appear ~1 hour before open
- The existing `get_second_bars()` method in `polygon_adapter.py` (line 442) already constructs the correct endpoint

**Conclusion:** Data source is viable. No tier upgrade needed.

---

## Quick Win (Can Do Immediately)

Before the full 10s implementation, a **quick config change** could help:

```python
# In check_active_market calls:
min_bars=3  # instead of 5 (3 minutes vs 5 minutes)
```

This doesn't fix the granularity issue but would have let SPAI enter ~2 minutes sooner today.
