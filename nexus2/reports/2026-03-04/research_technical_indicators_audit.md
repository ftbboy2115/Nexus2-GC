# Research: Technical Indicators Audit — Warrior Entry Pipeline

**Date:** 2026-03-04  
**Agent:** Backend Planner  
**Handoff:** `nexus2/reports/2026-03-04/handoff_planner_technical_audit.md`  
**Strategy:** `.agent/strategies/warrior.md` (418 lines, verified)

---

## 1. Indicator Matrix

| # | Indicator | Computed | Hard Gate | Scoring | Display-Only | Strategy Ref | Recommendation |
|---|-----------|----------|-----------|---------|--------------|-------------|----------------|
| 1 | **MACD (histogram)** | ✅ | ✅ Hard gate | ✅ 10% weight | — | §8.1 L304, L313-338 | ✅ Correct — matches "red light green light" |
| 2 | **VWAP (above/below)** | ✅ | ✅ Hard gate | ✅ 6% weight | — | §8 L303, §2.1 L53 | ✅ Correct — matches "primary bias indicator" |
| 3 | **EMA 9 (above/below)** | ✅ | ✅ Hard gate (1% tolerance) | ✅ 8% weight (via EMA trend) | — | §8 L342 "NOT Used: EMA crossovers" | ⚠️ **Possible over-gate** — see §A.3 |
| 4 | **EMA 20** | ✅ | ❌ (indirect via falling knife) | ✅ 8% weight (via EMA trend) | — | §8 L342 "NOT Used: EMA crossovers" | ⚠️ Same concern as EMA 9 |
| 5 | **EMA 200** | ✅ (scanner only) | ❌ | ❌ | ✅ Dashboard | §1 Pillar 5 L19 "room to 200 MA" | ✅ Correct — scanner/display only |
| 6 | **Volume Expansion (bar-level)** | ✅ | ✅ Per-pattern gate (2 of 11 patterns) | ❌ (hardcoded None) | — | §8.1 L322 "5x RVOL prerequisite" | 🔴 **Gap** — scoring not wired; see §A.6 |
| 7 | **Spread (bid/ask)** | ✅ | ✅ Hard gate | ✅ 1.5% weight | — | §2.1 L48 "check spread", §8 L311 | ✅ Correct |
| 8 | **L2 / Order Book** | ✅ (when enabled) | ⚙️ Configurable (default: log_only) | ❌ | Log-only by default | §8 L305 "primary tool" | ⚠️ **Severely underused** — see §A.8 |
| 9 | **Volume Confirmed (breakout)** | ✅ | ✅ Per-pattern (VWAP_BREAK only) | ❌ | — | §8 L310 "confirms interest" | ⚠️ Only used in VWAP_BREAK |
| 10 | **Active Market** | ✅ | ✅ Per-pattern (DIP_FOR_LEVEL, PMH_BREAK) | ❌ | — | §7 L266 "cold market" | ⚠️ Not applied to all patterns |
| 11 | **Falling Knife** | ✅ | ✅ Per-pattern (VWAP_BREAK only) | ❌ | — | Derived: below 20 EMA + MACD neg | 🔴 **Gap** — should guard ALL patterns |
| 12 | **High-Vol Red Candle** | ✅ | ✅ Per-pattern (VWAP_BREAK only) | ❌ | — | §3.3 L128-129 "big red candles" | 🔴 **Gap** — should guard ALL patterns |
| 13 | **Position Health Composite** | ✅ (API only) | ❌ | ❌ | ✅ Dashboard | N/A | ✅ Correct — display only |
| 14 | **SPY Context** | ❌ Not implemented | ❌ | ❌ | ❌ | §7 L267-282 (market temp) | 🟡 **Not in strategy** as a direct gate |
| 15 | **RVOL (scanner-level)** | ✅ (scanner) | ❌ (at entry) | ✅ 10% weight | — | §8.1 L322 "requires 5x RVOL" | 🔴 **5x RVOL pre-req missing** — see §A.15 |
| 16 | **Blue Sky (52-week high)** | ✅ | ❌ | ✅ +0.10 bonus | — | §1 Pillar 5 L34 "Blue sky setup" | ✅ Correct |
| 17 | **Re-entry Decay** | ✅ | ✅ (after N losses) | ✅ 8% weight | — | §4.3 L172-174 "3-5 trades" | ✅ Correct |
| 18 | **Price Extension (from PMH)** | ✅ | ❌ | ✅ 4% weight | — | Derived from distance | ✅ Reasonable |
| 19 | **Time Score** | ✅ | ❌ (6 AM hard cutoff only) | ✅ 4% weight | — | §9.3 L363-370 | ✅ Correct |

