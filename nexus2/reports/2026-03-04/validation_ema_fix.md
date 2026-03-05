# Validation Report: EMA Bar Reversal Fix + Sanity Checks

**Date:** 2026-03-04 12:36 ET  
**Validator:** Audit Validator  
**Source:** `backend_status_ema_fix.md`  
**Handoff:** `handoff_validator_ema_fix.md`

---

## Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | Bar reversal removed | **PASS** | Line 1195: `closes_chronological = closes` — no `[::-1]` |
| 2 | EMA sanity check (100x/0.01x) | **PASS** | Lines 1725-1732: ratio check, WARNING log, `ctx.ema_200_value = None` |
| 3 | `adjusted=true` in Polygon daily bars | **PASS** | `polygon_adapter.py:530`: `params={"limit": limit, "sort": "asc", "adjusted": "true"}` |
| 4 | Misleading comment fixed | **PASS** | Line 1183: `# Extract closing prices — Polygon returns sorted "asc" (oldest first)` |
| 5 | Health metrics never gated entries | **PASS** | `compute_position_health` called only from `warrior_positions.py` (API route) and `indicator_service.py` (definition). Zero calls from entry/monitor/scanner. |
| 6 | gc_quick_test.py new case separation | **PASS** | `diff_results()` separates `new_cases` list (line 204), prints "NEW CASES" header (line 285), excludes from improved/regressed counts (line 222). |
| 7 | Batch test: 0 regressions | **FAIL** | 2/39 regressed: MLEC (-$1,422.34), MNTS (-$617.76) |

---

## Detailed Evidence

### Claim 1: Bar reversal removed

**Verification Command:** `view_file` on `warrior_scanner_service.py:1166-1210`  
**Actual Output (line 1194-1195):**
```python
            # Polygon returns bars sorted ascending (oldest first) — already chronological
            closes_chronological = closes
```
**Result:** PASS — No `[::-1]` reversal anywhere in `_get_200_ema` (lines 1166-1210).  
**Secondary check:** `grep_search` for `[::-1]` in `warrior_scanner_service.py` returned **0 results**.

---

### Claim 2: EMA sanity check exists

**Verification Command:** `grep_search` for `ema_ratio` in `warrior_scanner_service.py`  
**Actual Output:**
```
Line 1725: ema_ratio = float(ctx.ema_200_value) / float(ctx.last_price)
Line 1726: if ema_ratio > 100 or ema_ratio < 0.01:
Line 1730: f"Ratio: {ema_ratio:.0f}x — likely stale/unadjusted data, ignoring"
```
**Verification Command:** `grep_search` for `200 EMA SANITY FAIL`  
**Actual Output:**
```
Line 1728: f"200 EMA SANITY FAIL | {ctx.symbol} | "
```
**Verification Command:** `view_file` on lines 1720-1745  
**Actual Output (line 1732):**
```python
                ctx.ema_200_value = None  # Discard garbage value
```
**Result:** PASS — Sanity check at lines 1725-1733 with 100x/0.01x thresholds, WARNING log, and `None` assignment.

---

### Claim 3: `adjusted=true` added

**Verification Command:** `grep_search` for `adjusted` in `polygon_adapter.py`  
**Actual Output:**
```
Line 530: params={"limit": limit, "sort": "asc", "adjusted": "true"}
```
**Result:** PASS

---

### Claim 4: Misleading comment fixed

**Verification Command:** `view_file` on `warrior_scanner_service.py:1183`  
**Actual Output:**
```python
            # Extract closing prices — Polygon returns sorted "asc" (oldest first)
```
**Result:** PASS — Old comment "most recent first" replaced with accurate description.

---

### Claim 5: Health metrics never gated entries

**Verification Command:** `grep_search` for `compute_position_health` in `nexus2/**/*.py`  
**Actual Output:**
```
indicator_service.py:235  — def compute_position_health(   [DEFINITION]
indicator_service.py:373  — ...calls compute_position_health()   [DOCSTRING]
indicator_service.py:390  — return self.compute_position_health(  [INTERNAL CALL]
warrior_positions.py:137  — health = indicator_service.compute_position_health(  [API ROUTE]
warrior_positions.py:184  — health = indicator_service.compute_position_health(  [API ROUTE]
```
**Secondary check:** `grep_search` for `compute_position_health` in `warrior_engine_entry.py` and `warrior_monitor.py` — **0 results**.  
**Result:** PASS — `compute_position_health` is never called from entry, monitor, or scanner code. Only from API routes (dashboard display).

---

### Claim 6: gc_quick_test.py new case separation

**Verification Command:** `view_file` on `scripts/gc_quick_test.py:184-296`  
**Actual Output (key lines):**
```python
Line 198: new_count = 0
Line 220-223: if not in_baseline and in_current:
                 new_count += 1
                 new_cases.append((cid, new_pnl))
Line 239: comparable = improved + regressed + unchanged  # excludes new_count
Line 258: print(f"  New cases: {new_count} (not in baseline — excluded from diff)")
Line 285: print(f"\n  NEW CASES (not in baseline — no diff applicable):")
```
**Result:** PASS — New cases tracked separately, excluded from improved/regressed/unchanged counts, displayed in own section.

---

### Claim 7: Batch test — 0 regressions

**Verification Command:** `python scripts/gc_quick_test.py --all --diff`  
**Actual Output:**
```
  DIFF vs BASELINE (40 cases, 39 comparable)
  Baseline saved: 2026-03-02 22:01:05
  Improved:  0/39
  Regressed: 2/39
  Unchanged: 37/39
  New cases: 1 (not in baseline — excluded from diff)
  Net change (comparable only): $-2,040.10

  - ross_mlec_20260213           | $   -578.33 | $ -2,000.67 | $ -1,422.34
  - ross_mnts_20260209           | $-15,502.64 | $-16,120.40 | $   -617.76
```
**Result:** **FAIL** — Report claimed 0/39 regressions, but actual batch test shows **2/39 regressed** (MLEC and MNTS) with a net loss of **-$2,040.10**.

> [!WARNING]
> The baseline used was saved `2026-03-02 22:01:05`. Other code changes made between the specialist's test run and now (e.g., entry guard fixes, negative AI tiebreaker, offering false-positive fix) may have caused these regressions — they may not be attributable to the EMA fix itself. However, the claim as stated ("0 regressions") does not match current reality.

---

## Overall Rating

**MEDIUM** — 6/7 claims verified. Claim 7 (zero regressions) fails: 2 cases regressed since the baseline. The regressions may be caused by other changes merged after the EMA fix, but the claim as written is not reproducible now.

### Recommended Action
- Investigate whether MLEC and MNTS regressions are caused by the EMA fix or by subsequent changes (entry guard fixes, negative AI tiebreaker, etc.)
- If caused by other changes, re-run batch test against a pre-EMA-fix baseline to isolate
