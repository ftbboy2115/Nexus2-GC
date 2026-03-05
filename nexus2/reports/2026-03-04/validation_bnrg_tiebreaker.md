# Tiebreaker Validation: BNRG/NPT Regression Root Cause

**Date:** 2026-03-04 15:00 ET  
**Validator:** Audit Validator (Tiebreaker)  
**Planner report:** `research_bnrg_regression.md`  
**Validator report:** `validation_bnrg_regression.md`

---

## Part 1: RVOL/Sim Disagreement — VERDICT

> [!IMPORTANT]
> **The VALIDATOR is correct.** `relative_volume` is hardcoded to `Decimal("10.0")` in sim,
> so the RVOL bypass (`rvol < 5.0`) never fires. The planner's root cause is wrong.

### Evidence

**Claim A (Planner):** `relative_volume` defaults to 0 in sim via `getattr(..., 0)`.

**Claim B (Validator):** `relative_volume` is hardcoded to `Decimal("10.0")` in `sim_context.py:283`.

**Verification:**

```
Verification Command: view_file sim_context.py lines 278-283
Actual Code:
    candidate = WarriorCandidate(
        symbol=symbol,
        name=symbol,
        price=Decimal(str(entry_price)),
        gap_percent=Decimal(str(gap_pct)),
        relative_volume=Decimal("10.0"),  # ← HARDCODED TO 10.0
```
**File:** [sim_context.py:278-283](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L278-L283)

**Additional evidence — sim routes also hardcode 10.0:**
```
warrior_sim_routes.py:651:  relative_volume=Decimal("10.0"),
warrior_sim_routes.py:800:  relative_volume=Decimal("10.0"),
```
**Verified with:** `grep_search` for `relative_volume` across `nexus2/` — all three sim paths use `Decimal("10.0")`.

