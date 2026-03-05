# Validation Report: Entry Quality Research

**Date:** 2026-03-03 10:50 ET  
**Validator:** Audit Validator  
**Source Report:** `nexus2/reports/2026-03-03/research_entry_quality_gap.md`  
**Handoff:** `nexus2/reports/2026-03-03/handoff_validator_entry_quality.md`

---

## Claims Verified

| # | Claim | Result | Summary |
|---|-------|--------|---------|
| 1 | Batch test cases run in complete isolation | **PASS** | Confirmed: in-memory SQLite, single symbol |
| 2 | Top 4 cases produce 52% of total P&L ($183,714) | **FAIL** | Actual top 4 = $205,735 (57.9%); wrong cases listed |
| 3 | `score_pattern()` receives ZERO real-time data | **PASS** | All 7 args are static/scanner-based |
| 4 | `entry_snapshot` computed but NOT passed to scoring | **PASS** | Set in guards, absent from scoring module |
| 5 | Re-entry cooldown in sim mode is 10 minutes | **PASS** | `_reentry_cooldown_minutes = 10` confirmed |
| 6 | `check_volume_expansion()` exists but NOT wired to scoring | **PARTIAL** | Called in pattern detection, not scoring |

---

## Detailed Evidence

### Claim 1: Batch Test Isolation — PASS ✅

**Claim:** Each batch test case runs in COMPLETE ISOLATION (single stock, single day) via per-process in-memory SQLite.

**Verification Command:**
```powershell
Select-String -Path "C:\Dev\Nexus\nexus2\adapters\simulation\sim_context.py" -Pattern "sqlite://|_watchlist\[symbol\]|watchlist.clear"
```

**Actual Output:**
```
sim_context.py:304: ctx.engine._watchlist.clear()
sim_context.py:308: ctx.engine._watchlist[symbol] = watched
sim_context.py:608: mem_engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
```

**Result:** PASS  
**Notes:** All three cited code patterns confirmed at the correct lines. Line 304 clears watchlist, line 308 adds exactly ONE symbol, line 608 creates per-process in-memory SQLite. The isolation claim is accurate.

---

### Claim 2: Top 4 Cases Produce 52% of P&L — FAIL ❌

**Claim:** Top 4 cases (NPT, BATL×2, ROLR) produce $183,714 = 51.7% of total $355,039 P&L.

**Verification:** Read `nexus2/reports/gc_diagnostics/baseline.json` directly via `view_file`. Sorted all 39 cases by `total_pnl` descending.

**Actual Top 4 (from baseline.json):**

| Rank | Case | Symbol | total_pnl |
|------|------|--------|----------:|
| 1 | ross_npt_20260203 | NPT | $68,021.20 |
| 2 | ross_batl_20260127 | BATL | $49,635.80 |
| 3 | ross_rolr_20260114 | ROLR | $45,723.39 |
| 4 | ross_evmn_20260210 | **EVMN** | $42,354.93 |

**Actual Top 4 Sum:** $205,735.32  
**Actual Percentage:** 205,735.32 / 355,038.66 = **57.9%**

**Report's Claim vs Actual:**

| Metric | Report Says | Actual |
|--------|-------------|--------|
| Top 4 cases | NPT, BATL×2, ROLR | NPT, BATL(0127), ROLR, **EVMN** |
| Top 4 P&L | $183,714 | $205,735 |
| Percentage | 51.7% | 57.9% |

**Result:** FAIL  
**Notes:** Two errors:
1. The report lists BATL×2 (two BATL cases) as top 4. But BATL(0126) = $26,757 ranks **5th**, not 4th. EVMN ($42,355) is the actual 4th-largest winner.
2. The report's math for the stated 4 cases is also wrong: NPT ($68,021) + BATL×2 ($49,636 + $26,757) + ROLR ($45,723) = $190,137, not $183,714.

> [!IMPORTANT]
> The overall thesis still holds — P&L IS top-heavy. In fact it's MORE concentrated than claimed (57.9% vs 51.7%). The directional conclusion is correct but the specific numbers and cases are wrong.

---

### Claim 3: `score_pattern()` Receives ZERO Real-Time Data — PASS ✅

**Claim:** `add_candidate()` at `warrior_engine_entry.py:500-525` passes only scanner metadata + hard-coded confidence to `score_pattern()`.

**Verification Command:**
```powershell
Select-String -Path "C:\Dev\Nexus\nexus2\domain\automation\warrior_engine_entry.py" -Pattern "score_pattern\(" -Context 0,10
```

**Actual Output (lines 503-512):**
```python
score = score_pattern(
    pattern=trigger,
    volume_ratio=volume_ratio,        # From scanner metadata (STATIC)
    pattern_confidence=confidence,     # Hard-coded per pattern type (STATIC)
    catalyst_strength=catalyst_strength, # From scanner metadata (STATIC)
    spread_pct=spread_pct,             # From scanner metadata (STATIC)
    level_proximity=level_proximity,   # Computed from current_price (MILDLY DYNAMIC)
    time_score=time_score,             # From clock (MILDLY DYNAMIC)
    blue_sky_pct=blue_sky_pct,         # From FMP quote (STATIC per session)
)
```

**Cross-check with `warrior_entry_scoring.py`:** Viewed entire file (202 lines). The `score_pattern()` function signature at line 64 confirms exactly these 7 parameters (+1 optional `blue_sky_pct`). No MACD, VWAP, EMA, snapshot, or volume expansion parameters exist in the function signature.

**Result:** PASS  
**Notes:** All 7 args are indeed static or near-static. The report's characterization is accurate — the scoring function has zero awareness of real-time price action, MACD momentum, or volume expansion.

---

### Claim 4: `entry_snapshot` NOT Passed to Scoring — PASS ✅

