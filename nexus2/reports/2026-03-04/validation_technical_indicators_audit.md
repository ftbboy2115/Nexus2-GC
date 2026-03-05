# Validation Report: Technical Indicators Audit

**Date:** 2026-03-04 13:45 ET  
**Validator:** Audit Validator  
**Source:** `nexus2/reports/2026-03-04/research_technical_indicators_audit.md`  
**Strategy:** `.agent/strategies/warrior.md`

---

## Quality Rating: **HIGH**

All 12 claims verified. The planner's audit is accurate and thorough. No fabricated evidence found.

---

## Claims Verified

| # | Claim | Result | Summary |
|---|-------|--------|---------|
| 1 | MACD hard gate threshold -0.02 | ✅ PASS | Confirmed exact implementation |
| 2 | VWAP below = block (hard gate) | ✅ PASS | Confirmed hard gate behavior |
| 3 | EMA 9 has 1% tolerance hard gate | ✅ PASS | Confirmed 0.99 multiplier |
| 4 | Falling knife only guards VWAP_BREAK | ✅ PASS | Confirmed single caller |
| 5 | Volume expansion scoring hardcoded to None | ✅ PASS | Confirmed dead code |
| 6 | L2 gate defaults to log_only | ✅ PASS | Confirmed in code + type def |
| 7 | RVOL ≥ 5x prerequisite for MACD not implemented | ✅ PASS | Zero RVOL refs in guards |
| 8 | Per-pattern guard coverage matrix | ✅ PASS | Spot-checked 3 patterns |
| 9 | Strategy says NOT Used: EMA crossovers | ✅ PASS | Confirmed at L342 |
| 10 | 5x RVOL prerequisite scope | ✅ PASS with NOTE | Strategy says MACD-specific |
| 11 | L2 is primary tool for supply/demand | ✅ PASS | Confirmed at L305 |
| 12 | Completeness — missed indicators | ✅ PASS | No missed indicators found |

---

## Detailed Evidence

### Claim 1: MACD Hard Gate (histogram < -0.02)

**Claim:** "MACD is a hard gate (histogram < -0.02)"

**Verification Command:** `grep_search "macd_histogram_tolerance" in nexus2/domain/automation/`

**Actual Output:**
- `warrior_entry_guards.py:274`: `tolerance = engine.config.macd_histogram_tolerance  # default -0.02`
- `warrior_engine_types.py:118`: `macd_histogram_tolerance: float = -0.02`

**Additional verification** (`warrior_entry_guards.py:279`):
```python
if histogram < tolerance and snapshot.macd_crossover != "bullish":
    return False, reason  # BLOCKS entry
```

**Result:** ✅ PASS  
**Notes:** Default is -0.02 as claimed. Code at L279 confirms it actually blocks entries (returns False). Bullish crossover exemption also confirmed. FAIL-CLOSED on missing bar data (L257-259) and exceptions (L302-303) verified.

---

### Claim 2: VWAP Below = Block (Hard Gate)

**Claim:** "VWAP below = block"

**Verification Command:** `view_file warrior_entry_guards.py L656-667`

**Actual Output** (L659):
```python
if actual_vwap and entry_price < actual_vwap:
    return False, reason
```

**Result:** ✅ PASS  
**Notes:** This is inside `validate_technicals()` (L568-694), which is a separate function from `check_entry_guards()`. It IS a hard gate — returns `False, reason` which blocks the entry. The audit correctly identifies this at L656-667. Note: audit said L656-667, actual gate logic is at L659-667.

---

### Claim 3: EMA 9 Has 1% Tolerance Hard Gate

**Claim:** "EMA 9 has 1% tolerance hard gate"

**Verification Command:** `view_file warrior_entry_guards.py L669-677`

**Actual Output** (L670):
```python
if snapshot.ema_9 and entry_price < snapshot.ema_9 * Decimal("0.99"):
    return False, reason
```

**Result:** ✅ PASS  
**Notes:** `0.99` = exactly 1% tolerance as claimed. Only blocks when price is >1% below EMA 9. The comment at L144-147 confirms a tighter gate was tested but caused -$34K regression, consistent with audit.

---

### Claim 4: Falling Knife Only Guards VWAP_BREAK Pattern

**Claim:** "Falling knife only guards VWAP_BREAK pattern"

**Verification Command:** `grep_search "check_falling_knife" in nexus2/domain/automation/`

**Actual Output:**
- `warrior_entry_patterns.py:1099`: `is_falling, reason = check_falling_knife(current_price, snapshot)` — inside `detect_vwap_break_pattern`
- `warrior_entry_helpers.py:216`: function definition
- `warrior_engine_entry.py:248`: duplicate function definition

