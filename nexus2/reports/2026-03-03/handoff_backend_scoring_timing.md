# Backend Specialist Handoff: Fix Scoring Data Timing

**Date:** 2026-03-03 11:59 ET  
**From:** Coordinator  
**To:** Backend Specialist  
**Output:** `nexus2/reports/2026-03-03/backend_status_scoring_timing_fix.md`

---

## Problem

The dynamic scoring factors added in the previous task default to neutral (0.5) because MACD histogram isn't available at scoring time. This is a **code ordering issue**:

1. `update_candidate_technicals()` runs every 60s → populates EMA, VWAP on `watched` ✅
2. `check_entry_triggers()` → calls `score_pattern()` via `add_candidate()` — **MACD not available here** ❌
3. `_check_macd_gate()` runs AFTER scoring → creates `entry_snapshot` with MACD histogram

Because of this ordering, batch tests show $0 change — the dynamic scoring isn't actually being exercised.

## Task

Make MACD histogram (and any other missing technical data) available at scoring time by either:

**Option A (preferred):** Have `update_candidate_technicals()` in `warrior_entry_helpers.py` also compute and cache MACD histogram on the `watched` object — similar to how it already caches `is_above_ema_9`, `current_vwap`, etc.

**Option B:** Move the MACD computation from `_check_macd_gate()` to before the scoring block in `check_entry_triggers()`, and store the result for both scoring and the gate to use.

## Key Files

| File | What to check |
|------|--------------|
| `nexus2/domain/automation/warrior_entry_helpers.py` | `update_candidate_technicals()` — already caches EMA/VWAP, add MACD |
| `nexus2/domain/automation/warrior_entry_guards.py` | `_check_macd_gate()` — currently computes MACD, creates `entry_snapshot` |
| `nexus2/domain/automation/warrior_engine_entry.py` | `check_entry_triggers()` → where `add_candidate()` reads dynamic factors |
| `nexus2/domain/automation/warrior_engine_types.py` | `WatchedCandidate` — may need `cached_macd_histogram` field |

## Open Questions (Investigate)

1. Does `update_candidate_technicals()` already fetch 1-min candles? If so, computing MACD from those same candles should be trivial.
2. Will caching MACD in `update_candidate_technicals()` duplicate work with `_check_macd_gate()`? If so, have the gate check the cached value first.
3. Are EMA and VWAP values actually being read by `score_pattern()` in the current implementation, or do they also default to neutral?

## Verification

```powershell
python scripts/gc_quick_test.py --all --diff
```

After this fix, the batch test should show **non-zero P&L change** — the dynamic scoring will now be active. This is the real test of whether the scoring improvements help.

> [!IMPORTANT]
> If the P&L change is significantly NEGATIVE (>5% drop), investigate which cases regressed and why before committing. The dynamic factors should improve or be neutral on most cases.
