# Backend Status: MACD Block Analysis Script

**Agent:** Backend Specialist  
**Date:** 2026-02-24  
**Reference:** `nexus2/reports/2026-02-24/spec_macd_block_analysis.md`

---

## Summary

Created standalone analysis script `scripts/analyze_macd_blocks.py` that:
1. Runs a full batch test via the API
2. Parses MACD histogram values from guard block reason strings
3. Classifies blocks into three buckets (A/B/C)
4. Computes MACD trajectory (5-bar history) for Bucket C classification
5. Cross-references with existing counterfactual P&L analysis
6. Generates text-based histogram distribution and bucket summary table
7. Outputs report to both stdout and markdown file

## Files Changed

| # | File | Change |
|---|------|--------|
| 1 | **[NEW]** `scripts/analyze_macd_blocks.py` | Standalone analysis script |

**No production code modifications.**

## Testable Claims

1. **Syntax valid:** `py_compile.compile('scripts/analyze_macd_blocks.py')` succeeds
2. **`parse_macd_from_reason()`** correctly extracts histogram and crossover from:
   ```
   MACD GATE - blocking entry (histogram=-0.0847 < tolerance=-0.02, crossover=neutral)...
   ```
   - Verified regex: `histogram=(-?[\d.]+)` matches the format at `warrior_entry_guards.py:218-220`
3. **`classify_block()`** returns:
   - `"A"` when histogram < -0.10
   - `"C"` when -0.10 <= histogram < -0.02 AND any of last 5 bars had histogram > 0
   - `"B"` when -0.10 <= histogram < -0.02 AND no recent positive histogram
4. **`compute_macd_trajectory()`** uses `HistoricalBarLoader.load_test_case()` + `pandas_ta.macd()` to compute 5-bar MACD history at block time
5. **Counterfactual cross-reference** matches blocks by `case_id` + `blocked_time` + `guard == "macd"` against `guard_analysis.details[]`
6. **`--from-file` flag** skips batch run and loads cached results from `_macd_batch_cache.json`
7. **Report output** saved to `nexus2/reports/2026-02-24/analysis_macd_blocks.md`

## Usage

```powershell
# Fresh batch run (requires Nexus server running on port 8000)
python scripts/analyze_macd_blocks.py

# Re-analyze from cached batch results
python scripts/analyze_macd_blocks.py --from-file
```

## Architecture Notes

- Follows `gc_batch_diagnose.py` patterns (same `fetch_json()`, same API endpoint)
- Trajectory computation is offline — no production code changes
- Only computes trajectories for B/C candidates (skips Bucket A for performance)
- Groups trajectory computation by `case_id` to minimize bar reloading