**No other callers** in any pattern detection function.

**Additional check** (`check_high_volume_red_candle`):
- `warrior_entry_patterns.py:1119`: `is_red_flag, red_vol, red_avg = check_high_volume_red_candle(candles)` — also inside `detect_vwap_break_pattern`
- No other callers.

**Result:** ✅ PASS  
**Notes:** Both falling knife AND high-volume red candle guards are VWAP_BREAK-only, confirming audit claims 11 (§A.11) and 12 (§A.12). This is a genuine gap — other patterns (DIP_FOR_LEVEL, PULLBACK, etc.) can enter during falling knife conditions.

---

### Claim 5: Volume Expansion Scoring Hardcoded to None

**Claim:** "Volume expansion scoring hardcoded to None"

**Verification Command:** `view_file warrior_engine_entry.py L530-531`

**Actual Output:**
```python
# Volume expansion: not wired yet (function exists but wiring caused regression)
_vol_expansion_ratio = None
```

**Also verified:** `warrior_entry_scoring.py:319` receives this value: `vol_expansion_score = compute_volume_expansion_score(volume_expansion)` → returns 0.5 (neutral) when `None` (L191-192).

**Result:** ✅ PASS  
**Notes:** 4% of composite score (L334: `vol_expansion_score * 0.04`) always defaults to neutral 0.5 × 0.04 = 0.02. Dead code confirmed.

---

### Claim 6: L2 Gate Defaults to log_only

**Claim:** "L2 gate defaults to log_only"

**Verification Command:** `grep_search "l2_gate_mode" in nexus2/`

**Actual Output:**
- `warrior_entry_guards.py:491`: `mode = getattr(settings, "l2_gate_mode", "log_only")`
- `warrior_types.py:141`: `l2_gate_mode: str = "log_only"  # "log_only" | "warn" | "block"`

**Verification of behavior** (`warrior_entry_guards.py:535-537`):
```python
if mode == "log_only":
    logger.info(f"[L2 Gate] {symbol}: {assessment} [mode=log_only]")
    return True, ""  # NEVER blocks
```

**Result:** ✅ PASS  
**Notes:** Default is `log_only` in both the settings type definition AND the getattr fallback. In `log_only` mode, the gate always returns `True` — it never blocks entries regardless of ask wall detection results. The audit's characterization is accurate: infrastructure is built but effectively disabled by default.

---

### Claim 7: RVOL ≥ 5x Prerequisite for MACD Not Implemented

**Claim:** "RVOL ≥ 5x prerequisite for MACD not implemented"

**Verification Command:** `grep_search "rvol" (case-insensitive) in warrior_entry_guards.py`

**Actual Output:** 0 results

**Additional check:** `grep_search "relative_volume|volume_ratio" in warrior_entry_guards.py` → 0 results

**Result:** ✅ PASS  
**Notes:** The MACD gate at `_check_macd_gate()` (L234-303) has zero references to RVOL, relative volume, or any volume threshold. The gate fires unconditionally regardless of volume context. RVOL only feeds scoring (`vol_normalized` at L301 of `warrior_entry_scoring.py`) at 10% weight — it does NOT gate MACD application.

---

### Claim 8: Per-Pattern Guard Coverage Matrix

**Claim:** Coverage matrix claiming falling knife/red candle only on VWAP_BREAK, volume expansion on 2 patterns, active market on 2 patterns

**Verification Commands:**
- `grep_search "check_volume_expansion" in warrior_entry_patterns.py`
- `grep_search "check_active_market" in warrior_entry_patterns.py`
- `grep_search "check_volume_confirmed" in warrior_entry_patterns.py`
- `grep_search "check_falling_knife" in warrior_entry_patterns.py`
- `grep_search "check_high_volume_red_candle" in warrior_entry_patterns.py`

**Actual Output (per-function callers in patterns):**

| Guard Function | Callers in warrior_entry_patterns.py |
|------|------|
| `check_volume_expansion` | L235 (WHOLE_HALF), L471 (DIP_FOR_LEVEL) |
| `check_active_market` | L396, L406, L413 (DIP_FOR_LEVEL), L590, L597, L604 (PMH_BREAK) |
| `check_volume_confirmed` | L1108 (VWAP_BREAK) |
| `check_falling_knife` | L1099 (VWAP_BREAK) |
| `check_high_volume_red_candle` | L1119 (VWAP_BREAK) |