**Claim:** `entry_snapshot` (MACD, VWAP, EMA) is computed in `_check_macd_gate()` and logged at entry, but never fed to `score_pattern()`.

**Verification Command 1 (guards file):**
```powershell
# view_file: warrior_entry_guards.py lines 264-265
```

**Actual Code:**
```python
# CRITICAL: Store snapshot for audit logging
watched.entry_snapshot = snapshot
```

Confirmed at line 265 of `warrior_entry_guards.py`.

**Verification Command 2 (scoring file):**
```powershell
# grep_search for snapshot|macd|vwap|ema in warrior_entry_scoring.py
```

**Actual Output:** No results found.

**Cross-check:** Viewed entire `warrior_entry_scoring.py` (202 lines). The words "snapshot", "macd", "vwap", and "ema" do NOT appear anywhere in the file.

**Result:** PASS  
**Notes:** The claim is accurate. `entry_snapshot` is computed and stored on `watched` before scoring decisions, but is never referenced by `warrior_entry_scoring.py`. This confirms the report's thesis: the scoring system has no access to real-time technical indicators.

---

### Claim 5: Sim-Mode Re-Entry Cooldown Is 10 Minutes — PASS ✅

**Claim:** Code at `warrior_entry_guards.py:166-176` implements sim-mode cooldown using `_reentry_cooldown_minutes`, defaulting to 10.

**Verification Command:**
```powershell
# grep_search for _reentry_cooldown_minutes across automation directory
```

**Actual Output:**
```
warrior_types.py:156:     live_reentry_cooldown_minutes: int = 10
warrior_monitor.py:105:   self._reentry_cooldown_minutes = 10  # Minutes (in sim time) before re-entry allowed
warrior_entry_guards.py:172: cooldown_minutes = engine.monitor._reentry_cooldown_minutes
```

**Cross-check at `warrior_entry_guards.py:166-176`:**
```python
# SIM MODE COOLDOWN
if engine.monitor.sim_mode and symbol in engine.monitor._recently_exited_sim_time:
    exit_sim_time = engine.monitor._recently_exited_sim_time[symbol]
    if hasattr(engine.monitor, '_sim_clock') and engine.monitor._sim_clock:
        current_sim_time = engine.monitor._sim_clock.current_time
        minutes_since_exit = (current_sim_time - exit_sim_time).total_seconds() / 60
        cooldown_minutes = engine.monitor._reentry_cooldown_minutes
        if minutes_since_exit < cooldown_minutes:
            reason = f"SIM re-entry cooldown - exited {minutes_since_exit:.1f}m ago (waiting {cooldown_minutes}m)"
```

**Result:** PASS  
**Notes:** Default value of 10 minutes confirmed in `warrior_monitor.py:105`. Live-mode cooldown is also 10 minutes per `warrior_types.py:156`. Code logic at lines 166-176 matches the report exactly.

---

### Claim 6: `check_volume_expansion()` Exists But NOT Wired to Scoring — PARTIAL ⚠️

**Claim:** The function exists in `warrior_engine_entry.py` but is never called from the entry flow.

**Verification Command:**
```powershell
# grep_search for check_volume_expansion across automation/*.py
```

**Actual Output:**
```
warrior_entry_patterns.py:28:  check_volume_expansion,
warrior_entry_patterns.py:235: vol_ok, vol_ratio, vol_reason = check_volume_expansion(
warrior_entry_patterns.py:471: vol_ok, vol_ratio, vol_reason = check_volume_expansion(
warrior_entry_helpers.py:62:   def check_volume_expansion(
warrior_engine_entry.py:31:    check_volume_expansion,
warrior_engine_entry.py:211:   def check_volume_expansion(
```

**Cross-check:** Viewed `warrior_entry_patterns.py` lines 233-237 and 469-475:
- Line 235: Called inside `detect_whole_half_anticipatory()` for volume confirmation
- Line 471: Called inside `detect_dip_for_level()` for volume expansion check

**Is it wired to scoring?** Checked `warrior_entry_scoring.py` — no reference to `check_volume_expansion`, `vol_ratio`, or `vol_ok`. The function's return values are used as **pattern gates** (blocking/allowing pattern detection), NOT as scoring inputs.

**Result:** PARTIAL  
**Notes:** The report's claim that the function "is never called from the entry flow" is **incorrect**. It IS actively called in two pattern detection functions (`detect_whole_half_anticipatory` and `detect_dip_for_level`). However, the report's broader point is valid: the volume expansion result is NOT fed into `score_pattern()` as a scoring factor. It acts as a binary gate (pass/fail) within specific patterns, not as a quality signal that influences the composite score.

---

## Overall Rating: **MEDIUM**

### Summary

- **5 of 6 claims verified** (4 PASS + 1 PARTIAL)
- **1 claim FAILED** (Claim 2: P&L math and case identification errors)

### Impact Assessment

The **failed claim** (Claim 2) is a data accuracy issue but does NOT undermine the report's thesis. The actual numbers ($205K / 57.9%) support the top-heavy P&L conclusion even MORE strongly than the reported numbers ($183K / 51.7%).

The **partial claim** (Claim 6) incorrectly states the function "is never called from the entry flow" — it is. But the core insight (volume expansion doesn't feed scoring) remains valid.

### Corrections Needed

1. **Claim 2:** Fix the top-4 table to include EVMN instead of BATL(0126). Update sum from $183,714 to $205,735 and percentage from 51.7% to 57.9%.
2. **Claim 6:** Reword to: "`check_volume_expansion()` is used as a binary gate in `detect_whole_half_anticipatory()` and `detect_dip_for_level()`, but its output is NOT passed to `score_pattern()` as a scoring factor."
