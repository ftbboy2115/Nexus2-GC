# Research: VCIG EMA Data Quality + Health Metrics

**Date:** 2026-03-04 11:45 ET
**Author:** Backend Planner
**Handoff:** `handoff_planner_vcig_ema_health.md`

---

## TL;DR

| Question | Answer |
|----------|--------|
| Why is EMA 200 = $665,900? | **Bar reversal bug** in `_get_200_ema` — computes EMA backward through time, seeding from newest bars and converging toward oldest. Likely amplified by unadjusted historical data (reverse split). |
| Where is `room_to_ema_pct` calculated? | Line 1725 of `warrior_scanner_service.py`, purely derived from the broken EMA 200 value. |
| Do health metrics gate entries? | **NO — they are DISPLAY ONLY.** Health metrics are only computed in API route for dashboard rendering. |
| What safeguards exist? | **NONE.** No sanity check exists for absurd EMA values. The existing ceiling check paradoxically PASSES broken data. |

---

## 1. Why is EMA 200 = $665,900?

### Root Cause: Bar Reversal Bug + Possible Unadjusted Split Data

The EMA 200 is computed in `_get_200_ema()`.

**File:** [warrior_scanner_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py#L1166-L1210)

### Data Source

Polygon daily bars via `get_daily_bars(symbol, limit=400)`.

**File:** [polygon_adapter.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/market_data/polygon_adapter.py#L502-L550)

```python
# Line 530 — Polygon API call
data = self._get(
    f"/v2/aggs/ticker/{symbol}/range/1/day/{from_date}/{to_date}",
    params={"limit": limit, "sort": "asc"}
)
```

> [!CAUTION]
> **No `adjusted` parameter is passed.** The Polygon API defaults `adjusted=true`, but this is implicit and unverified.

### Bug #1: Bar Reversal (Computing EMA Backward)

The bars come from Polygon sorted `"asc"` (oldest first). But `_get_200_ema` **incorrectly assumes they are newest-first** and reverses them:

```python
# Line 1196 — WRONG assumption
# Note: bars are typically most recent first, so we need to reverse
closes_chronological = closes[::-1]  # Oldest to newest
```

**What actually happens:**
1. Polygon returns: `[bar_day1, bar_day2, ..., bar_day400]` (oldest → newest, because `sort: "asc"`)
2. `closes` = `[close_day1, ..., close_day400]` (already oldest → newest)
3. `closes[::-1]` reverses to `[close_day400, ..., close_day1]` (**newest → oldest**)
4. `sma = sum(closes_chronological[:200]) / 200` → SMA of the **200 newest** bars (wrong — should be oldest)
5. `for close in closes_chronological[200:]` → iterates through **increasingly OLD** bars

**Result:** The EMA starts from a recent SMA and then "runs backward" through time, converging toward old historical prices. For stocks with very different historical prices, this produces garbage.

### Bug #2: Likely Unadjusted Reverse Split Data

VCIG has a gap of **171.48%** and RVOL of **2882x** with PMH of **$33.3** (stock at ~$9). This pattern is consistent with a recent reverse split.

If VCIG had a significant reverse split and Polygon's adjustment hasn't fully propagated (or if the bars predate the adjustment), pre-split prices (e.g., $0.001 per share × 75,000 shares = $75 per share... or much higher raw cumulative bars) would contaminate the EMA.

Combined with the backward computation (Bug #1), the EMA converges toward these inflated/unadjusted historical prices → **$665,900**.

### Cache TTL Makes It Worse

```python
# Line 1723 — cached for 6 HOURS
ctx.ema_200_value = self._cached(f"ema200:{ctx.symbol}", 21600, lambda: self._get_200_ema(ctx.symbol))
```

Once computed, the broken $665K value persists for 6 hours without recalculation.

---

## 2. Where is `room_to_ema_pct` Calculated?

**File:** [warrior_scanner_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py#L1725)

```python
# Line 1725
ctx.room_to_ema_pct = ((float(ctx.last_price) - float(ctx.ema_200_value)) / float(ctx.ema_200_value)) * 100
```

**For VCIG:** `((9 - 665900) / 665900) * 100 = -99.998%`

This is **purely derived** from the broken EMA 200. Fix the EMA → fixes `room_to_ema_pct`.

### The Scanner Gate Paradoxically PASSES

```python
# Line 1729
if ctx.room_to_ema_pct < 0 and ctx.room_to_ema_pct > -s.min_room_to_200ema_pct:
```

With `min_room_to_200ema_pct = 15`:
- `-99.998 < 0` → True
- `-99.998 > -15` → **False**
- Combined: **False → Does NOT reject**

The logic interprets -99.998% as "the price is way below the EMA, tons of room to run" — correct for real data, but **silently passes garbage data**.

---

## 3. Do Health Metrics Gate Entries?

### Answer: NO — Display Only

`PositionHealth` (the dashboard traffic lights: MACD, EMAs, VWAP, Volume, Stop, Target) is **computed exclusively in the API route** for dashoard rendering:

**File:** [warrior_positions.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_positions.py#L106-L258)

```python
# Line 106 — This is an HTTP GET endpoint, not entry logic
@positions_router.get("/positions/health")
async def get_positions_health():
    ...
    health = indicator_service.compute_position_health(...)  # Line 137, 184, 233
```

**Callers of `compute_position_health` (exhaustive):**

| Caller | File | Line | Purpose |
|--------|------|------|---------|
| `get_positions_health()` | `warrior_positions.py` | 137, 184, 233 | API endpoint for dashboard |

**NOT called by:**
- `warrior_engine_entry.py` (entry decisions)
- `warrior_monitor.py` (position monitoring)
- `warrior_scanner_service.py` (scanning)

> [!IMPORTANT]
> The dashboard shows red health indicators, but the bot **does not use them for any trading decision**. They are purely visual.

### The Scanner's EMA Check IS a Gate — But Only for Scanning

The `_check_200_ema()` function IS called during scanning (line 983), and it CAN reject candidates. But:
1. It only rejects if price is **slightly** below EMA (0% to -15% room)
2. Broken EMA values bypass it entirely (as shown above)
3. It is NOT checked again at entry time

---

## 4. What Safeguards Exist for Bad EMA Data?

### Answer: NONE

There is **zero sanity checking** on the EMA 200 value anywhere in the codebase.

No check for:
- ❌ EMA > 100x current price
- ❌ EMA < 0.01x current price
- ❌ EMA = 0 or negative
- ❌ Absurd bar values in the source data
- ❌ Split-adjusted consistency

---

## Recommended Fixes

### Fix 1: Bar Ordering Bug (CRITICAL)

Remove the incorrect reversal in `_get_200_ema`. Bars from Polygon with `sort: "asc"` are already oldest-first.

```diff
- # Note: bars are typically most recent first, so we need to reverse
- closes_chronological = closes[::-1]  # Oldest to newest
+ # Polygon returns bars sorted ascending (oldest first) — already chronological
+ closes_chronological = closes
```

**File:** `warrior_scanner_service.py:1195-1196`

### Fix 2: Explicit `adjusted=true` Parameter

Pass `adjusted=true` explicitly rather than relying on Polygon's default.

```diff
  data = self._get(
      f"/v2/aggs/ticker/{symbol}/range/1/day/{from_date}/{to_date}",
-     params={"limit": limit, "sort": "asc"}
+     params={"limit": limit, "sort": "asc", "adjusted": "true"}
  )
```

**File:** `polygon_adapter.py:530`

### Fix 3: EMA Sanity Check

Add a sanity check in `_check_200_ema` to catch absurd values before they're used:

```python
# After line 1724, before computing room_to_ema_pct:
if ctx.ema_200_value and float(ctx.last_price) > 0:
    ratio = float(ctx.ema_200_value) / float(ctx.last_price)
    if ratio > 100 or ratio < 0.01:
        scan_logger.warning(
            f"200 EMA SANITY FAIL | {ctx.symbol} | EMA=${ctx.ema_200_value:.2f} vs Price=${ctx.last_price:.2f} | "
            f"Ratio: {ratio:.0f}x — likely stale/unadjusted data, ignoring"
        )
        ctx.ema_200_value = None  # Discard garbage value
        return None
```

**File:** `warrior_scanner_service.py`, inside `_check_200_ema()` after line 1724

### Fix 4 (Optional): Position Health As Entry Gate

The dashboard health indicators COULD gate entries, but this is a **design decision for Clay**. Currently they're display-only by design. If desired, the entry engine could check `ema200` status before entering, but the broken data bug should be fixed first.

---

## Evidence Summary

| Finding | File | Line | Verified With |
|---------|------|------|---------------|
| EMA computed from Polygon daily bars | `warrior_scanner_service.py` | 1178 | `view_file` |
| Bar reversal bug (wrong assumption) | `warrior_scanner_service.py` | 1195-1196 | `view_file` |
| Polygon returns `sort: "asc"` (oldest first) | `polygon_adapter.py` | 530 | `view_file` |
| No `adjusted` param passed to Polygon | `polygon_adapter.py` | 530 | `grep_search` for "adjusted" in file — 0 results |
| `room_to_ema_pct` derived from EMA | `warrior_scanner_service.py` | 1725 | `view_file` |
| Scanner gate passes broken data | `warrior_scanner_service.py` | 1729 | Logic analysis |
| Health metrics display-only | `warrior_positions.py` | 106-258 | `grep_search` for all callers |
| No callers from entry engine | `warrior_engine_entry.py` | — | `grep_search` for "health" — no results in entry files |
| EMA cached 6 hours | `warrior_scanner_service.py` | 1723 | `view_file` |
| VCIG gap 171.48%, RVOL 2882x, PMH $33.3 | VPS diagnostics | — | SSH query to VPS |