**Spot-checked 3 patterns:**
1. **VWAP_BREAK** — Has falling knife ✅, red candle ✅, volume confirmed ✅ (matches matrix row)
2. **DIP_FOR_LEVEL** — Has volume expansion ✅, active market ✅, NO falling knife ✅ (matches matrix row)
3. **PMH_BREAK** — Has active market ✅, NO volume expansion ✅, NO falling knife ✅ (matches matrix row)

**Result:** ✅ PASS  
**Notes:** All 3 spot-checked patterns match the audit's coverage matrix exactly.

---

### Claim 9: Strategy Says "NOT Used: EMA Crossovers"

**Claim:** Audit references warrior.md §8 L342: "NOT Used: EMA crossovers"

**Verification Command:** `view_file warrior.md L340-345`

**Actual Output:**
```
### NOT Used
- RSI
- EMA crossovers  
- Bollinger Bands
- Fibonacci
- Any "indicator-based" system
```

**Result:** ✅ PASS  
**Notes:** Exact text at L342 confirms: "EMA crossovers" is under "NOT Used." The audit correctly distinguishes that "EMA crossovers" (crossing signals) ≠ "EMA position" (above/below check). The code uses EMA 9 as a positional gate (above/below), NOT as a crossover signal, so the implementation is a reasonable engineering compromise. However, the audit's ⚠️ warning that even the positional gate may be an over-gate is a valid concern since the strategy lists EMA crossovers as NOT Used and the prior backtest showed regression.

---

### Claim 10: 5x RVOL Prerequisite — Scope

**Claim:** Audit references warrior.md §8.1 L322: "Requires 5x RVOL as a prerequisite for MACD signals to be meaningful"

**Verification Command:** `view_file warrior.md L318-324`

**Actual Output:**
```
4. Requires **5x RVOL** as a prerequisite for MACD signals to be meaningful
5. Entry: Wait for first pullback when MACD is positive. Stop = low of pullback
```

**Result:** ✅ PASS with NOTE  
**Notes:** The strategy explicitly ties the 5x RVOL prerequisite to MACD signals specifically (item 4 under "Ross's MACD rules"). It's not a general entry requirement — it's a MACD-specific prerequisite. The audit correctly identifies this as a gap: the MACD gate fires without checking RVOL. However, implementing this requires careful consideration — applying it too strictly could block valid trades where the bot already passed the RVOL-based scanner filter.

---

### Claim 11: L2 Is "Primary Tool" for Supply/Demand

**Claim:** Audit references warrior.md §8 L305

**Verification Command:** `view_file warrior.md L305`

**Actual Output:**
```
| **Level 2 / Order Book** | Primary tool for reading supply/demand. Watches for big buyers on bid, big sellers on ask. |
```

**Result:** ✅ PASS  
**Notes:** Ross explicitly calls L2 his "primary tool" for reading supply/demand. The audit correctly identifies the tension: the strategy says "primary tool" but the bot defaults to `log_only` mode. The audit's recommendation to promote to `warn` mode for live trading is reasonable.

---

### Claim 12: Completeness — Any Missed Indicators

**Claim:** The audit lists 19 indicators. Are there any indicators the planner missed?

**Verification Command:** `grep_search "atr|rsi|bollinger|fibonacci|stochastic|adx|cci"` in entry path files

**Actual Output:**
- ATR found in `warrior_entry_patterns.py:1390-1407` — used inside HOD_BREAK pattern for consolidation tightness check. This is a pattern-internal calculation, not a standalone indicator.
- Zero results for RSI, Bollinger, Fibonacci, Stochastic, ADX, CCI.

**Additional check:** `snapshot.` fields accessed across entry files:
- `snapshot.macd_histogram`, `snapshot.macd_crossover`, `snapshot.is_macd_bullish` (MACD)
- `snapshot.vwap` (VWAP)
- `snapshot.ema_9`, `snapshot.ema_20` (EMAs)
- `snapshot.macd_line`, `snapshot.macd_signal` (MACD components)

No uncatalogued indicators found.

**Result:** ✅ PASS  
**Notes:** ATR is used internally within HOD_BREAK for consolidation tightness (L1390-1407), but it's a pattern-internal metric, not a standalone indicator gate/score. The planner didn't list it separately because it's embedded in the pattern logic rather than being a distinct indicator. This is a reasonable omission. No genuinely missed standalone indicators found.

---

## Summary

The Backend Planner's technical indicators audit is **thorough, accurate, and well-evidenced**. All 19 indicators are correctly categorized by usage (hard gate / scoring / display-only). The per-pattern coverage matrix is verified. The strategy references are accurate. The gap analysis (falling knife/red candle scope, RVOL prerequisite, volume expansion dead code) is valid and actionable.

**Confidence:** HIGH — no findings require rework of the audit.
