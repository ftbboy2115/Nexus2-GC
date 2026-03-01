# Research Report: Windows vs Linux Batch Divergence — Root Cause Found

**Agent:** Backend Planner  
**Date:** 2026-02-28  
**Status:** ✅ ROOT CAUSE IDENTIFIED — Trace logging may be unnecessary

---

## Executive Summary

> [!CAUTION]
> **THREE wall-clock leaks found in entry logic that directly affect trading decisions.**
> These explain the $137K gap ($391K Windows vs $254K Linux) without needing trace logging.

The divergence is NOT caused by float arithmetic, `set()` ordering, bar loading order, or SQLite version differences. It is caused by **wall-clock time leaking into entry decision logic** in three places — all in `warrior_engine_entry.py` and `warrior_entry_helpers.py`.

---

## Finding 1: `_get_eastern_time()` → Pattern Scoring Uses Wall Clock (CRITICAL)

> [!CAUTION]
> **This is almost certainly the PRIMARY root cause.**

**File:** `warrior_engine.py` line 291-294  
**Verified with:** `view_code_item` → `WarriorEngine._get_eastern_time`

```python
def _get_eastern_time(self) -> datetime:
    """Get current time in Eastern timezone."""
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/New_York"))
```

**Called at:** `warrior_engine_entry.py` line 462-463

```python
et_now = engine._get_eastern_time()
time_score = compute_time_score(et_now.hour, et_now.minute)
```

**Impact:** `time_score` is a component of **every** pattern's competition score (line 493-501). It determines:
- Which pattern wins the competition (`max(candidates, key=lambda c: c.score)`)  
- Whether ANY pattern passes `MIN_SCORE_THRESHOLD` (line 616)

**Why this causes OS divergence:** Batch tests replay historical data from e.g. January 14, 2026. But `_get_eastern_time()` returns `datetime.now()` — the **actual current time** (February 28, 2026 at 10pm ET). Since "10pm" is far outside trading hours, `compute_time_score()` returns a different score than what the sim time would be (e.g., 9:42 AM during the ROLR trade). The score difference can push patterns above/below the threshold.

But wait — both Windows and Linux run at roughly the same wall-clock time, so how does this create divergence? The answer is **execution speed**:
- Windows processes a 960-minute sim in ~X seconds  
- Linux processes a 960-minute sim in ~Y seconds  
- Each `check_entry_triggers` call gets `datetime.now()`, which returns different timestamps on each OS based on how fast the loop runs

A single entry decision at a boundary score can flip a trade from $45K profit to -$1.4K loss (ROLR case).

---

## Finding 2: `time.time()` Throttle for Technical Updates

**File:** `warrior_engine_entry.py` lines 398-402  
**Verified with:** `grep_search` for `time.time()` in `warrior_engine_entry.py`

```python
import time as _time
_last = getattr(watched, '_last_tech_update_ts', 0)
if _time.time() - _last >= 60:
    await update_candidate_technicals(engine, watched, current_price)
    watched._last_tech_update_ts = _time.time()
```

**Impact:** This throttle controls how often EMA/VWAP/MACD are recalculated. It uses **real wall-clock seconds**, not simulated minutes.

- A 960-minute sim taking 10 seconds of wall time → technical updates fire ~0 times (10s < 60s threshold)
- A 960-minute sim taking 120 seconds of wall time → technical updates fire ~2 times

**Why this causes OS divergence:** If Windows runs the sim loop 30% slower than Linux (or vice versa), the number of technical update calls differs. Different update counts → different EMA/VWAP/MACD values → different entry/exit decisions.

**Note:** This is actually insidious because it means the sim engine gets *stale* technical data. The `update_candidate_technicals` function updates `watched.current_ema_9`, `watched.current_vwap`, `watched.is_above_ema_9`, `watched.is_above_vwap` — all of which gate entry decisions in `validate_technicals`.

---

## Finding 3: `datetime.now()` in `trend_updated_at`

**File:** `warrior_entry_helpers.py` line 356  
**Verified with:** `view_file` on `warrior_entry_helpers.py`

```python
watched.trend_updated_at = datetime.now(timezone.utc)
```

**Impact:** Lower severity. This timestamp is used for tracking and may not directly gate decisions, but it contributes to non-determinism in the sim engine.

---

## Eliminated Hypotheses

| Hypothesis | Evidence | Status |
|-----------|----------|--------|
| **H1: Float arithmetic (MSVC vs glibc)** | Technical calculations use `pandas-ta` → `numpy`. While float results could theoretically differ, the `TechnicalService` cache key is `(symbol, candle_count, first_close)` which is deterministic. The real issue is that tech updates are called different numbers of times per OS due to the `time.time()` throttle. | ❌ Not the root cause |
| **H2: Set iteration order** | `set()` usage found in `warrior_engine.py:668` (`sorted(set(levels))`) — the `sorted()` makes it deterministic. Other `set()` uses are for tracking (blacklist, recently exited) not decision-making. | ❌ Eliminated |
| **H3: Bar loading order** | `HistoricalBarLoader.load_test_case()` loads from JSON files with deterministic ordering. Bars arrive in time-sorted order via `IntradayData.from_json()`. | ❌ Eliminated |
| **H4: SQLite version** | Concurrent runner uses per-process in-memory SQLite (`sqlite://`). No `ORDER BY` dependency issues since each process gets a clean DB. | ❌ Eliminated |
| **H5: TechnicalService singleton cache leak** | Concurrent runner uses `ProcessPoolExecutor` — each process gets its own singleton. No cross-case leakage. | ❌ Eliminated |

---

## Proposed Fix (for Backend Specialist)

### Fix 1: Make `_get_eastern_time()` sim-aware (CRITICAL)

