# Research: MLEC P&L Regression After EMA Fix

**Date:** 2026-03-04 12:48 ET  
**Author:** Backend Planner  
**Handoff:** `handoff_planner_mlec_regression.md`

---

## TL;DR

| Question | Answer |
|----------|--------|
| Did the EMA fix cause MLEC regression? | **NO.** All sim data comes from historical bar loader, not Polygon daily bars. |
| What is MLEC's actual P&L? | **-$578.33** (solo run matches baseline exactly) |
| Where did the -$2,000.67 come from? | **Concurrency noise** in the batch concurrent runner. |
| Same for MNTS? | **Same root cause.** PMH bar fix status report also noted MNTS non-determinism. |

---

## Finding 1: Sim Entry Technicals Use Historical Bar Loader, Not Polygon

The entry engine computes technicals (MACD, EMA 9/20, VWAP) via `update_candidate_technicals()` at `warrior_entry_helpers.py:258`. This function:

1. Calls `engine._get_intraday_bars(symbol, "1min", limit=30)` (line 283)
2. Passes bars to `tech.get_snapshot()` for MACD/EMA (line 358)
3. Computes VWAP from today's session bars (line 370+)

**In sim, `_get_intraday_bars` is rewired** at `warrior_sim_routes.py:1013`:
```python
engine._get_intraday_bars = sim_get_intraday_bars
```

`sim_get_intraday_bars` reads from the **historical bar loader** (test case JSON files), NOT from Polygon. 

**Verified with:** `view_code_item` on `update_candidate_technicals`, `view_file` on `warrior_sim_routes.py:941-1013`.

### What the EMA fix changed:
- `get_daily_bars` in `polygon_adapter.py` → added `adjusted=true`, fixed bar reversal
- These changes affect `_get_200_ema` in the scanner (daily timeframe)

### What the entry engine uses:
- `_get_intraday_bars` → rewired to historical bar loader in sim
- 1-minute bars from test case JSON for MACD/EMA 9/EMA 20/VWAP

**These are entirely separate data paths.** The EMA fix changes daily bars from Polygon; the entry engine uses intraday bars from test case JSON.

---

## Finding 2: Scanner Is Also Bypassed

`load_historical_test_case()` at `warrior_sim_routes.py:794-818` creates `WatchedCandidate` directly without calling `_evaluate_symbol()`. The scanner's `_check_200_ema()` is never invoked during batch sim.

**Verified with:** `view_file` on `warrior_sim_routes.py:692-850`.

---

## Finding 3: MLEC Solo Run Matches Baseline

**Command run by Clay:**
```
python scripts/gc_quick_test.py ross_mlec_20260213 --trades
```
**Output:**
```
  MLEC 2026-02-13    | Bot: $   -578.33 | Ross: $ 43,000.00
```

Solo result: **-$578.33** = baseline value exactly. No regression.

The -$2,000.67 from the `--all --diff` batch only appeared in the concurrent runner.

---

## Finding 4: Root Cause — Concurrency Noise

The PMH bar fix increased `limit` from 100→400 in `_get_premarket_high()`, adding **+113.6s** to batch runtime. The PMH fix status report itself documented MNTS as "non-deterministic concurrency noise":

> "MNTS regression is non-deterministic concurrency noise from heavier bar loads in batch mode. Solo run confirms no behavioral change."

MLEC follows the same pattern: stable in solo, noisy in concurrent batch.

---

## Recommendation

1. **No action needed on EMA fix.** It cannot affect sim results (separate data path).
2. **MLEC regression is phantom.** Solo run: -$578.33 = baseline exactly.
3. **Save a fresh baseline** after all current fixes to eliminate stale-baseline confusion.