---

## 2. Detailed Evidence per Indicator

### A.1 — MACD (Hard Gate + Scoring)

**Strategy says:**
> "Red light, green light — MACD negative = DO NOT TRADE" (§8.1 L320)
> "MACD crossover from negative → positive IS a valid entry signal" (§8.1 L321)

**Implementation:**

**Hard Gate:**
**File:** `warrior_entry_guards.py:234-303` (`_check_macd_gate`)
```python
histogram = snapshot.macd_histogram or 0
tolerance = engine.config.macd_histogram_tolerance  # default -0.02
if histogram < tolerance and snapshot.macd_crossover != "bullish":
    return False, reason  # BLOCKS entry
```
- FAIL-CLOSED: blocks when no bar data (L251, L257-259, L302-303)
- Tolerance-based: allows slightly negative histogram (> -0.02) during pullbacks
- Bullish crossover exemption: allows entry when MACD is crossing from negative to positive

**Scoring:**
**File:** `warrior_entry_scoring.py:70-97` (`compute_macd_score`)
- Weight: 10% of composite score (L330)
- Histogram ≥ 0.3 → 1.0, ≥ 0.1 → 0.8, ≥ 0.01 → 0.6, near zero → 0.4, negative → 0.2/0.0

**Verdict:** ✅ Correctly implements Ross's binary gate. Tolerance-based approach is a reasonable engineering choice that a future audit should tune via backtest.

---

### A.2 — VWAP (Hard Gate + Scoring)

**Strategy says:**
> "Primary bias indicator. Above = bullish, below = bearish. Break of VWAP = entry trigger." (§8 L303)

**Implementation:**

