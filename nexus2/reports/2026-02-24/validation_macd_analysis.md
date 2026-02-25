# Validation Report: MACD Block Analysis Script

**Validator:** Testing Specialist
**Date:** 2026-02-24
**Reference:** `nexus2/reports/2026-02-24/backend_status_macd_analysis.md`
**Script:** `scripts/analyze_macd_blocks.py`

---

## Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | Syntax valid: `py_compile.compile()` succeeds | **PASS** | `python -c "import py_compile; py_compile.compile(r'scripts\analyze_macd_blocks.py', doraise=True); print('COMPILE SUCCESS')"` → output: `COMPILE SUCCESS` |
| 2 | `parse_macd_from_reason()` extracts histogram and crossover from reason string | **PASS** | Tested regex against actual format from `warrior_entry_guards.py:217-220`. Command: `python -c "import re; HISTOGRAM_RE = re.compile(r'histogram=(-?[\d.]+)'); CROSSOVER_RE = re.compile(r'crossover=(\w+)'); reason='MACD GATE - blocking entry (histogram=-0.0847 < tolerance=-0.02, crossover=neutral)...'; hm=HISTOGRAM_RE.search(reason); cm=CROSSOVER_RE.search(reason); print(hm.group(1), cm.group(1))"` → output: `-0.0847 neutral` |
| 3 | `classify_block()` returns A/B/C correctly | **PASS** | Tested via import: `classify_block(-0.15,[])→A`, `classify_block(-0.05,[-0.03,-0.04,-0.02,-0.01,-0.05])→B`, `classify_block(-0.05,[-0.03,0.01,-0.02,-0.01,-0.05])→C`, `classify_block(None,[])→UNKNOWN`. Edge: `-0.10→B` (strict `<` threshold), `-0.1001→A`. All match documented behavior. |
| 4 | `compute_macd_trajectory()` uses `HistoricalBarLoader.load_test_case()` + `pandas_ta.macd()` | **PASS** | Code inspection: Line 113 calls `loader.load_test_case(case_id)`, line 118 calls `data.get_bars_up_to(blocked_time, include_continuity=True)`, line 143 calls `ta.macd(df["close"], fast=12, slow=26, signal=9)`. Verified `HistoricalBarLoader.load_test_case()` exists at `historical_bar_loader.py:292` and `IntradayData.get_bars_up_to()` exists at line 142 with `include_continuity` parameter. |
| 5 | Counterfactual cross-reference matches by `case_id` + `blocked_time` + `guard == "macd"` | **PASS** | Code inspection lines 366-382: Builds lookup by `case_id` (line 363: `counterfactual_lookup[case_id] = details`), then matches by `detail.get("guard") == "macd"` (line 371) AND `detail.get("blocked_time") == b.get("blocked_time")` (line 372). Exact match on all 3 fields confirmed. |
| 6 | `--from-file` flag skips batch run and loads cached results | **PASS** | Code inspection: Line 228: `from_file = "--from-file" in sys.argv`. Line 239: `if from_file and os.path.exists(BATCH_CACHE)` loads from `_macd_batch_cache.json`. Lines 260-263: fresh runs cache results to same file. Health check skipped when `from_file` (line 231: `if not from_file`). |
| 7 | Report output saved to `nexus2/reports/2026-02-24/analysis_macd_blocks.md` | **PASS** | Code inspection line 575: `report_path = os.path.join(REPORT_DIR, "analysis_macd_blocks.md")` where `REPORT_DIR = os.path.join(NEXUS_PATH, "nexus2", "reports", "2026-02-24")`. Line 576-581 writes markdown report with header, timestamp, and code block. |

---

## Additional Observations

### Minor Note (non-blocking)
- The backend status report references `warrior_entry_guards.py:218-220` — the actual file is at `nexus2/domain/automation/warrior_entry_guards.py` (not `domain/warrior/`). The line numbers 217-220 are accurate for the reason string format. This is cosmetic only; the regex correctly matches the actual format.

### Edge Case Behavior (Claim 3)
- `classify_block(-0.10, [])` returns `B` (not `A`) because threshold uses strict `<` comparison. This is **consistent** with the claim which states "A when histogram < -0.10" — exactly -0.10 is NOT less than -0.10. Behavior is correct.

---

## Overall Rating

**HIGH** — All 7 claims verified. No rework needed.
