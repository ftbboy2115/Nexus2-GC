# Batch Test Report: HOD Consolidation Break (Fix 1)

**Date:** 2026-02-14  
**Tester:** Testing Specialist Agent  
**Pattern:** `detect_hod_consolidation_break` in [warrior_entry_patterns.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py#L1257-L1412)

---

## Test 1: MLEC Individual Run

```
POST /warrior/sim/run_batch  {"case_ids": ["ross_mlec_20260213"]}
```

| Field | Result |
|-------|--------|
| Trades | **0** |
| P&L | $0.00 |
| Ross P&L | $43,000 |
| Delta | -$43,000 |
| Pattern triggered | **None** — HOD_BREAK never fired |

### Root Cause: Consolidation Too Wide (17.2% vs 3% threshold)

The HOD_BREAK pattern requires the last 5 candles to have a range ≤ 3% of `consol_high`. MLEC's price action is too volatile for this threshold.

**Bar data at the breakout window:**

| Time | Open | High | Low | Close | Volume |
|------|------|------|-----|-------|--------|
| 08:03 | 5.49 | **8.49** | 5.49 | 7.37 | 46K |
| 08:04 | 7.35 | 8.03 | 6.76 | 7.02 | 207K |
| 08:05 | 7.01 | 7.33 | 6.60 | 6.68 | 142K |
| 08:06 | 6.74 | 7.67 | 6.54 | 7.29 | 332K |
| 08:07 | 7.30 | 7.50 | 7.00 | 7.35 | 225K |
| 08:08 | 7.28 | 7.75 | 7.20 | 7.30 | 260K |
| 08:09 | 7.36 | 7.69 | 7.03 | 7.52 | 225K |
| 08:10 | 7.58 | 7.90 | 7.20 | 7.59 | 395K |
| **08:11** | **7.62** | **9.07** | **7.37** | **8.71** | **555K** ← Ross's entry |

**At 08:10** (last chance before breakout):
- HOD = $8.49 (from 08:03 spike)
- Consolidation last 5 bars (08:06–08:10): Low=$6.54, High=$7.90
- **Range = 17.2%** → blocked by `consol_range_pct > 3.0` at [line 1334](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py#L1334)

**At 08:11** (breakout bar):
- consol_high ($9.07) ≥ hod_level ($9.07) → blocked by [line 1342](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py#L1342)

> [!CAUTION]
> The 3% tightness threshold is fundamentally incompatible with MLEC's price action. Ross's "break of high-of-day" on MLEC was a breakout through a **volatile** consolidation zone ($6.54–$7.90), not a tight flag. The pattern as implemented can only detect calm, tight consolidations — not the aggressive, volatile HOD breaks that Ross trades.

---

## Test 2: Full Batch Regression

```
POST /warrior/sim/run_batch  (all POLYGON_DATA cases)
```

| Metric | Value |
|--------|-------|
| Cases run | 29 |
| Total P&L | $1,570.00 |
| Ross P&L | $412,026.08 |
| Delta | -$410,456.08 |
| Cases profitable | 15 |
| Errors | 1 (ONCO: 404 test case not found) |
| Runtime | 43.38s |
| **HOD_BREAK triggers** | **0 across all 29 cases** |

### Per-Case Results

| Case | Symbol | Trades | P&L | Ross P&L | Delta | Trigger Types |
|------|--------|--------|-----|----------|-------|---------------|
| ross_lcfy_20260116 | LCFY | 0 | -$193 | +$10,457 | -$10,650 | — |
| ross_pavm_20260121 | PAVM | 3 | +$216 | +$43,950 | -$43,734 | pullback, pmh_break ×2 |
| ross_batl_20260126 | BATL | 4 | -$70 | $0 | -$70 | micro_pullback ×4 |
| ross_batl_20260127 | BATL | 3 | -$302 | $0 | -$302 | pullback, pmh_break, dip_for_level |
| ross_rolr_20260114 | ROLR | 4 | +$613 | +$85,000 | -$84,387 | micro_pullback ×4 |
| ross_bnkk_20260115 | BNKK | 1 | +$71 | +$15,000 | -$14,929 | whole_half_anticipatory |
| ross_tnmg_20260116 | TNMG | 0 | -$5 | +$2,102 | -$2,107 | — |
| ross_gwav_20260116 | GWAV | 0 | +$253 | +$3,975 | -$3,722 | — |
| ross_vero_20260116 | VERO | 6 | +$14 | +$3,485 | -$3,471 | pullback ×3, pmh_break ×2, whole_half |
| ross_gri_20260128 | GRI | 0 | +$79 | +$31,600 | -$31,520 | — |
| ross_lrhc_20260130 | LRHC | 0 | $0 | +$31,077 | -$31,077 | — |
| ross_hind_20260127 | HIND | 0 | $0 | +$55,253 | -$55,253 | — |
| ross_dcx_20260129 | DCX | 2 | +$79 | +$6,268 | -$6,189 | whole_half ×2 |
| ross_npt_20260203 | NPT | 0 | +$694 | +$81,000 | -$80,306 | — |
| ross_bnai_20260205 | BNAI | 2 | +$72 | -$7,900 | +$7,972 | whole_half ×2 |
| ross_rnaz_20260205 | RNAZ | 0 | $0 | +$1,700 | -$1,700 | — |
| ross_rvsn_20260205 | RVSN | 0 | +$42 | -$3,000 | +$3,042 | — |
| ross_flye_20260206 | FLYE | 0 | -$107 | +$4,800 | -$4,907 | — |
| ross_rdib_20260206 | RDIB | 0 | +$11 | +$700 | -$689 | — |
| ross_mnts_20260209 | MNTS | 1 | +$18 | +$9,000 | -$8,982 | dip_for_level |
| ross_sxtc_20260209 | SXTC | 0 | $0 | -$5,000 | +$5,000 | — |
| ross_uoka_20260209 | UOKA | 0 | +$112 | +$858 | -$747 | — |
| ross_evmn_20260210 | EVMN | 1 | +$109 | -$10,000 | +$10,109 | dip_for_level |
| ross_velo_20260210 | VELO | 0 | -$155 | -$2,000 | +$1,845 | — |
| ross_bnrg_20260211 | BNRG | 0 | -$181 | +$272 | -$452 | — |
| ross_prfx_20260211 | PRFX | 0 | $0 | +$5,971 | -$5,971 | — |
| ross_pmi_20260212 | PMI | 0 | +$200 | +$9,959 | -$9,760 | — |
| ross_onco_20260212 | ONCO | 0 | $0 | -$5,500 | +$5,500 | ERROR: 404 |
| **ross_mlec_20260213** | **MLEC** | **0** | **$0** | **+$43,000** | **-$43,000** | **— (HOD_BREAK blocked)** |

### Regression Check

No regressions detected. All existing test case P&L values match prior runs. The new HOD_BREAK pattern had **zero effect** on any test case because it never triggered.

---

## Test 3: HOD_BREAK Pattern Triggers in Logs

**Zero HOD_BREAK triggers across all 29 test cases.** No `[Warrior Entry]` log line mentioning `HOD_BREAK` or `HOD CONSOLIDATION BREAK` was produced.

---

## Diagnosis

The HOD_BREAK pattern has **three compounding problems** that prevent it from ever firing on MLEC:

### Problem 1: Tightness threshold too strict (BLOCKING)
The 3% consolidation range threshold ([line 1334](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py#L1334)) is far too tight for MLEC's volatile price action. The actual consolidation range is **17.2%** ($6.54–$7.90). Ross's "consolidation" in this context means price bouncing $6.50–$7.90 for several minutes — this is normal for a low-cap stock with 200K+ volume bars.

### Problem 2: Timing paradox
The only bar where all checks *could* pass (08:10) fails tightness. By the time the breakout happens (08:11), `consol_high` already equals `hod_level` because the breakout bar's high ($9.07) *is* the new HOD — so `consol_high >= hod_level` blocks at [line 1342](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py#L1342).

### Problem 3: Pattern checks using close price, not real-time
The simulation uses bar close prices, but Ross entered mid-bar at ~$7.86–$7.97 during the 08:11 breakout bar (O=$7.62, H=$9.07). By close ($8.71), the entry opportunity has passed.

---

## Recommendations

| # | Fix | Impact | Effort |
|---|-----|--------|--------|
| 1 | **Relax tightness to 15–20%** for low-cap momentum stocks, or use ATR-based dynamic threshold | High — unblocks MLEC | S |
| 2 | **Use breakout bar high vs prior consol_high**, not close price, for trigger detection | High — fixes timing paradox | M |
| 3 | **Consider 10s bar stepping** for MLEC test case to capture mid-bar entries | Medium — improves accuracy | S |
| 4 | Log all HOD_BREAK skip reasons at `logger.info` level (currently `logger.debug`) | Medium — enables debugging | S |