**Hard Gate:**
**File:** `warrior_entry_guards.py:656-667` (`validate_technicals`)
```python
if actual_vwap and entry_price < actual_vwap:
    return False, f"REJECTED - below VWAP..."
```
- Uses session-filtered candles for accurate VWAP (excludes yesterday's continuity bars)
- Does NOT set `entry_triggered=True` — allows re-check when price recovers

**Scoring:**
**File:** `warrior_entry_scoring.py:147-175` (`compute_vwap_score`)
- Weight: 6% of composite score (L333)
- Below VWAP ≥ -2% → 0.0, just above → 0.6, 1-5% above → 1.0, very extended → 0.4

**Verdict:** ✅ Correctly implements Ross's "above VWAP = bullish" rule. The VWAP_BREAK pattern explicitly handles the "break of VWAP" entry trigger (§2.1 L53).

---

### A.3 — EMA 9 (Hard Gate + Scoring) ⚠️

**Strategy says:**
> "NOT Used: EMA crossovers" (§8 L342)
> Ross uses EMA 9 visually for trend context but does NOT list it as a gate or crossover signal.

**Implementation:**

**Hard Gate:**
**File:** `warrior_entry_guards.py:669-677` (`validate_technicals`)
```python
if snapshot.ema_9 and entry_price < snapshot.ema_9 * Decimal("0.99"):
    return False, f"REJECTED - below 9 EMA..."
```
- 1% tolerance zone — only blocks when price is >1% below EMA 9

**Scoring:**
**File:** `warrior_entry_scoring.py:100-121` (`compute_ema_trend_score`)
- Weight: 8% of composite score (L331)
- Above both EMA 9 and 20 = 1.0, above 20 only = 0.5, below both = 0.2

> [!WARNING]
> **The strategy file explicitly lists "EMA crossovers" under "NOT Used" (§8 L342).**
> However, the code at line 144-147 of `warrior_entry_guards.py` notes:
> ```
> # NOTE: EMA trend is handled by scoring penalty (not a hard gate).
> # The MACD gate + falling knife guard already block truly dead trends.
> # A hard EMA gate was tested but caused -$34K regression
> ```
> The 1% tolerance gate + scoring penalty is an engineering compromise. The scoring use is defensible (trend context), but the hard gate at EMA 9 was tested and proven harmful at tighter thresholds.

**Verdict:** ⚠️ Consider removing the EMA 9 hard gate entirely and relying only on scoring penalty. The strategy doesn't mandate it, and prior backtesting showed regression.

---

### A.4 — EMA 20 (Scoring + Falling Knife)

**Implementation:**
- NOT a standalone hard gate
- Used in `check_falling_knife` (L270-277): below 20 EMA AND MACD negative = block
- Feeds EMA trend scoring via `update_candidate_technicals`

**Verdict:** ✅ Appropriate — EMA 20 is used contextually (falling knife), not as a standalone gate.

---

### A.5 — EMA 200 (Scanner → Display Only)

**Strategy says:**
> "Daily chart: Float rotation, 200 MA position, recent history" (§8 L309, §1 Pillar 5)

**Implementation:**
**File:** `warrior_scanner_service.py:1166` (`_get_200_ema`)
**File:** `warrior_scanner_service.py:1722` (`ctx.ema_200_value = self._cached(...)`)
**File:** `indicator_service.py:235` (`compute_position_health`) — display API only
**File:** `warrior_positions.py:137,184` — API routes for dashboard rendering

**Verified:** Zero calls from entry engine, monitor, or guards.

**Verdict:** ✅ Correct — EMA 200 is a scanner-phase metric for stock selection (Pillar 5). It correctly does NOT gate individual entries.

---

### A.6 — Volume Expansion (Partial Guard, Scoring NOT Wired) 🔴

**Strategy says:**
> "Requires 5x RVOL as a prerequisite for MACD signals to be meaningful" (§8.1 L322)
> "Volume: Relative volume vs 50-day average. Confirms interest." (§8 L310)

**Implementation:**

**Guard function:**
**File:** `warrior_entry_helpers.py:62` (`check_volume_expansion`)
- Compares current bar volume to average of prior bars (configurable min_expansion, default 3.0x)

**Used as pattern guard in only 2 of 11 patterns:**
- `detect_whole_half_anticipatory` (`warrior_entry_patterns.py:235`) — min 1.5x
- `detect_dip_for_level` (`warrior_entry_patterns.py:471`) — min 3.0x (1.5x for re-entries)

**NOT used in:** PMH_BREAK, PULLBACK, BULL_FLAG, INVERTED_HS, CUP_HANDLE, HOD_BREAK, ORB, MICRO_PULLBACK

**Scoring:**
**File:** `warrior_engine_entry.py:530-531`
```python
# Volume expansion: not wired yet (function exists but wiring caused regression)
_vol_expansion_ratio = None
```
**File:** `warrior_entry_scoring.py:178-205` (`compute_volume_expansion_score`) — function exists but receives `None`

> [!CAUTION]
> **Volume expansion scoring is defined but permanently receives `None`.**
> The comment says "wiring caused regression." This means 4% of the composite score always defaults to 0.5 (neutral).
> The `check_volume_expansion` guard also only applies to 2 of 11 patterns.

**Verdict:** 🔴 **Gap.** Volume expansion should at minimum be wired to scoring. The function exists at `warrior_entry_scoring.py:178` and the scoring weight is already allocated (4%). The guard should also apply to more patterns (especially PMH_BREAK and HOD_BREAK).

---

### A.7 — Spread / Bid-Ask (Hard Gate + Scoring)

**Strategy says:**
> "Check spread (bid/ask)" (§2.1 L48)
> "Tight = good liquidity. Wide = dangerous." (§8 L311)

**Implementation:**

**Hard Gate:**
**File:** `warrior_entry_guards.py:363-450` (`_check_spread_filter`)
- Blocks when spread % > `max_entry_spread_percent` (config)
- Progressive EoD tightening: Phase 1 (4-6 PM), Phase 2 (6-7 PM)
- FAIL-CLOSED: blocks on invalid bid/ask data

**Scoring:**
- Weight: 1.5% of composite (L337)

**Verdict:** ✅ Correct and thorough.

---

### A.8 — L2 / Order Book (Configurable, Default Log-Only) ⚠️

**Strategy says:**
> "Primary tool for reading supply/demand. Watches for big buyers on bid, big sellers on ask." (§8 L305)

**Implementation:**

**File:** `warrior_entry_guards.py:453-560` (`_check_l2_gate`)
- Three modes: `log_only` (default), `warn`, `block`
- Checks: ask walls within proximity, spread quality
- FAIL-OPEN: L2 errors never block trades

> [!WARNING]
> **Ross calls L2 his "primary tool" — the bot defaults to log_only mode.**
> The L2 infrastructure exists (ask wall detection, spread quality) but never actually blocks entries by default. This is a deliberate engineering choice (L2 data quality is inconsistent), but it means a key part of Ross's methodology is effectively disabled.

**Verdict:** ⚠️ Consider enabling `warn` mode at minimum for live trading. The infrastructure is already built.

---

### A.9 — Volume Confirmed (Breakout Bar Volume)

**Implementation:**
**File:** `warrior_entry_helpers.py:14` (`check_volume_confirmed`)
- Used ONLY in `detect_vwap_break_pattern` (L1108)
- Simple check: current bar vol ≥ average OR > prior bar

**Not used in:** WHOLE_HALF, PMH_BREAK, PULLBACK, ABCD, BULL_FLAG

**Verdict:** ⚠️ Similar volume confirmation logic exists inline in other patterns (HOD_BREAK L1435, CUP_HANDLE L1291, INVERTED_HS L1201) but not consistently applied.

---

### A.10 — Active Market Check

**Implementation:**
**File:** `warrior_entry_helpers.py:148` (`check_active_market`)
- Checks: minimum bars, avg volume per bar, max time gaps between bars
- Used in: `detect_dip_for_level` (L396-413), `detect_pmh_break` (L590-604)
- **NOT used in:** WHOLE_HALF, PULLBACK, BULL_FLAG, VWAP_BREAK, INVERTED_HS, CUP_HANDLE, HOD_BREAK

**Verdict:** ⚠️ Should consider applying to all patterns that use intraday bars.

---

### A.11 — Falling Knife Guard 🔴

**Implementation:**
**File:** `warrior_engine_entry.py:248-282` / `warrior_entry_helpers.py:216` (`check_falling_knife`)
- Logic: below 20 EMA AND MACD negative
- **Used ONLY in `detect_vwap_break_pattern`** (`warrior_entry_patterns.py:1099`)

> [!CAUTION]
> **The falling knife guard protects only VWAP_BREAK entries.**
> Other patterns (DIP_FOR_LEVEL, WHOLE_HALF, PMH_BREAK, etc.) can enter during falling knife conditions.
> The MACD gate catches MACD-negative cases, but the combined "below 20 EMA + MACD weakening (but within tolerance)" scenario is unguarded in 10 of 11 patterns.

**Verdict:** 🔴 **Gap.** Should be a universal guard or at minimum applied to all patterns that trade during weak conditions (DIP_FOR_LEVEL, PULLBACK).

---

### A.12 — High-Volume Red Candle Guard 🔴

**Implementation:**
**File:** `warrior_engine_entry.py:285-326` / `warrior_entry_helpers.py:99` (`check_high_volume_red_candle`)
- Logic: current bar is red (close < open) AND volume ≥ 1.5x average
- **Used ONLY in `detect_vwap_break_pattern`** (`warrior_entry_patterns.py:1119`)

**Strategy says:**
> "High-volume red candles: Multiple large-body red candles = sellers in control" (§3.3 L128-129)

**Verdict:** 🔴 **Gap.** Ross uses this as a general exit signal. At minimum it should warn/block on all new entry patterns, not just VWAP_BREAK.

---

### A.13 — Position Health Composite (Display Only)

**Implementation:**
**File:** `indicator_service.py:235` (`compute_position_health`)
**Callers:** `warrior_positions.py:137,184` (API routes only)
**Verified:** Zero references in entry engine, monitor, or scanner.

**Verdict:** ✅ Correct — display-only dashboard metric. Not part of Ross's methodology.

---

### A.14 — SPY Context (Not Implemented)

**Strategy says:**
> §7 L266-282: Market temperature assessment references Bitcoin, scanner activity, sector conditions
> No explicit mention of SPY 20MA/50MA gating

**Implementation:** Zero code references to `spy_context`, `spy_health`, or any SPY indicator.

**Verdict:** 🟡 Not in Ross's methodology as a direct gate. The "market temperature" concept (§7) is broader than SPY — it encompasses scanner activity, holding patterns, and sector themes. Not a gap per se.

---

### A.15 — RVOL (5x Prerequisite for MACD) 🔴

**Strategy says:**
> "Requires 5x RVOL as a prerequisite for MACD signals to be meaningful" (§8.1 L322)

**Implementation:**
- Scanner computes RVOL and stores it on the candidate
- Scoring uses `volume_ratio` (scanner RVOL) at 10% weight
- **But the MACD gate does NOT check whether RVOL ≥ 5x before applying MACD logic**

**Verified with:** `grep_search "5.*rvol" in nexus2/domain/automation/` → 0 results

**Verdict:** 🔴 **Gap.** The strategy explicitly states that MACD signals require 5x RVOL as a prerequisite. The MACD gate currently applies unconditionally regardless of RVOL. Low-RVOL stocks could have noisy/meaningless MACD values.

---

## 3. Per-Pattern Guard Coverage Matrix

Shows which quality guards protect each entry pattern:

| Pattern | MACD Gate | VWAP Gate | EMA 9 Gate | Vol Expansion | Falling Knife | Red Candle | Active Market | Vol Confirmed |
|---------|-----------|-----------|------------|---------------|---------------|------------|---------------|---------------|
| WHOLE_HALF_ANTICIPATORY | ✅¹ | ✅¹ | ✅¹ | ✅ (1.5x) | ❌ | ❌ | ❌ | ❌ |
| DIP_FOR_LEVEL | ✅¹ | ✅¹ | ✅¹ | ✅ (3.0x) | ❌ | ❌ | ✅ | ❌ |
| PMH_BREAK | ✅¹ | ✅¹ | ✅¹ | ❌ | ❌ | ❌ | ✅ | ❌ |
| PULLBACK | ✅¹ | ✅¹ | ✅¹ | ❌ | ❌ | ❌ | ❌ | ❌ |
| ABCD | ✅¹ | ✅¹ | ✅¹ | ❌ | ❌ | ❌ | ❌ | ❌ |
| BULL_FLAG | ✅¹ | ✅¹ | ✅¹ | ❌ | ❌ | ❌ | ❌ | ❌ |
| VWAP_BREAK | ✅¹ | N/A² | ✅¹ | ❌ | ✅ | ✅ | ❌ | ✅ |
| INVERTED_HS | ✅¹ | ✅¹ | ✅¹ | ❌ | ❌ | ❌ | ❌ | inline |
| CUP_HANDLE | ✅¹ | ✅¹ | ✅¹ | ❌ | ❌ | ❌ | ❌ | inline |
| HOD_BREAK | ✅¹ + inline | inline VWAP | ✅¹ | ❌ | ❌ | ❌ | ❌ | inline |
| MICRO_PULLBACK | inline MACD | ❌³ | ❌³ | ❌ | ❌ | ❌ | ❌ | inline |
| ORB | ✅¹ | ✅¹ | ✅¹ | ❌ | ❌ | ❌ | ❌ | ❌ |

¹ = Applied via centralized `check_entry_guards()` + `validate_technicals()` AFTER pattern detection  
² = VWAP_BREAK IS the VWAP crossing — above-VWAP gate would be contradictory  
³ = MICRO_PULLBACK intentionally skips VWAP/EMA gates per Ross methodology for extended stocks

---

## 4. Summary of Gaps (Ranked by Impact)

| Priority | Gap | Current State | Strategy Justification | Recommended Action |
|----------|-----|---------------|----------------------|-------------------|
| 🔴 HIGH | Falling knife guard is VWAP_BREAK only | Other patterns can enter during falling knife conditions | §3.3: "High-volume red candles = sellers in control" | Move to centralized guard (pre-pattern) or apply in check_entry_guards |
| 🔴 HIGH | High-vol red candle guard is VWAP_BREAK only | Same as above | §3.3 L128-129 | Same fix as falling knife |
| 🔴 HIGH | RVOL ≥ 5x prerequisite for MACD not implemented | MACD gate fires regardless of RVOL | §8.1 L322: "Requires 5x RVOL as a prerequisite" | Add RVOL check before MACD gate, or make MACD gate lenient when RVOL is low |
| 🔴 MEDIUM | Volume expansion scoring not wired | Hardcoded `None` at L531, score always 0.5 | §8 L310: "Volume confirms interest" | Wire the ratio from `check_volume_expansion` to scoring |
| ⚠️ LOW | EMA 9 hard gate may over-block | 1% tolerance gate, but strategy says "NOT Used: EMA crossovers" | §8 L342 | Consider removing hard gate, keep scoring penalty only |
| ⚠️ LOW | L2 mode defaults to log_only | Infrastructure built but effectively disabled | §8 L305: "primary tool" | Promote to `warn` mode for live trading |
| ⚠️ LOW | Volume expansion guard only on 2/11 patterns | WHOLE_HALF and DIP_FOR_LEVEL have it; others don't | §8.1 L322 | Consider adding to PMH_BREAK and HOD_BREAK at minimum |

---

## 5. Files Referenced

| File | Lines | What's There |
|------|-------|-------------|
| `warrior_entry_guards.py` | 35-231 | `check_entry_guards()` — centralized guard orchestration |
| `warrior_entry_guards.py` | 234-303 | `_check_macd_gate()` — MACD hard gate |
| `warrior_entry_guards.py` | 363-450 | `_check_spread_filter()` — spread hard gate |
| `warrior_entry_guards.py` | 453-560 | `_check_l2_gate()` — L2 configurable gate |
| `warrior_entry_guards.py` | 568-694 | `validate_technicals()` — VWAP + EMA 9 gates |
| `warrior_entry_scoring.py` | 70-97 | `compute_macd_score()` — MACD scoring |
| `warrior_entry_scoring.py` | 100-121 | `compute_ema_trend_score()` — EMA 9/20 scoring |
| `warrior_entry_scoring.py` | 147-175 | `compute_vwap_score()` — VWAP scoring |
| `warrior_entry_scoring.py` | 178-205 | `compute_volume_expansion_score()` — defined but receives None |
| `warrior_entry_scoring.py` | 245-345 | `score_pattern()` — composite scoring (55/45 static/dynamic) |
| `warrior_engine_entry.py` | 334-720 | `check_entry_triggers()` — pattern competition orchestration |
| `warrior_engine_entry.py` | 530-531 | Volume expansion hardcoded to None |
| `warrior_entry_helpers.py` | 62 | `check_volume_expansion()` — volume guard function |
| `warrior_entry_helpers.py` | 99 | `check_high_volume_red_candle()` — red candle guard |
| `warrior_entry_helpers.py` | 148 | `check_active_market()` — dead market guard |
| `warrior_entry_helpers.py` | 216 | `check_falling_knife()` — falling knife guard |
| `warrior_entry_helpers.py` | 258 | `update_candidate_technicals()` — caches MACD/EMA/VWAP |
| `warrior_entry_patterns.py` | 1099 | Falling knife used in VWAP_BREAK only |
| `warrior_entry_patterns.py` | 1119 | Red candle used in VWAP_BREAK only |
| `warrior_entry_patterns.py` | 235 | Volume expansion in WHOLE_HALF |
| `warrior_entry_patterns.py` | 471 | Volume expansion in DIP_FOR_LEVEL |
| `warrior_scanner_service.py` | 1166 | `_get_200_ema()` — scanner display metric |
| `indicator_service.py` | 235-357 | `compute_position_health()` — display-only |
| `warrior_positions.py` | 137, 184 | Dashboard API routes — display-only |
