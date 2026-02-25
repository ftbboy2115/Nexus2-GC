# Spec: 10s vs 1min Bar Data Fidelity in Test Cases

**Agent:** Backend Planner  
**Date:** 2026-02-25  
**Reference:** `handoff_planner_10s_data_fidelity.md`

---

## Executive Summary

Only **3 of 35** test cases have 10s bar data. The remaining 32 cases run at 1-minute granularity. While the sim pipeline correctly uses 10s data for **price stepping** and **quote resolution** when available, there is a critical gap: the `sim_get_intraday_bars` callback (used by all pattern detection code) **does not support returning 10s bars** — it falls through to 1min. This means `entry_bar_timeframe="10s"` has **no effect in simulation**, even for the 3 cases that have 10s data.

Additionally, **all alternative patterns** (micro_pullback, pullback, vwap_break, bull_flag, cup_and_handle) **hardcode `"1min"` for candle fetches**, ignoring `entry_bar_timeframe` entirely. This explains why the 5 pattern toggle sweeps showed identical P&L.

---

## Finding 1: Test Case Inventory (10s vs 1min)

**Verified with:** `list_dir` on `nexus2/tests/test_cases/intraday/`

| # | 10s File | Matching Main File | Size |
|---|----------|--------------------|------|
| 1 | `bctx_20260127_10s.json` | `ross_bctx_20260127.json` | 161 KB |
| 2 | `gri_20260128_10s.json` | `ross_gri_20260128.json` | 179 KB |
| 3 | `hind_20260127_10s.json` | `ross_hind_20260127.json` | 71 KB |

**Result: 3/35 cases have 10s bars (8.6%).**

The remaining 32 cases have only 1-minute bar data in their `ross_*.json` files.

### How 10s Data Gets Loaded

**File:** `historical_bar_loader.py:332-344`
```python
# AUTO-LOAD 10s BARS: Look for matching *_10s.json file
symbol = data.get("symbol", "").lower()
date_str = data.get("date", "").replace("-", "")
if symbol and date_str:
    bars_10s_path = self._test_cases_dir / "intraday" / f"{symbol}_{date_str}_10s.json"
    if bars_10s_path.exists():
        with open(bars_10s_path, "r", encoding="utf-8") as f:
            data_10s = json.load(f)
        data["bars_10s"] = data_10s.get("bars", [])
```

The loader auto-discovers `*_10s.json` sidecar files. No configuration per-case — purely file-existence based.

---

## Finding 2: How `entry_bar_timeframe` Flows Through the Sim Pipeline

**Setting:** `warrior_engine_types.py:145`
```python
entry_bar_timeframe: str = "1min"  # Options: "1min", "10s"
```

### Where It's Used (Pattern Detection)

`entry_bar_timeframe` is checked in **2 patterns** for the **activity gate** only:

| Pattern | File:Line | Usage |
|---------|-----------|-------|
| `detect_dip_for_level` | `warrior_entry_patterns.py:398-434` | Activity candle fetch + `check_active_market` thresholds |
| `detect_pmh_break` | `warrior_entry_patterns.py:605-638` | Activity candle fetch + `check_active_market` thresholds |

When `tf == "10s"`, these patterns request candles via `engine._get_intraday_bars(symbol, "10s", limit=60)`.

### The Broken Link: `sim_get_intraday_bars` Doesn't Handle "10s"

**File:** `sim_context.py:384-407`
```python
async def sim_get_intraday_bars(symbol, timeframe="1min", limit=50, ...):
    ...
    bars = _loader.get_bars_up_to(symbol, time_str, timeframe, include_continuity=True)
    ...
```

This passes `timeframe` through to `HistoricalBarLoader.get_bars_up_to()`:

**File:** `historical_bar_loader.py:420-442`
```python
def get_bars_up_to(self, symbol, time_str, timeframe="1min", ...):
    if timeframe == "5min":
        return data.aggregate_to_5min(time_str)
    else:
        return data.get_bars_up_to(time_str, ...)  # ← ALWAYS returns 1min bars
```

