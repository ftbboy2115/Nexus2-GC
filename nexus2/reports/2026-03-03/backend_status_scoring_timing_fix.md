# Backend Status: Scoring Data Timing Fix

**Date:** 2026-03-03 12:09 ET  
**Agent:** Backend Specialist  
**Task:** Make MACD histogram available at scoring time

---

## Status: ✅ COMPLETE

Batch test: **$355,038.66** (baseline: $355,038.66, net change: **$0.00**)  
All 39 cases unchanged — zero regression.

---

## Changes Made

### 1. `warrior_engine_types.py` — MODIFIED (+1 field)

- Added `cached_macd_histogram: Optional[float] = None` to `WatchedCandidate` (line 201)

### 2. `warrior_entry_helpers.py` — MODIFIED (+7 lines in `update_candidate_technicals`)

- After computing the snapshot (line 350), now caches `snapshot.macd_histogram` on `watched.cached_macd_histogram`
- Uses the same snapshot already computed for EMA — zero extra API calls or computation

### 3. `warrior_engine_entry.py` — MODIFIED (`check_entry_triggers` scoring block)

- Changed MACD source from `entry_snapshot` (only set after MACD gate) to `watched.cached_macd_histogram` (set by `update_candidate_technicals()` every 60s)
- Falls back to `entry_snapshot` if cached value isn't available

### 4. `warrior_entry_guards.py` — MODIFIED (`_check_macd_gate`)

- After computing MACD histogram, updates `watched.cached_macd_histogram` to keep scoring in sync with the gate
- Gate still fetches its own candles (50 vs 30) for higher fidelity

---

## Why $0 Change (Expected)

The MACD gate (`_check_macd_gate`) already blocks entries where `histogram < -0.02`. So entries that survive always have `histogram >= -0.02`. With `compute_macd_score()`:

| MACD Histogram | Old Score (None) | New Score | Delta | Weighted (×10%) |
|----------------|-----------------|-----------|-------|-----------------|
| `None` | 0.5 | N/A | — | — |
| `-0.02` | 0.5 | 0.2 | -0.3 | -0.03 (gate blocks) |
| `-0.01` | 0.5 | 0.4 | -0.1 | -0.01 |
| `0.00` | 0.5 | 0.4 | -0.1 | -0.01 |
| `0.01` | 0.5 | 0.6 | +0.1 | +0.01 |
| `0.10` | 0.5 | 0.8 | +0.3 | +0.03 |
| `0.30` | 0.5 | 1.0 | +0.5 | +0.05 |

Max total score impact = ±0.01 to ±0.05, with threshold at 0.40. No entries in the 39 batch cases sit close enough to the threshold to be pushed across.

---

## Open Questions Resolved

| # | Question | Answer |
|---|----------|--------|
| 1 | Does `update_candidate_technicals()` fetch 1-min candles? | **Yes** — line 283, `limit=30`. MACD comes from the same snapshot. |
| 2 | Will caching duplicate work with `_check_macd_gate()`? | **Partially** — gate uses `limit=50` for higher fidelity. Gate now updates cache too, keeping scoring in sync. |
| 3 | Are EMA/VWAP read by `score_pattern()`? | **Yes** — lines 504-519 compute `_ema_trend` and `_vwap_distance_pct` from cached values. These were already working. |

---

## Testable Claims

| # | Claim | File:Line | Verification |
|---|-------|-----------|-------------|
| 1 | `WatchedCandidate` has `cached_macd_histogram` field | `warrior_engine_types.py:201` | `Select-String "cached_macd_histogram" warrior_engine_types.py` |
| 2 | `update_candidate_technicals` caches MACD histogram | `warrior_entry_helpers.py:362` | `Select-String "cached_macd_histogram" warrior_entry_helpers.py` |
| 3 | Scoring reads from `cached_macd_histogram` first | `warrior_engine_entry.py:500` | `Select-String "cached_macd_histogram" warrior_engine_entry.py` |
| 4 | MACD gate updates cached value | `warrior_entry_guards.py:254` | `Select-String "cached_macd_histogram" warrior_entry_guards.py` |
| 5 | Batch test regression = $0 | This report | `python scripts/gc_quick_test.py --all --diff` |

---

## Real-World Impact

The fix ensures MACD data flows into scoring. While batch tests show $0 (expected due to gate pre-filtering), the real impact is in **LIVE mode**:

1. **Fading momentum**: Entries with near-zero MACD (0 to -0.01) now score 0.4 instead of 0.5 — small penalty for weak momentum
2. **Strong momentum**: Entries with histogram > 0.1 now score 0.8-1.0 instead of 0.5 — reward for conviction
3. **Re-entries**: After MACD gate passes, the histogram VALUE now differentiates quality. A barely-passing entry (histogram = -0.01) scores worse than a strong entry (histogram = 0.3)
4. **Pattern competition**: When multiple patterns trigger on the same symbol, MACD can now break ties in favor of the one with better momentum context
