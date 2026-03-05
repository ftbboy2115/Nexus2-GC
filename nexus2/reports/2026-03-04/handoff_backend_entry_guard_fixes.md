# Backend Specialist Handoff: Fix Entry Guard Bugs (MOBX)

**Date:** 2026-03-04 09:41 ET  
**From:** Coordinator  
**To:** Backend Specialist  
**Research:** `nexus2/reports/2026-03-04/research_mobx_entry_bugs.md`  
**Output:** `nexus2/reports/2026-03-04/backend_status_entry_guard_fixes.md`

---

## Context

MOBX 2026-03-04 entered two losing trades at $1.36/$1.37 when PMH was ~$1.70. Three bugs allowed this.

---

## Bug 1: PMH Falls Back to HOD (CRITICAL)

**File:** `warrior_engine.py` lines 561-565

**Problem:** When `_get_premarket_high()` returns None, code falls back to `candidate.session_high` — which is Polygon's intraday HOD (`day.h`). This is dynamic and declines as the stock fades. Result: "PMH break" triggers at $1.36 when real PMH was $1.70.

**Fix:** Derive PMH from Polygon intraday bars (already available via `_get_intraday_bars`). Filter for bars before 9:30 AM ET and take max(high). Only use FMP as a secondary fallback.

```python
# Pseudocode:
bars = await self._get_intraday_bars(symbol, "1min", limit=100)
pre_market_bars = [b for b in bars if b.timestamp < market_open_930]
pmh = max(b.high for b in pre_market_bars) if pre_market_bars else None
```

**Important:** PMH must be frozen at scan time and NOT updated as HOD changes.

---

## Bug 2: No Price Floor at Entry (HIGH)

**Problem:** Scanner checks `min_price=$1.50` at scan time, but the entry path never rechecks. MOBX was scanned at ~$1.80, then entered at $1.36 (9% below floor).

**Fix:** Add a price floor check in entry guards (`warrior_entry_guards.py`):

```python
# Before any entry execution:
if current_price < scanner_settings.min_price:
    logger.warning(f"[Entry Guard] {symbol}: Price ${current_price} below min ${scanner_settings.min_price}")
    return False  # Block entry
```

The scanner settings min_price ($1.50) needs to be accessible at entry time. Check the planner's report for where to wire this.

---

## Bug 3: Paper Mode Cooldown Gap (HIGH)

**Problem:** Paper mode sets `sim_mode=True`, which skips the live cooldown guard in `warrior_entry_guards.py`. The sim cooldown guard requires `_sim_clock` which may not exist in paper mode. Result: both paths bypassed, no cooldown enforced.

**Evidence:** MOBX Trade 1 exited at 11:31, Trade 2 entered at 11:33 — only 2 minutes apart. Should be 10-minute cooldown.

**Fix:** Ensure paper mode uses the live cooldown path (wall clock), not the sim path. Check `sim_mode` vs "is this a batch test" — paper mode is NOT a batch test, it should use live cooldowns.

---

## Verification

```powershell
# Run batch test — expect $0 regression (bugs 1+2 only affect live, bug 1 may affect batch if FMP returns None for any case)
python scripts/gc_quick_test.py --all --diff
```

---

## CLI Reference (verified)
```
gc_quick_test.py [cases...] --all --diff --trades --save --list
```