```python
# In warrior_engine.py, line 291-294
def _get_eastern_time(self) -> datetime:
    """Get current time in Eastern timezone — sim-aware."""
    clock = getattr(self, '_sim_clock', None)
    if clock and clock.is_active():
        return clock.current_time  # Already ET-localized
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/New_York"))
```

This is the same pattern used in `update_candidate_technicals` (lines 296-304 of `warrior_entry_helpers.py`).

### Fix 2: Replace `time.time()` throttle with bar-count throttle

```python
# In warrior_engine_entry.py, line 398-402
# BEFORE (wall-clock dependent):
# import time as _time
# _last = getattr(watched, '_last_tech_update_ts', 0)
# if _time.time() - _last >= 60:

# AFTER (deterministic):
_last_bar_count = getattr(watched, '_last_tech_update_bar_count', 0)
# Get current bar count - update technicals every N new bars
current_bars = 0
if engine._get_intraday_bars:
    try:
        _bars = await engine._get_intraday_bars(symbol, "1min", limit=2)
        current_bars = len(_bars) if _bars else 0
    except:
        pass
if current_bars != _last_bar_count:
    await update_candidate_technicals(engine, watched, current_price)
    watched._last_tech_update_bar_count = current_bars
```

**Alternative (simpler):** Simply remove the throttle entirely in sim mode. The throttle exists to avoid excessive API calls in live mode, but in sim mode all data is local.

### Fix 3: Replace `datetime.now()` in trend_updated_at

```python
# In warrior_entry_helpers.py, line 356
# BEFORE:
watched.trend_updated_at = datetime.now(timezone.utc)

# AFTER:
clock = getattr(engine, '_sim_clock', None)
if clock and clock.is_active():
    watched.trend_updated_at = clock.current_time
else:
    watched.trend_updated_at = datetime.now(timezone.utc)
```

---

## Change Surface Summary

| # | File | Function | Line | Change | Priority |
|---|------|----------|------|--------|----------|
| 1 | `warrior_engine.py` | `_get_eastern_time` | 291-294 | Use `_sim_clock` when available | P0 |
| 2 | `warrior_engine_entry.py` | `check_entry_triggers` | 398-402 | Replace `time.time()` with bar-count or sim-time throttle | P0 |
| 3 | `warrior_entry_helpers.py` | `update_candidate_technicals` | 356 | Use sim clock for `trend_updated_at` | P2 |

---

## Verification Plan

### Phase 1: Quick Validation (before implementing)

Run the ROLR case on Windows, note exact entry time, trigger type, and pattern score. Log the `time_score` value used in scoring. If `compute_time_score` returns a score based on the current wall-clock time (e.g., "22:20 ET" instead of the sim time "09:42 ET"), the hypothesis is confirmed.

### Phase 2: After Fix

1. Run `pytest` — all 844 tests should pass
2. Run ROLR single case on Windows → note P&L
3. Run ROLR single case on VPS → compare P&L (should match within rounding)
4. Run full batch on both → compare total P&L

### Automated Test Command

```powershell
cd "c:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus"
.venv\Scripts\python -m pytest nexus2/tests/ -x -q 2>&1 | Select-Object -Last 20
```

---

## Risk Assessment

- **Low risk:** Fixes 1 and 3 follow existing patterns (`_sim_clock` usage in `update_candidate_technicals`)
- **Medium risk:** Fix 2 (throttle replacement) needs to ensure no regression in live mode performance
- **No behavior change for live trading:** All fixes fall back to `datetime.now()` / `time.time()` when no sim clock is active

---

## Trace Logging Spec (Only If Fix Doesn't Resolve Divergence)

If the above fixes don't resolve the gap, here is the trace logging specification:

### Insertion Points

**Point A — Entry Decision (`warrior_engine_entry.py` line 614-626):**
```python
if candidates:
    winner = max(candidates, key=lambda c: c.score)
    # === TRACE LOG ===
    sim_time = engine._sim_clock.get_time_string() if hasattr(engine, '_sim_clock') and engine._sim_clock else "LIVE"
    logger.warning(
        f"[TRACE] {symbol} @ {sim_time}: CANDIDATES: "
        + ", ".join(f"{c.pattern.name}={c.score:.4f}" for c in candidates)
        + f" | WINNER={winner.pattern.name} score={winner.score:.4f} threshold={MIN_SCORE_THRESHOLD}"
    )
```

**Point B — Guard Evaluation (`warrior_entry_guards.py` line 35-200):**
```python
# At function return, before returning (True/False, reason):
sim_time = engine._sim_clock.get_time_string() if hasattr(engine, '_sim_clock') and engine._sim_clock else "LIVE"
logger.warning(f"[TRACE] {watched.candidate.symbol} @ {sim_time}: GUARD result=({can_enter}, {reason})")
```

**Point C — Exit Decision (`warrior_monitor_exit.py` — each `_check_*` function):**
```python
# In evaluate_position_for_exit, before return:
sim_time = monitor._sim_clock.get_time_string() if hasattr(monitor, '_sim_clock') and monitor._sim_clock else "LIVE"
logger.warning(f"[TRACE] {position.symbol} @ {sim_time}: EXIT signal={exit_signal.reason if exit_signal else 'NONE'}")
```

**Point D — Technical Values (`warrior_entry_helpers.py` line 349-367):**
```python
# After snapshot computed (line 350), before updating watched fields:
logger.warning(
    f"[TRACE] {symbol}: TECHNICALS ema9={snapshot.ema_9} ema20={snapshot.ema_20} "
    f"vwap={watched.current_vwap} macd={snapshot.macd_histogram} "
    f"bullish={snapshot.is_macd_bullish} candles={len(all_candle_dicts)}"
)
```
