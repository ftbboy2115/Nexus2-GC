# Validation Report: Guard Tuning Fixes

**Date:** 2026-02-24
**Validator:** Audit Validator
**Reference:** `nexus2/reports/2026-02-24/backend_status_guard_tuning.md`

---

## Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | `max_reentry_count` default = 5 | **PASS** | Line 122, `max_reentry_count: int = 5` |
| 2 | `pnl_above_threshold` removed from guards | **PASS** | 0 results from Select-String |
| 3 | `macd_histogram_tolerance` = -0.02 | **PASS** | Line 117, `macd_histogram_tolerance: float = -0.02` |
| 4 | MACD gate uses `histogram < tolerance` | **PASS** | Lines 214-228, `is_macd_bullish` fully removed |
| 5 | pytest passes (757+) | **PASS** | 757 passed, 4 skipped, 0 failures |

---

## Detailed Evidence

### Claim 1: `max_reentry_count` default is now 5

**Claim:** max_reentry_count changed from 3 to 5
**Verification Command:**
```powershell
Select-String -Path "nexus2\domain\automation\warrior_types.py" -Pattern "max_reentry_count"
```
**Actual Output:**
```
nexus2\domain\automation\warrior_types.py:122:    max_reentry_count: int = 5  # Max re-entries per symbol (5 = 6 total entries; Ross: 3-5 trades/stock per session)
```
**Result:** PASS
**Notes:** Default is 5, comment correctly notes this means 6 total entries.

---

### Claim 2: `pnl_above_threshold` removed from guard code

**Claim:** No `pnl_above_threshold` or `price_past_target` in warrior_entry_guards.py
**Verification Command:**
```powershell
Select-String -Path "nexus2\domain\automation\warrior_entry_guards.py" -Pattern "pnl_above_threshold|price_past_target"
```
**Actual Output:** *(no output — 0 matches)*
**Result:** PASS
**Notes:** 25% profit-check guard completely removed.

---

### Claim 3: `macd_histogram_tolerance` exists with default -0.02

**Claim:** macd_histogram_tolerance added to engine config
**Verification Command:**
```powershell
Select-String -Path "nexus2\domain\automation\warrior_engine_types.py" -Pattern "macd_histogram_tolerance"
```
**Actual Output:**
```
nexus2\domain\automation\warrior_engine_types.py:117:    macd_histogram_tolerance: float = -0.02  # Allow slightly negative histogram during pullbacks (Ross: MACD is "confirmation only")
```
**Result:** PASS
**Notes:** Correctly typed as float with appropriate comment referencing Ross methodology.

---

### Claim 4: MACD gate uses histogram comparison, not binary `is_macd_bullish`

**Claim:** Gate condition is `histogram < tolerance`, not `is_macd_bullish`
**Verification Command (part 1):**
```powershell
Select-String -Path "nexus2\domain\automation\warrior_entry_guards.py" -Pattern "is_macd_bullish" -Context 2,2
```
**Actual Output:** *(no output — 0 matches)*

**Verification Command (part 2):**
```powershell
Select-String -Path "nexus2\domain\automation\warrior_entry_guards.py" -Pattern "histogram.*tolerance|macd_histogram_tolerance" -Context 1,2
```
**Actual Output:**
```
  warrior_entry_guards.py:213:        histogram = snapshot.macd_histogram or 0
> warrior_entry_guards.py:214:        tolerance = engine.config.macd_histogram_tolerance  # default -0.02
  warrior_entry_guards.py:215:
> warrior_entry_guards.py:216:        if histogram < tolerance:
  warrior_entry_guards.py:217:            reason = (
  warrior_entry_guards.py:218:                f"MACD GATE - blocking entry "
> warrior_entry_guards.py:219:                f"(histogram={histogram:.4f} < tolerance={tolerance}, "
  warrior_entry_guards.py:220:                f"crossover={snapshot.macd_crossover}) - MACD too negative for entry"
  warrior_entry_guards.py:221:            )
  warrior_entry_guards.py:223:
> warrior_entry_guards.py:224:        # If histogram is between tolerance and 0, allow with info log
  warrior_entry_guards.py:225:        if histogram < 0:
  warrior_entry_guards.py:226:            logger.info(
  warrior_entry_guards.py:227:                f"[Warrior Entry] {symbol}: MACD slightly negative but within tolerance "
> warrior_entry_guards.py:228:                f"(histogram={histogram:.4f}, tolerance={tolerance}) - allowing entry"
  warrior_entry_guards.py:229:            )
```
**Result:** PASS
**Notes:** `is_macd_bullish` completely removed. Gate now uses `histogram < tolerance` with configurable threshold. Slightly negative histograms (between tolerance and 0) are allowed with an info log — good observability.

---

### Claim 5: All tests pass

**Claim:** pytest 757+ passed, 0 failures
**Verification Command:**
```powershell
python -m pytest nexus2/tests/ -x -q --tb=short 2>&1
```
**Actual Output:**
```
757 passed, 4 skipped, 3 deselected in 118.66s (0:01:58)
```
**Result:** PASS
**Notes:** 757 passed, 0 failures. 4 skipped and 3 deselected are expected (pre-existing).

---

## Overall Rating: **HIGH**

All 5 claims verified with evidence. Clean implementation, no regressions.

## Summary

All three guard tuning fixes are correctly implemented:
1. **Reentry limit** relaxed from 3 → 5 (allows more trades per Ross methodology)
2. **25% profit guard** fully removed (was blocking profitable re-entries)
3. **MACD gate** converted from binary to tolerance-based (allows slightly negative histograms)

No issues found. No rework needed.
