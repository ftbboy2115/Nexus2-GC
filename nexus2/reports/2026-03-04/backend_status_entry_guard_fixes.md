# Backend Status: Entry Guard Bug Fixes (MOBX)

**Date:** 2026-03-04 09:49 ET  
**Agent:** Backend Specialist  
**Reference:** `handoff_backend_entry_guard_fixes.md`

---

## Results

| Metric | Value |
|--------|-------|
| Improved | 1/40 (ross_npt_20260303: $0 → $10,590.75) |
| Regressed | 0/40 |
| Net change | **+$10,590.75** |
| New total P&L | $365,629.41 (80.4% capture) |
| Runtime | 90.2s (-12.1s from baseline) |

---

## Bug 1: PMH Derivation from Polygon Bars (CRITICAL)

**Files modified:** `warrior_engine.py`

### Change 1a: `_get_premarket_high()` rewritten (lines 606-666)

- **PRIMARY:** Now derives PMH from Polygon 1-min intraday bars (already available via `_get_intraday_bars`). Filters bars before 9:30 AM ET, takes `max(high)`.
- **SECONDARY FALLBACK:** FMP `get_premarket_high()` retained as fallback only.
- **REMOVED:** `day_high` quote fallback (semantically incorrect — it's dynamic intraday HOD, not frozen PMH).
- **FAIL-CLOSED:** Returns `None` when no source has pre-market data, with WARNING log.

### Change 1b: `session_high` fallback removed (lines 558-580)

- When `_get_premarket_high()` returns `None`, `pmh` is set to `Decimal("0")` instead of `candidate.session_high`.
- `pmh=0` ensures PMH-break triggers **never fire** for candidates without valid PMH data (fail-closed).
- Previously: fell back to `session_high` (Polygon `day.h`), which declines as the stock fades, causing false PMH-break triggers.

### Testable Claims

| # | Claim | File:Line | Grep Pattern |
|---|-------|-----------|--------------|
| 1 | PMH derived from Polygon bars before FMP | `warrior_engine.py:615` | `Derive from Polygon 1-min intraday bars` |
| 2 | No `day_high` fallback exists | `warrior_engine.py` | Should NOT contain `day_high` in `_get_premarket_high` |
| 3 | No `session_high` in PMH assignment | `warrior_engine.py:575` | `pmh=pmh,` (not `pmh or candidate.session_high`) |
| 4 | Fail-closed log when no PMH | `warrior_engine.py:666` | `No PMH available from any source` |

---

## Bug 2: Price Floor Guard at Entry (HIGH)

**File modified:** `warrior_entry_guards.py`

### Change: Price floor guard added (lines 134-142)

- Added after per-symbol fail limit check, before MACD gate.
- Reads `min_price` from scanner settings (default `$1.50`).
- Blocks entry if `current_price < scanner_min_price`.
- Handles both `int/float` and `Decimal` types for `min_price`.
- Logs via TML `price_floor` guard block event.

### Testable Claims

| # | Claim | File:Line | Grep Pattern |
|---|-------|-----------|--------------|
| 5 | Price floor guard exists | `warrior_entry_guards.py:134` | `PRICE FLOOR` |
| 6 | Uses scanner min_price setting | `warrior_entry_guards.py:136` | `_get_scanner_setting("min_price"` |
| 7 | Guard blocks below floor | `warrior_entry_guards.py:140` | `Below scanner min_price` |

---

## Bug 3: Paper Mode Cooldown Gap (HIGH)

**File modified:** `warrior_entry_guards.py`

### Change: Cooldown logic unified (lines 157-193)

**Before (broken):**
- Live cooldown: `if not sim_mode` → skipped in paper mode
- Sim cooldown: `if sim_mode and _sim_clock` → no `_sim_clock` in paper mode
- Result: paper mode skipped BOTH paths

**After (fixed):**
- Three-way branching: `has_sim_clock` determines path
- `sim_mode=True WITH _sim_clock` → historical replay → use sim clock
- `everything else (live + paper)` → use wall clock
- Both paths use `settings.live_reentry_cooldown_minutes` (unified from separate `_reentry_cooldown_minutes`)

### Testable Claims

| # | Claim | File:Line | Grep Pattern |
|---|-------|-----------|--------------|
| 8 | Unified cooldown logic | `warrior_entry_guards.py:157` | `unified: live, paper, and sim modes` |
| 9 | Paper mode uses wall clock | `warrior_entry_guards.py:183` | `LIVE + PAPER MODE: Use wall clock` |
| 10 | Sim uses settings (not instance var) | `warrior_entry_guards.py:178` | `settings.live_reentry_cooldown_minutes` |
| 11 | No `not engine.monitor.sim_mode` gate | `warrior_entry_guards.py` | Should NOT contain `not engine.monitor.sim_mode` in cooldown section |

---

## Verification

```
python scripts/gc_quick_test.py --all --diff
  Improved:  1/40
  Regressed: 0/40
  Unchanged: 39/40
  Net change:  $+10,590.75
  New total P&L: $365,629.41  (Ross: $454,718.05)
  Capture: 80.4%  (Fidelity: 48.7%)
  Runtime: 90.2s  (baseline: 102.3s, delta: -12.1s)
```

NPT improvement: the Polygon PMH derivation provided a valid PMH where FMP previously returned `None`, enabling correct PMH-break entries.
