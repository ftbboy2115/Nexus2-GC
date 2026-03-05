# Research: PMH Data Source — Zero Premarket Bars from Polygon

**Date:** 2026-03-04  
**From:** Backend Planner  
**Ref:** `handoff_planner_pmh_data_source.md`

---

## Root Cause: Timestamp Dropped During Bar Conversion

The `Bar` dataclass in `create_get_intraday_bars()` strips timestamps, making premarket filtering impossible.

### Evidence Chain

**1. The callback converts OHLCV → Bar, dropping `.timestamp`:**

**File:** `warrior_callbacks.py:264-270`
```python
@dataclass
class Bar:
    open: float
    high: float
    low: float
    close: float
    volume: int
    # ← NO timestamp field
```

**File:** `warrior_callbacks.py:318-324` — Polygon OHLCV converted to Bar:
```python
return [Bar(
    open=float(b.open), high=float(b.high), low=float(b.low),
    close=float(b.close), volume=int(b.volume)
    # b.timestamp is DROPPED here
) for b in bars]
```

**2. PMH derivation checks for timestamp, gets None, skips every bar:**

**File:** `warrior_engine.py:638-653`
```python
bar_ts = getattr(bar, 'timestamp', None)  # → None
if bar_ts is not None and hasattr(bar_ts, 'hour'):
    # ... timezone conversion — NEVER REACHED
else:
    bar_time = getattr(bar, 'time', '') or ''  # → ''
    if not bar_time:
        continue  # ← EVERY BAR HITS THIS
```

**Result:** All 400 bars are skipped → `pre_market_highs` is empty → logs `"No pre-market bars found in Polygon data (135 total bars)"` → falls to FMP.

---

## Answers to Handoff Questions

### Q1: Does `_get_intraday_bars` request extended hours?

**Yes — implicitly.** Polygon's Aggregates API (`/v2/aggs/ticker/{symbol}/range/...`) includes all trading hours (4 AM – 8 PM ET) by default. There is no `extended_hours` parameter — premarket and after-hours bars are always included.

**Verified:** `polygon_adapter.py:420-422` — no filtering params:
```python
data = self._get(
    f"/v2/aggs/ticker/{symbol}/range/{timeframe}/{unit}/{from_date}/{to_date}",
    params={"limit": limit, "sort": sort_order}
)
```

The bars themselves are fine. **The problem is the conversion layer** stripping timestamps before `_get_premarket_high()` can filter by time.

### Q2: What does Polygon actually return?

Polygon returns `OHLCV` objects with a proper UTC `datetime` in `.timestamp` — including premarket bars. The `from_date` defaults to today (`now_et().strftime("%Y-%m-%d")`), so all today's bars (4 AM onward) are included.

**But:** The callback at `warrior_callbacks.py:318-324` converts these to timestamp-less `Bar` objects. The 135/156 bars logged for VCIG/CANF likely DID include premarket bars — they just couldn't be filtered.

### Q3: Is FMP's premarket high accurate?

**Likely inaccurate for micro-caps.** FMP's `get_premarket_high()` at `fmp_adapter.py:466-509`:
- Uses **30-min bars** (`timeframe="30min"`) — very coarse, may miss premarket spikes
- FMP timestamps are in ET (no timezone conversion needed)
- For CANF: FMP returned $8.73, but chart shows ~$15 peak → FMP is significantly wrong
- FMP's premarket data for micro-caps is **sparse and unreliable** — 30-min bars may only capture 1-2 bars in premarket that average out the highs

**File:** `fmp_adapter.py:488-489`
```python
bars = self.get_intraday_bars(symbol, timeframe="30min", date=date)
```

### Q4: What Polygon parameter enables premarket bars?

**No parameter needed.** Polygon includes all extended hours bars (4 AM – 8 PM ET) by default for any paid plan (Developer tier and up). The date range specified via `from`/`to` determines which bars are returned, and since `from_date` defaults to today, premarket bars ARE fetched.

---

## Fix Required

### Single Change: Preserve timestamp in the Bar dataclass

**File:** `warrior_callbacks.py:264-270`

Add `timestamp` to the `Bar` dataclass and pass it through from the OHLCV conversion:

```python
@dataclass
class Bar:
    open: float
    high: float
    low: float
    close: float
    volume: int
    timestamp: datetime = None  # ← ADD THIS
```

Then at L318-324 (Polygon path), L288-291 (sim path), and all other conversion points:

```python
return [Bar(
    open=float(b.open), high=float(b.high), low=float(b.low),
    close=float(b.close), volume=int(b.volume),
    timestamp=getattr(b, 'timestamp', None)  # ← PRESERVE
) for b in bars]
```

### Change Surface

| # | File | Change | Why |
|---|------|--------|-----|
| 1 | `warrior_callbacks.py:266` | Add `timestamp: datetime = None` to `Bar` | Core fix |
| 2 | `warrior_callbacks.py:318-324` | Add `timestamp=b.timestamp` in Polygon conversion | Pass through |
| 3 | `warrior_callbacks.py:288-291` | Add `timestamp=getattr(b, 'timestamp', None)` in sim conversion | Consistency |
| 4 | `warrior_callbacks.py:339-345` | Add `timestamp=getattr(b, 'timestamp', None)` in Alpaca conversion | Consistency |
| 5 | `warrior_callbacks.py:357-363` | Add `timestamp=getattr(b, 'timestamp', None)` in FMP conversion | Consistency |

### FMP Fallback: Keep but don't rely on

FMP fallback should remain as a secondary source (some data is better than none), but it's unreliable for micro-caps due to 30-min bar granularity. With the Polygon timestamp fix, the primary path will work correctly and FMP will rarely be needed.

---

## Risk Assessment

- **Low risk fix:** Adding a field to a local dataclass. No API changes, no schema changes.
- **No regression risk:** The `Bar` dataclass is internal to `create_get_intraday_bars()`. Adding an optional field with `= None` is backward-compatible — existing code that doesn't use `.timestamp` is unaffected.
- **Verification:** After fix, the log should show `"Derived from Polygon bars ($X.XX, N pre-market bars)"` instead of `"No pre-market bars found"`.