**Conclusion:** `get_bars_up_to()` only handles `"1min"` and `"5min"`. When `timeframe="10s"` is passed, it hits the `else` branch and returns **1-minute bars**. The 10s bar data stored in `IntradayData.bars_10s` is **never accessed by pattern detection**.

### What 10s Data DOES Affect

Despite the pattern detection gap, 10s data **does** affect two things in the sim pipeline:

1. **Clock stepping granularity** (`sim_context.py:113-122`):
```python
use_10s_stepping = any(ctx.loader.has_10s_bars(sym) for sym in ...)
if use_10s_stepping:
    total_steps = minutes * 6  # 6 steps per minute instead of 1
    step_seconds = 10
```

2. **Price quote resolution** (`sim_context.py:443-458`):
```python
async def sim_get_quote_historical(symbol, ...):
    if _loader.has_10s_bars(symbol):
        time_str = _clock.get_time_string_with_seconds()
        price = _loader.get_10s_price_at(symbol, time_str)
        if price: return price
    # Fallback to 1min
```

So for BCTX, GRI, and HIND: the engine steps 6x faster and gets more precise prices — but patterns still analyze 1-minute candles.

---

## Finding 3: Alternative Patterns Hardcode "1min"

All 5 alternative patterns that showed identical P&L in sweeps hardcode their candle timeframe:

| Pattern | File:Line | Candle Fetch |
|---------|-----------|--------------|
| `check_micro_pullback_entry` | `warrior_entry_patterns.py:733` | `engine._get_intraday_bars(symbol, "1min", limit=30)` |
| `detect_pullback_pattern` | `warrior_entry_patterns.py:849+` | Uses `engine._get_intraday_bars(symbol, "1min", ...)` |
| `detect_vwap_break_pattern` | `warrior_entry_patterns.py:1089` | `engine._get_intraday_bars(symbol, "1min", limit=bar_limit)` |
| `detect_abcd_pattern` | `warrior_entry_patterns.py:75` | `engine._get_intraday_bars(symbol, "1min", limit=40)` |
| `detect_whole_half_anticipatory` | `warrior_entry_patterns.py:196` | `engine._get_intraday_bars(symbol, "1min", limit=10)` |

None of these check `entry_bar_timeframe`. They would need 10s candle data to potentially detect patterns that happen within a single 1-minute bar.

---

## Finding 4: Would 10s Data Change Entry Behavior?

### Patterns That Could Benefit From 10s Data

| Pattern | Why 10s Matters | Impact Level |
|---------|-----------------|--------------|
| **micro_pullback** | Swing highs/lows happen within 1min candles. A 2% dip and recovery in 30 seconds is invisible to 1min bars but visible to 10s. | **HIGH** — This pattern specifically tracks micro-movements |
| **pullback** | Pullback detection from HOD uses candle-level highs/lows. 10s would detect shallower pullbacks earlier. | **MEDIUM** |
| **vwap_break** | VWAP cross detection is price-tick based (already uses `_get_quote`), but volume confirmation uses candle volume. 10s volume bars would give earlier signals. | **MEDIUM** |
| **pmh_break** (activity gate) | Activity detection would be 6x more granular. A "dead market" with 1 bar/min might show 6 active 10s bars. | **LOW** — The gate already uses context-appropriate thresholds |
| **abcd/cup_and_handle** | These are structural patterns requiring 15-40 candles. 10s bars would need proportionally more bars. | **LOW** — Likely insufficient data depth |

### The Key Insight

