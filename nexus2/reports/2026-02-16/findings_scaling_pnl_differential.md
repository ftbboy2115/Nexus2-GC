# Fix 5 Scaling Regression: Per-Case P&L Differential

**Date:** 2026-02-16  
**Agent:** Backend Planner  
**Reference:** [handoff_fix5_scaling_investigation.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-02-16/handoff_fix5_scaling_investigation.md)

---

## Executive Summary

The `enable_improved_scaling` toggle causes a **-$3,501.75 regression** ($13,297.88 → $9,796.13).

> [!CAUTION]
> **77% of the regression ($2,693) is concentrated in just 2 cases: VERO and ROLR.**
> VERO's regression (-$1,667) is NOT from the scaling module — it's from re-entry consolidation leaking `scale_count`.

### Quick Stats

| Metric | Value |
|--------|-------|
| Baseline P&L (`False`) | $13,297.88 |
| Scaling P&L (`True`) | $9,796.13 |
| **Total Delta** | **-$3,501.75** |
| Cases Regressed | 17 / 29 |
| Cases Improved | 9 / 29 |
| Cases Unchanged | 3 / 29 |
| Top Regressor | VERO (-$1,667.35) |
| Top Improver | MNTS (+$410.37) |

---

## Per-Case Delta Table

Sorted by delta (worst first). Cases with SCALE EXECUTED events (from trace data) are marked with ⚡.

| Case ID | Symbol | Baseline | Scaling | Delta | Impact | Scaled? |
|---------|--------|----------|---------|-------|--------|---------|
| ross_vero_20260116 | VERO | $+1,907.25 | $+239.90 | **-$1,667.35** | WORSE | ⚡ re-entry only |
| ross_rolr_20260114 | ROLR | $+6,140.06 | $+5,114.16 | **-$1,025.90** | WORSE | ⚡ 1 scale |
| ross_npt_20260203 | NPT | $+1,732.62 | $+1,157.26 | -$575.36 | WORSE | No |
| ross_batl_20260127 | BATL | $+2,485.37 | $+1,996.77 | -$488.60 | WORSE | ⚡ 2 scales |
| ross_gri_20260128 | GRI | $+533.93 | $+355.11 | -$178.82 | WORSE | No |
| ross_pmi_20260212 | PMI | $+499.06 | $+332.74 | -$166.32 | WORSE | No |
| ross_gwav_20260116 | GWAV | $+215.91 | $+56.29 | -$159.62 | WORSE | ⚡ 2 scales |
| ross_evmn_20260210 | EVMN | $+319.60 | $+211.75 | -$107.85 | WORSE | No |
| ross_tnmg_20260116 | TNMG | $+215.17 | $+125.66 | -$89.51 | WORSE | ⚡ 2 scales |
| ross_bnai_20260205 | BNAI | $+141.91 | $+97.27 | -$44.64 | WORSE | No |
| ross_lrhc_20260130 | LRHC | $+86.64 | $+57.76 | -$28.88 | WORSE | No |
| ross_mlec_20260213 | MLEC | $-299.33 | $-324.14 | -$24.81 | WORSE | ⚡ 2 scales |
| ross_lcfy_20260116 | LCFY | $-482.56 | $-501.92 | -$19.36 | WORSE | ⚡ 2 scales |
| ross_rnaz_20260205 | RNAZ | $+42.47 | $+28.19 | -$14.28 | WORSE | No |
| ross_rvsn_20260205 | RVSN | $+20.06 | $+13.17 | -$6.89 | WORSE | No |
| ross_bnkk_20260115 | BNKK | $+17.91 | $+11.86 | -$6.05 | WORSE | No |
| ross_pavm_20260121 | PAVM | $+9.63 | $+4.04 | -$5.59 | WORSE | No |
| ross_hind_20260127 | HIND | $0.00 | $0.00 | $0.00 | SAME | No |
| ross_onco_20260212 | ONCO | $0.00 | $0.00 | $0.00 | SAME | No |
| ross_sxtc_20260209 | SXTC | $0.00 | $0.00 | $0.00 | SAME | No |
| ross_velo_20260210 | VELO | $-389.82 | $-388.93 | +$0.89 | BETTER | ⚡ 2 scales |
| ross_rdib_20260206 | RDIB | $-9.79 | $-7.11 | +$2.68 | BETTER | No |
| ross_flye_20260206 | FLYE | $-382.20 | $-378.60 | +$3.60 | BETTER | ⚡ 2 scales |
| ross_uoka_20260209 | UOKA | $+824.14 | $+897.59 | +$73.45 | BETTER | ⚡ 2 scales |
| ross_prfx_20260211 | PRFX | $0.00 | $+147.68 | +$147.68 | BETTER | ⚡ 2 scales |
| ross_batl_20260126 | BATL | $+770.96 | $+921.89 | +$150.93 | BETTER | No |
| ross_bnrg_20260211 | BNRG | $-452.55 | $-301.70 | +$150.85 | BETTER | No |
| ross_dcx_20260129 | DCX | $+55.75 | $+223.38 | +$167.63 | BETTER | ⚡ 2 scales |
| ross_mnts_20260209 | MNTS | $-704.31 | $-293.94 | +$410.37 | BETTER | ⚡ 2 scales |

