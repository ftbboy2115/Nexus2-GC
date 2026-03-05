# Research Report: BNRG & NPT Regressions from RVOL Prerequisite

**Date:** 2026-03-04 14:40 ET  
**From:** Backend Planner  
**Ref:** `handoff_planner_bnrg_regression.md`

---

## Executive Summary

> [!CAUTION]
> **The RVOL prerequisite completely disables the MACD gate for ALL sim test cases.**
> This is the root cause of both the BNRG (-$10,065) and NPT (-$5,614) regressions.

The bug is a combination of two issues:
1. **Missing data:** `relative_volume` is never populated in sim test candidates (defaults to `0`)
2. **Inverted logic:** The code treats low RVOL as reason to *skip* the MACD gate, when the strategy actually says low RVOL means MACD signals aren't reliable enough to *trade on*

---

## Root Cause Analysis

### The Code (lines 291-309 of `warrior_entry_guards.py`)

```python
# RVOL PREREQUISITE (warrior.md §8.1 L322):
# "Requires 5x RVOL as a prerequisite for MACD signals to be meaningful"
# When RVOL < 5x, MACD is noisy/unreliable — bypass the gate.
rvol = float(getattr(watched.candidate, 'relative_volume', 0) or 0)
if rvol < 5.0:
    logger.info(
        f"[Warrior Entry] {symbol}: MACD gate BYPASSED — "
        f"RVOL {rvol:.1f}x < 5x prerequisite ..."
    )
    # Still store snapshot/candles for falling knife guard downstream
elif histogram < tolerance and snapshot.macd_crossover != "bullish":
    # ... BLOCK the entry ...
    return False, reason
```

### Problem 1: `relative_volume` is never set in sim

| Path | Sets `relative_volume`? |
|------|------------------------|
| Live scanner (`unified_scanner.py`) | ✅ Yes, from FMP/Polygon data |
| Sim routes — interactive (`/sim/load_case`) | ❌ **No** — candidate not created this way |
| `sim_context.run_batch_concurrent` | ❌ **No** — never touches `relative_volume` |
| Test case JSON files | ❌ **No** — only has `symbol`, `date`, `bars`, `premarket`, `continuity_bars`, `source` |

**Result:** `getattr(watched.candidate, 'relative_volume', 0) or 0` → always `0.0` in sim.

**Verified with:**
```powershell
python -c "import json; d=json.load(open('nexus2/tests/test_cases/intraday/ross_bnrg_20260211.json')); print(list(d.keys()))"
# Output: ['symbol', 'date', 'premarket', 'continuity_bars', 'bars', 'source']
```

### Problem 2: Logic is inverted vs. strategy intent

**What warrior.md §8.1 (line 322) says:**
> "Requires **5x RVOL** as a prerequisite for MACD signals to be meaningful"

**Correct interpretation:** MACD is only a reliable indicator when volume is high (5x+). Below 5x, MACD readings are noisy — so MACD *entry signals* (bullish crossovers) shouldn't be trusted. This is about the *offensive* use of MACD.

**What the code does:** Below 5x, the MACD *defensive gate* (blocking negative-MACD entries) is bypassed. This allows entries during MACD-negative conditions — the exact opposite of the strategy's intent.

**The strategy's MACD defensive rule is unconditional:**
- Line 320: `"Red light, green light" — MACD negative = DO NOT TRADE`
- Line 333: `MACD is a **hard binary gate** for entries (negative = don't trade)`

There is NO exception for low-volume conditions. The 5x RVOL prerequisite applies to MACD *signals* (entry triggers), not to the MACD *gate* (defensive blocker).

---

## Impact: Which Fix Caused Each Regression

Since `relative_volume = 0` in ALL sim tests, the RVOL prerequisite (`rvol < 5.0` → True for all) means the MACD gate is bypassed for **every single test case**. This is equivalent to removing the MACD gate entirely.

| Case | Before | After | Delta | Cause |
|------|--------|-------|-------|-------|
| BNRG | +$361 | -$9,705 | -$10,065 | MACD gate disabled → negative-MACD entries allowed |
| NPT | +$10,591 | +$4,977 | -$5,614 | MACD gate disabled → negative-MACD entries allowed |

Both regressions are from the **RVOL prerequisite change** (change #2), not the falling knife extension (change #1).

> [!IMPORTANT]
> The falling knife guard extension (change #1) uses `snapshot` and `candles` stored by `_check_macd_gate()`. Since the MACD gate still *runs* (it just doesn't block), the data for the falling knife guard is still available. So change #1 is functioning correctly — it's change #2 that's catastrophic.

---

## Recommended Fix

**Remove the RVOL bypass from the MACD gate entirely.** The MACD defensive gate ("red light = don't trade") should ALWAYS apply, regardless of RVOL.

**File:** [warrior_entry_guards.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py#L291-L309)

**Change:** Delete lines 291-301 (the RVOL bypass block). The existing `elif` at line 302 becomes a plain `if`:

```python
# Before (BROKEN):
rvol = float(getattr(watched.candidate, 'relative_volume', 0) or 0)
if rvol < 5.0:
    logger.info(...)  # BYPASSES the gate!
elif histogram < tolerance and snapshot.macd_crossover != "bullish":
    return False, reason

# After (FIXED):
if histogram < tolerance and snapshot.macd_crossover != "bullish":
    return False, reason
```

If RVOL should influence entry decisions, it should be used as:
- A **scoring factor** (higher RVOL = higher score)
- A **prerequisite for MACD-based *entry triggers*** (not the defensive gate)
- A separate concern in `validate_technicals()` or the scoring system

---

## Open Questions for Clay

1. **Should we also populate `relative_volume` in sim test candidates?** The scanner sets this from FMP/Polygon. For sim replay, we could either hardcode a reasonable default (e.g., 10x since these are scanner-qualifying stocks) or compute it from the test case bar data.

2. **Should RVOL factor into scoring at all?** The warrior.md mentions RVOL only in §8.1 as a MACD prerequisite. It's already a scanner filter (stocks must have notable volume to appear on scanners). Making it a scoring factor is reasonable but not documented in the strategy.