The reason alternative patterns don't fire is **not necessarily** the bar timeframe — it's more likely that:
1. The pattern conditions aren't met on the test cases (setup_type filtering, guard conditions)
2. Most test cases are PMH break setups (Ross's primary pattern)
3. Pattern competition means only the matching setup_type is checked

However, **micro_pullback** is the most likely beneficiary of 10s data, since it tracks price movements that genuinely happen at sub-minute timeframes.

---

## Finding 5: Can We Backfill 10s Data from Polygon?

### Current Data Source
**File:** `fetch_test_case_data.py` uses **FMP** (Financial Modeling Prep) for 1-minute bars.

The existing 3 `*_10s.json` files were likely fetched from **Polygon.io** (the project uses Polygon for live 10s bars).

### Polygon 10s Aggregates Availability

> [!IMPORTANT]
> Polygon.io provides aggregate bars at any custom timeframe via their `/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}` endpoint. For 10-second bars: `multiplier=10, timespan=second`.

- **Data availability:** Polygon stores tick-level data. 10s aggregates are available for all US equities for **the last 2+ years**.
- **Our test dates:** Jan 14 – Feb 20, 2026 — well within the availability window.
- **API cost:** Polygon's "Stocks Starter" plan allows up to 5 API calls/minute (free tier). With 32 cases needing backfill, this takes ~7 minutes.
- **Data volume:** Each trading day has ~2,340 10s bars (6:30 AM – 8:00 PM). At ~100 bytes/bar, each case is ~230 KB.

### Backfill Script Requirements

A backfill script would need to:
1. Read `warrior_setups.yaml` to get all test case symbols/dates
2. For each case without a `*_10s.json`, fetch 10s aggs from Polygon
3. Format as `{bars: [{t: "HH:MM:SS", o, h, l, c, v}, ...]}` matching existing format
4. Save as `{symbol}_{YYYYMMDD}_10s.json` in `tests/test_cases/intraday/`

Estimated effort: **~1 hour** for a Backend Specialist to write and run.

---

## Finding 6: `sim_get_intraday_bars` Fix Required

Even if we backfill all 35 cases with 10s data, patterns will **still** receive 1-minute bars because `sim_get_intraday_bars` → `get_bars_up_to()` doesn't handle `"10s"` timeframe.

### Fix Needed in `sim_context.py:384-407`

The `sim_get_intraday_bars` callback needs a 10s path:

```python
async def sim_get_intraday_bars(symbol, timeframe="1min", limit=50, ...):
    # NEW: Handle 10s timeframe
    if timeframe == "10s" and _loader.has_10s_bars(symbol):
        time_str = _clock.get_time_string_with_seconds()
        bars_10s = _loader.get_10s_bars_up_to(symbol, time_str)
        # Apply limit
        if bars_10s and len(bars_10s) > limit:
            bars_10s = bars_10s[-limit:]
        return bars_10s
    
    # Existing 1min/5min path
    ...
```

### Fix Also Needed in `historical_bar_loader.py:420-442`

`get_bars_up_to()` needs a `"10s"` branch to call `get_10s_bars_up_to()` on the underlying `IntradayData`.

---

## Recommendations

### Priority 1: Backfill 10s Data for All 35 Cases (LOW effort)
- Write a Polygon fetch script
- Adds ~8 MB to test_cases directory
- **Impact:** Enables 10s price stepping for all cases → more precise entries

### Priority 2: Fix `sim_get_intraday_bars` to Return 10s Bars (LOW effort)
- 2 code changes: `sim_context.py` callback + `historical_bar_loader.py:get_bars_up_to()`
- **Impact:** Removes the broken link — patterns can actually receive 10s candles

### Priority 3: Update Alternative Patterns to Use `entry_bar_timeframe` (MEDIUM effort)
- `micro_pullback`, `vwap_break`, `pullback` need to check `engine.config.entry_bar_timeframe`
- Thresholds need adjustment (e.g., `min_bars=20` for 1min → `min_bars=120` for 10s)
- **Impact:** Potentially unlocks alternative pattern triggers

### Do NOT Do Yet
- Don't change `entry_bar_timeframe` default to "10s" until all 35 cases have 10s data
- Don't modify ABCD/cup_and_handle for 10s — these need 15-40 bars of structure, which at 10s granularity requires different detection logic

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| 10s bars return different MACD/EMA from 1min | **MEDIUM** | Technical indicators computed on 10s bars will have different smoothing. Need to adjust indicator periods or compute from 1min even when stepping at 10s |
| Backfill data may differ from live 10s | **LOW** | Polygon stores exact tick→aggregate data. Historical should match what the live system would have seen |
| Performance: 6x more steps per case | **LOW** | Already handled by 3 existing cases. May add ~30s to batch run |
| P&L may change for existing 3 cases | **MEDIUM** | After fixing sim_get_intraday_bars, BCTX/GRI/HIND may get different entry timing. Run before/after comparison |
