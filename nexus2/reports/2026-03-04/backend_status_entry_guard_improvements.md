# Backend Status: Entry Guard Improvements

**Date:** 2026-03-04  
**Agent:** Backend Specialist  
**Handoff:** `nexus2/reports/2026-03-04/handoff_backend_entry_guard_improvements.md`  
**Strategy:** `.agent/strategies/warrior.md`

---

## Baseline (Before Changes)

```
Total P&L: $365,629.41 (Ross: $454,718.05)
Capture: 80.4% | Fidelity: 48.7%
Improved: 0/39 | Regressed: 0/39 | Unchanged: 39/39
```

---

## Fix #1: Falling Knife + Red Candle Guard → All Patterns

**Problem:** Falling knife and high-volume red candle guards only protected `VWAP_BREAK` pattern (1 of 11). Other patterns could enter during sharp selloffs.

**Solution:** Added centralized `_check_falling_knife_guard()` to `check_entry_guards()` in `warrior_entry_guards.py`. Runs after MACD gate, reuses the snapshot + candles already fetched by `_check_macd_gate()`.

### Changes Made

#### `warrior_entry_guards.py`

1. **Added import** (L20-23): `check_falling_knife` and `check_high_volume_red_candle` from `warrior_entry_helpers`

2. **Wired new guard** (L160-166): Added `_check_falling_knife_guard()` call after MACD gate in `check_entry_guards()`, with trade event logging via `tml.log_warrior_guard_block(symbol, "falling_knife", ...)`

3. **Store candles from MACD gate** (L308): Added `watched._macd_gate_candles = candles` so falling knife guard can reuse them without duplicate API calls

4. **New function `_check_falling_knife_guard()`** (L316-360):
   - Reads `watched.entry_snapshot` and `watched._macd_gate_candles` (set by MACD gate)
   - Falling knife check: below 20 EMA AND MACD negative (requires ≥20 candles)
   - High-volume red candle check: red bar with volume ≥ 1.5x average
   - FAIL-OPEN on missing data (MACD gate already passed)

### Testable Claims

| # | Claim | Verification |
|---|-------|-------------|
| 1 | `_check_falling_knife_guard` exists at `warrior_entry_guards.py:316-360` | `Select-String "def _check_falling_knife_guard" warrior_entry_guards.py` |
| 2 | Guard is called in `check_entry_guards()` after MACD gate | `Select-String "falling_knife_guard" warrior_entry_guards.py` → L163 |
| 3 | Guard uses `check_falling_knife` from helpers | `Select-String "from nexus2.domain.automation.warrior_entry_helpers import" warrior_entry_guards.py` |
| 4 | MACD gate stores candles on watched | `Select-String "_macd_gate_candles" warrior_entry_guards.py` → L308 |
| 5 | Trade events logged with guard_type `"falling_knife"` | `Select-String '"falling_knife"' warrior_entry_guards.py` → L165 |

---

## Fix #2: RVOL ≥ 5x Prerequisite for MACD Gate

**Problem:** MACD gate applied unconditionally regardless of RVOL level. Per `warrior.md §8.1 L322`: "Requires 5x RVOL as a prerequisite for MACD signals to be meaningful."

**Solution:** Added RVOL check in `_check_macd_gate()`. When `relative_volume < 5.0`, the MACD histogram gate is bypassed (MACD signals aren't meaningful at low volume). Histogram is still cached for scoring.

### Changes Made

#### `warrior_entry_guards.py`

1. **RVOL prerequisite check** (L291-302): 
   - Gets `rvol` from `watched.candidate.relative_volume`
   - If `rvol < 5.0`: logs bypass and skips to snapshot storage (no blocking)
   - If `rvol >= 5.0`: applies histogram check as before (with RVOL added to log message)

### Testable Claims

| # | Claim | Verification |
|---|-------|-------------|
| 6 | RVOL pull from `relative_volume` exists | `Select-String "relative_volume" warrior_entry_guards.py` → L294 |
| 7 | RVOL < 5.0 bypasses MACD gate | `Select-String "rvol < 5.0" warrior_entry_guards.py` → L295 |
| 8 | Bypass is logged with RVOL value | `Select-String "MACD gate BYPASSED" warrior_entry_guards.py` → L297 |
| 9 | MACD gate still fires when RVOL ≥ 5.0 | `Select-String "elif histogram" warrior_entry_guards.py` → L303 |
| 10 | RVOL is included in MACD block reason string | `Select-String "RVOL=" warrior_entry_guards.py` → L307 |

---

## Batch Test Results

> **NOTE:** Both fixes are combined in the current code state. To measure individual impact, test after rolling back Fix #2 first.

### Testing Protocol

```powershell
# Current state has BOTH fixes — run to get combined delta:
python scripts/gc_quick_test.py --all --diff

# To isolate Fix #1 impact: Comment out RVOL check (L291-302), re-run
# To isolate Fix #2 impact: Compare combined vs Fix #1-only
```

### Results (Pending User Execution)

| State | P&L | Δ from Baseline |
|-------|-----|-----------------|
| Baseline | $365,629.41 | — |
| After Fix #1 only | *pending* | *pending* |
| After Fix #1 + #2 | *pending* | *pending* |

---

## Files Modified

| File | Lines Changed | What |
|------|--------------|------|
| `warrior_entry_guards.py` | +4 (imports), +8 (guard call), +1 (candle store), +44 (new function), +12 (RVOL check) | Both fixes |