**Trace through entry guards:**
```
warrior_entry_guards.py:294:  rvol = float(getattr(watched.candidate, 'relative_volume', 0) or 0)
warrior_entry_guards.py:295:  if rvol < 5.0:   # 10.0 < 5.0 → False → bypass NEVER fires
```
**File:** [warrior_entry_guards.py:294-295](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py#L294-L295)

**Result:** `float(Decimal("10.0"))` = `10.0`. `10.0 < 5.0` → **False**. The MACD gate runs normally in sim. The RVOL bypass has **zero effect** on batch test results.

### Why the Planner Was Wrong

The planner checked the test case JSON files (which don't contain `relative_volume`) and concluded the attribute is missing. But the planner missed that `load_case_into_context()` in `sim_context.py` explicitly creates a `WarriorCandidate` with `relative_volume=Decimal("10.0")` — the JSON file is loaded as bar data, not used directly as the candidate object.

| Agent | Claim | Correct? |
|-------|-------|----------|
| Planner | `relative_volume=0` in sim → RVOL bypass disables MACD gate for all tests | ❌ **WRONG** |
| Validator | `relative_volume=10.0` in sim → RVOL bypass never fires | ✅ **CORRECT** |

---

## Part 2: Actual Root Cause — Falling Knife Guard Extension

> [!CAUTION]
> **The falling knife guard extension (change #1) is the actual cause of BNRG/NPT regressions.**
> It creates a logic gap where entries pass the MACD tolerance gate but get blocked by a stricter
> `is_macd_bullish` check inside the falling knife guard.

### The Logic Gap

Two different MACD checks exist with different strictness:

| Check | Location | Condition | Strictness |
|-------|----------|-----------|------------|
| **MACD gate** | `warrior_entry_guards.py:302` | `histogram < tolerance` (default -0.02) | Lenient — allows slightly negative MACD |
| **`is_macd_bullish`** | `technical_service.py:47-51` | `histogram > 0` or crossover == "bullish" | **Strict** — requires positive histogram |

**The falling knife guard** at [warrior_entry_guards.py:357-363](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py#L357-L363) blocks when:
```python
if not is_above_20_ema and not macd_ok:   # macd_ok = snapshot.is_macd_bullish
    return True, reason  # FALLING KNIFE → blocked
```

**Evidence — `is_macd_bullish` property:**
```python
# File: technical_service.py:47-51
@property
def is_macd_bullish(self) -> bool:
    """Check if MACD is bullish (histogram > 0 or crossover)."""
    return self.macd_crossover == "bullish" or (
        self.macd_histogram is not None and self.macd_histogram > 0
    )
```
**File:** [technical_service.py:47-51](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/indicators/technical_service.py#L47-L51)

### The Regression Scenario

An entry with:
- MACD histogram = **-0.01** (within tolerance of -0.02 → passes MACD gate)
- Price **below 20 EMA** (in a pullback)
- `is_macd_bullish` = **False** (because -0.01 is not > 0)

| Step | Before Change | After Change |
|------|---------------|--------------|
| 1. MACD gate | ✅ PASS (histogram >= tolerance) | ✅ PASS (same) |
| 2. Falling knife guard | ⚪ **Not checked** (guard didn't exist for this pattern) | ❌ **BLOCKED** (below 20 EMA + MACD not bullish) |
| **Result** | Entry proceeds → profit | Entry blocked → missed profit = **regression** |

### What Changed (from `git diff`)

The diff shows both changes are **uncommitted working tree modifications**:

1. **New import:** `check_falling_knife`, `check_high_volume_red_candle` from `warrior_entry_helpers`
2. **New centralized guard** at line 160-166: `_check_falling_knife_guard()` runs for ALL patterns (previously only VWAP_BREAK checked this inline)
3. **New `_macd_gate_candles` storage** at line 320: `watched._macd_gate_candles = candles` — provides candle data to the falling knife guard (without this, the guard returns `True, ""` immediately)

**Key evidence from diff:**
```diff
+    # FALLING KNIFE + HIGH-VOL RED CANDLE GUARD (all patterns)
+    # Previously only protected VWAP_BREAK. Now centralized to guard ALL entries.
+    fk_result = _check_falling_knife_guard(engine, watched, current_price)
```

Before this change, `_check_falling_knife_guard` did not exist as a centralized guard. The falling knife check was inline inside the VWAP_BREAK pattern handler only. Extending it to **all patterns** means ORB, MICRO_PULLBACK, and other triggers now get falling-knife-checked for the first time.

### Two Blocking Paths in the New Guard

The new `_check_falling_knife_guard` has **two** blocking conditions:

1. **Falling knife** (line 358-363): below 20 EMA AND MACD not bullish
2. **High-volume red candle** (line 366-373): current candle is red with volume ≥ 1.5x average

Either condition can independently block entries that previously passed.

---

## Summary

| Question | Answer | Evidence |
|----------|--------|----------|
| Is RVOL=0 in sim? | **No** — it's `Decimal("10.0")` | `sim_context.py:283` |
| Does RVOL bypass fire in sim? | **No** — `10.0 < 5.0` is False | `warrior_entry_guards.py:295` |
| Which agent was right about RVOL? | **Validator** | See Part 1 |
| What's the actual root cause? | **Falling knife guard extension** | See Part 2 |
| Mechanism | MACD tolerance gate is lenient (allows slightly negative), but `is_macd_bullish` used by falling knife is strict (requires positive). Entries in pullbacks below 20 EMA with slightly negative MACD get caught. | `technical_service.py:47-51` vs `warrior_entry_guards.py:302` |

### Recommended Investigation for Fix

1. **Option A — Align strictness:** Make the falling knife guard use the same tolerance-based check as the MACD gate instead of `is_macd_bullish`
2. **Option B — Revert extension:** Only apply falling knife guard to VWAP_BREAK pattern (restore original scope)
3. **Option C — Remove tolerance gap:** Set MACD tolerance to 0 (no more slightly-negative allowance), which would make both checks equivalent but may cause other regressions

> [!IMPORTANT]
> The RVOL bypass code should still be removed as a separate cleanup. While it has no effect on sim results (RVOL=10.0), it IS architecturally wrong per warrior.md §8.1 — the MACD defensive gate should be unconditional. Removing it protects against future live-mode bugs if a stock has RVOL < 5x.

---

## Quality Rating: **HIGH**

Both the RVOL disagreement is settled with definitive code evidence, and the actual root cause is identified with a clear mechanical explanation supported by code tracing.