---

## Regression Concentration Analysis

> [!IMPORTANT]
> **The regression is NOT spread across many cases. It's concentrated in 4 cases (-$3,757), partially offset by 3 improving cases (+$628).**

### Top 4 Regressors (account for 107% of total regression)

| Case | Delta | % of Regression | Root Cause |
|------|-------|----------------|------------|
| VERO | -$1,667 | 47.6% | Re-entry consolidation (NOT scaling module) |
| ROLR | -$1,026 | 29.3% | Scale at $14.14 (12% below $16.07 entry) |
| NPT | -$575 | 16.4% | Non-scaled case, indirect effect |
| BATL 1/27 | -$489 | 14.0% | 2 scales at $3.11/$3.10 (3.4% below $3.22 entry) |

### Top 3 Improvers (offset -$628 of regression)

| Case | Delta | Mechanism |
|------|-------|-----------|
| MNTS | +$410 | 2 scales at $6.75/$6.73 (12% below $7.67 entry) |
| DCX | +$168 | 2 scales at $4.10/$4.04 (7-8% below $4.41 entry) |
| BATL 1/26 | +$151 | Not scaled (different date) |

---

## Scale Price Analysis (from trace logs)

All 23 SCALE EXECUTED events across 12 symbols scaled BELOW entry price (averaging down):

| Symbol | Entry | Scale #1 | Scale #2 | % Below Entry | P&L Impact |
|--------|-------|----------|----------|---------------|------------|
| **ROLR** | $16.07 | $14.14 | — | -12.0% | **-$1,026** |
| **TNMG** | $3.43 | $2.75 | $2.73 | -19.8% / -20.4% | -$90 |
| **FLYE** | $7.11 | $5.66 | $5.54 | -20.4% / -22.1% | +$4 |
| **GWAV** | $5.68 | $5.20 | $5.18 | -8.4% / -8.8% | -$160 |
| **DCX** | $4.41 | $4.10 | $4.04 | -7.0% / -8.4% | **+$168** |
| **VELO** | $14.90 | $14.15 | $14.18 | -5.0% / -4.8% | +$1 |
| **PRFX** | $2.96 | $2.83 | $2.83 | -4.4% | **+$148** |
| **BATL** (1/27) | $3.22 | $3.11 | $3.10 | -3.4% / -3.7% | **-$489** |
| **UOKA** | $2.43 | $2.07 | $2.08 | -14.8% / -14.4% | **+$73** |
| **LCFY** | $4.96 | $4.71 | $4.70 | -5.0% / -5.2% | -$19 |
| **MNTS** | $7.67 | $6.75 | $6.73 | -12.0% / -12.3% | **+$410** |
| **MLEC** | $8.76 | $8.45 | $8.30 | -3.5% / -5.3% | -$25 |

### Pattern: No correlation between pullback depth and outcome

- Deep pullbacks (12-20%) can be profitable (MNTS +$410, UOKA +$73) or unprofitable (ROLR -$1,026, TNMG -$90)
- Shallow pullbacks (3-5%) can be unprofitable (BATL -$489, LCFY -$19)
- **The pullback depth threshold alone is not predictive of outcome**

---

## VERO Deep Dive: The Non-Scaling Regression

> [!WARNING]
> VERO's -$1,667 regression (47.6% of total) is NOT caused by the scaling module.

### Trace Evidence

From `scaling_trace_57952.log`:

1. VERO enters at $2.83 with 384 shares, `scale_count=0`
2. Pullback threshold is $2.49 — price never enters pullback zone (`is_pullback_zone=False` on all checkpoints)
3. **No SCALE EXECUTED event fires for VERO**
4. Yet at line 33: `scale_count=1`, `shares=674`, `entry=$2.92` — this came from **re-entry consolidation** (`consolidate_position()`)
5. After partial: `shares=337`, `partial_taken=True`, `exit_mode=home_run`, `stop=$2.92`

### How the regression happens

```
BASELINE (no scaling toggle effects):
  Entry: 866 shares @ $2.90, rides to high → $1,907 P&L

SCALING (toggle enables cooldown bypass + pullback zone):
  Entry: 384 shares @ $2.83
  Re-entry: consolidates to 674 shares @ $2.92 (scale_count=1)  
  Partial at $3.25: sells 337 → home_run mode with 337 shares
  BUT: scale_count=1 from consolidation, only 1 scale slot left
  Result: $240 P&L (88% less)
```

The different share counts (866 vs 384/674) and entry prices ($2.90 vs $2.83/$2.92) suggest the `enable_improved_scaling` code path has a **secondary effect on position sizing or entry timing**, not just scaling.

---

## Non-Scaled Cases That Regressed

> [!IMPORTANT]
> **10 of 17 regressed cases had NO scale events.** These smaller regressions ($5-$575 each) likely stem from secondary effects of the toggle on cooldown/guard bypasses.

| Case | Symbol | Delta | Trades (B/S) |
|------|--------|-------|-------------|
| NPT | NPT | -$575 | 0 / 0 |
| GRI | GRI | -$179 | 0 / 0 |
| PMI | PMI | -$166 | 0 / 0 |
| EVMN | EVMN | -$108 | 0 / 0 |
| BNAI | BNAI | -$45 | 0 / 0 |
| LRHC | LRHC | -$29 | 0 / 0 |
| RNAZ | RNAZ | -$14 | 0 / 0 |
| RVSN | RVSN | -$7 | 0 / 0 |
| BNKK | BNKK | -$6 | 0 / 0 |
| PAVM | PAVM | -$6 | 0 / 0 |

These cases showing 0 trades in warrior_db (but non-zero P&L from MockBroker) means trade data
is tracked at broker level. The consistent ~33% reduction pattern across many non-scaled cases
suggests a **systemic position sizing change**, not individual scaling effects.

---

## Answers to Handoff Questions

### Q1: What is the per-case P&L impact of scaling?
**ANSWERED.** See delta table above. Regression is heavily concentrated: VERO (-$1,667) + ROLR (-$1,026) = 77%.

### Q2: Is the pullback zone threshold (50%) too deep?
**PARTIALLY ANSWERED.** Scale prices range from 3% to 22% below entry, but depth does NOT predict outcome. MNTS scaled 12% below and gained $410; ROLR scaled 12% below and lost $1,026. The issue is not the threshold — it's that **all scaling is averaging down** regardless of depth.

### Q6: Is the regression ALL from scaling or partially from other interactions?
**ANSWERED.** It's BOTH:
- **Scaling-caused:** ROLR (-$1,026), BATL (-$489), GWAV (-$160) = -$1,675 from actual scale events
- **Side-effect caused:** VERO (-$1,667) and 9 other non-scaled cases (-$1,135) regressed without any SCALE EXECUTED events
- The toggle's cooldown bypass and pullback zone guards have **secondary effects beyond enabling scaling**

---

## Conclusions

1. **Scaling is net-negative overall** but some cases benefit (MNTS, DCX, UOKA, PRFX)
2. **47% of the regression is from VERO**, which never scaled through the module — it's a re-entry consolidation bug
3. **Non-scaled cases show a systemic ~33% P&L reduction**, suggesting the toggle has side effects beyond scaling
4. **If VERO's consolidation bug were fixed**, the remaining regression would be -$1,834 (still significant but more manageable)

### Recommended Next Steps

1. **Fix re-entry `scale_count` leak** — `consolidate_position()` incrementing `scale_count` is the single biggest regresssion source
2. **Investigate systemic position sizing change** — why do 10 non-scaled cases all lose ~33% P&L?
3. **Keep `enable_improved_scaling=False`** until both issues above are resolved

---

## Raw Data

- Baseline results: [scaling_comparison_baseline.json](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/data/scaling_comparison_baseline.json)
- Scaling results: [scaling_comparison_scaling.json](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/data/scaling_comparison_scaling.json)
- Delta comparison: [scaling_comparison_delta.json](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/data/scaling_comparison_delta.json)
- Trace logs: `data/scaling_trace_*.log` (8 files)
