# Warrior Bot Batch Benchmark — 2026-02-21

**Timestamp:** 2026-02-21 22:50 ET
**Server:** Fresh restart (PID 52580), latest code
**Runtime:** 92.58s concurrent
**Previous Benchmark:** [batch_test_warrior_sim.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-02-18/batch_test_warrior_sim.md) (Feb 18, 30 cases)

---

## Summary

| Metric | Feb 21 (Current) | Feb 18 (Prior) | Change |
|--------|----------------:|---------------:|--------|
| Cases Run | 35 | 30 | +5 new |
| Cases Profitable | 23 (65.7%) | 18 (60%) | **+5.7pp** |
| Bot Total P&L | **+$120,888** | +$101,256 | **+$19,632** |
| Ross Total P&L | +$433,000 | +$413,626 | +$19,374 |
| Delta (Bot − Ross) | -$312,111 | -$312,370 | **+$259** |
| Capture Rate | **27.9%** | 24.5% | **+3.4pp** |
| Errors | 0 | 0 | — |

> [!NOTE]
> The 5 new cases (BCTX, SNSE, ENVB, MLEC Feb 20, EDHL) contribute +$19,374 to Ross's total and +$1,670 to the bot's, slightly diluting capture rate. The core 30 cases improved independently — notably **HIND went from $0 to +$14,110** due to code changes since Feb 18.

---

## Per-Case Results (Sorted by Delta — Worst Mismatches First)

### ❌ Largest Underperformance (Delta < -$5,000)

| # | Case ID | Symbol | Date | Bot P&L | Ross P&L | Delta | Capture | Guards | Bars |
|--:|---------|--------|------|--------:|---------:|------:|--------:|-------:|-----:|
| 1 | ross_npt_20260203 | NPT | 02-03 | +$17,539 | +$81,000 | **-$63,461** | 21.7% | 0 | 656 |
| 2 | ross_pavm_20260121 | PAVM | 01-21 | +$105 | +$43,950 | **-$43,845** | 0.2% | 0 | 595 |
| 3 | ross_mlec_20260213 | MLEC | 02-13 | +$290 | +$43,000 | **-$42,710** | 0.7% | 6 | 598 |
| 4 | ross_hind_20260127 | HIND | 01-27 | +$14,110 | +$55,253 | **-$41,142** | 25.5% | 4 | 612 |
| 5 | ross_lrhc_20260130 | LRHC | 01-30 | +$869 | +$31,077 | **-$30,208** | 2.8% | 1 | 903 |
| 6 | ross_gri_20260128 | GRI | 01-28 | +$5,351 | +$31,600 | **-$26,249** | 16.9% | 0 | 563 |
| 7 | ross_rolr_20260114 | ROLR | 01-14 | +$61,566 | +$85,000 | **-$23,434** | 72.4% | 4 | 653 |
| 8 | ross_mnts_20260209 | 🔴 MNTS | 02-09 | -$7,046 | +$9,000 | **-$16,046** | — | 3 | 686 |
| 9 | ross_lcfy_20260116 | 🔴 LCFY | 01-16 | -$4,833 | +$10,457 | **-$15,290** | — | 0 | 556 |
| 10 | ross_bnkk_20260115 | BNKK | 01-15 | +$180 | +$15,000 | **-$14,820** | 1.2% | 0 | 680 |
| 11 | ross_snse_20260218 | 🔴 SNSE | 02-18 | -$207 | +$9,373 | **-$9,580** | — | 8 | 347 |
| 12 | ross_flye_20260206 | 🔴 FLYE | 02-06 | -$3,866 | +$4,800 | **-$8,666** | — | 0 | 466 |
| 13 | ross_prfx_20260211 | PRFX | 02-11 | $0 | +$5,971 | **-$5,971** | 0% | 2 | 465 |
| 14 | ross_dcx_20260129 | DCX | 01-29 | +$559 | +$6,268 | **-$5,709** | 8.9% | 0 | 668 |
| 15 | ross_mlec_20260220 | MLEC | 02-20 | +$244 | +$5,612 | **-$5,368** | 4.3% | 92 | 311 |

### ⚠️ Moderate Underperformance (Delta -$5,000 to $0)

| # | Case ID | Symbol | Date | Bot P&L | Ross P&L | Delta | Capture | Guards | Bars |
|--:|---------|--------|------|--------:|---------:|------:|--------:|-------:|-----:|
| 16 | ross_pmi_20260212 | PMI | 02-12 | +$4,999 | +$9,959 | -$4,960 | 50.2% | 0 | 339 |
| 17 | ross_bnrg_20260211 | 🔴 BNRG | 02-11 | -$4,526 | +$272 | -$4,797 | — | 0 | 788 |
| 18 | ross_batl_20260127 | BATL | 01-27 | -$3,300 | $0 | -$3,300 | — | 110 | 592 |
| 19 | ross_velo_20260210 | VELO | 02-10 | -$3,908 | -$2,000 | -$1,908 | — | 0 | 472 |
| 20 | ross_gwav_20260116 | GWAV | 01-16 | +$2,179 | +$3,975 | -$1,795 | 54.8% | 0 | 540 |
| 21 | ross_vhub_20260217 | VHUB | 02-17 | $0 | +$1,600 | -$1,600 | 0% | 0 | 341 |
| 22 | ross_rnaz_20260205 | RNAZ | 02-05 | +$426 | +$1,700 | -$1,274 | 25% | 3 | 529 |
| 23 | ross_rdib_20260206 | 🔴 RDIB | 02-06 | -$99 | +$700 | -$799 | — | 0 | 348 |
| 24 | ross_bctx_20260127 | BCTX | 01-27 | +$4,353 | +$4,500 | -$147 | **96.7%** | 6 | 517 |

### ✅ Bot Matched or Beat Ross (Delta ≥ $0)

| # | Case ID | Symbol | Date | Bot P&L | Ross P&L | Delta | Notes | Guards | Bars |
|--:|---------|--------|------|--------:|---------:|------:|-------|-------:|-----:|
| 25 | ross_envb_20260219 | ENVB | 02-19 | +$2 | $0 | +$2 | Near-zero both | 4 | 422 |
| 26 | ross_tnmg_20260116 | TNMG | 01-16 | +$2,152 | +$2,102 | +$50 | ⭐ Near-perfect | 12 | 695 |
| 27 | ross_onco_20260212 | ONCO | 02-12 | -$5,178 | -$5,500 | +$322 | Both lost, bot less | 0 | 515 |
| 28 | ross_edhl_20260220 | 🟢 EDHL | 02-20 | +$1,632 | -$112 | +$1,744 | Bot won Ross's loser | 0 | 322 |
| 29 | ross_rvsn_20260205 | 🟢 RVSN | 02-05 | +$201 | -$3,000 | +$3,201 | Avoided hail mary | 0 | 243 |
| 30 | ross_uoka_20260209 | UOKA | 02-09 | +$5,646 | +$858 | +$4,788 | Bot scaled better | 2 | 905 |
| 31 | ross_sxtc_20260209 | SXTC | 02-09 | $0 | -$5,000 | +$5,000 | Correctly avoided | 0 | 426 |
| 32 | ross_batl_20260126 | BATL | 01-26 | +$7,740 | $0 | +$7,740 | Bot found trade | 3 | 673 |
| 33 | ross_bnai_20260205 | 🟢 BNAI | 02-05 | +$1,455 | -$7,900 | +$9,355 | Avoided fatal add | 0 | 778 |
| 34 | ross_evmn_20260210 | 🟢 EVMN | 02-10 | +$3,182 | -$10,000 | +$13,182 | Bot profitable | 0 | 594 |
| 35 | ross_vero_20260116 | VERO | 01-16 | +$19,072 | +$3,485 | +$15,587 | Bot outperformed 5.5x | 4 | 960 |

---

## Direction Mismatches

### 🟢 Bot Profitable / Ross Lost (4 cases — bot's risk management working)

| Symbol | Bot P&L | Ross P&L | Lesson |
|--------|--------:|---------:|--------|
| EVMN | +$3,182 | -$10,000 | Bot avoided hidden seller trap |
| BNAI | +$1,455 | -$7,900 | Bot didn't do fatal add into reversal |
| EDHL | +$1,632 | -$112 | Bot caught spike early, Ross dip-bought late |
| RVSN | +$201 | -$3,000 | Bot avoided hail mary setup |

### 🔴 Bot Lost / Ross Won (6 cases — entry/exit timing gaps)

| Symbol | Bot P&L | Ross P&L | Issue |
|--------|--------:|---------:|-------|
| MNTS | -$7,046 | +$9,000 | Wrong timing on dip buy |
| LCFY | -$4,833 | +$10,457 | Entry/exit mismatch |
| BNRG | -$4,526 | +$272 | Loss on Ross's near-zero trade |
| FLYE | -$3,866 | +$4,800 | Wrong entry timing |
| SNSE | -$207 | +$9,373 | MACD gate blocked profitable re-entries |
| RDIB | -$99 | +$700 | Small loss vs small win |

---

## Key Changes Since Feb 18 Benchmark

### Improved Cases (same case, different P&L)
| Symbol | Feb 18 P&L | Feb 21 P&L | Improvement |
|--------|----------:|-----------:|------------:|
| **HIND** | $0 | +$14,110 | **+$14,110** ← biggest code improvement |
| MNTS | -$6,544 | -$7,046 | -$502 (slightly worse) |

> [!IMPORTANT]
> **HIND going from $0 (no trade) to +$14,110** is the most significant behavioral change since Feb 18. Code changes between Feb 18-21 enabled the bot to find and take HIND's entry that it previously missed entirely.

### New Cases Added Since Feb 18
| Case ID | Symbol | Bot P&L | Ross P&L |
|---------|--------|--------:|---------:|
| ross_bctx_20260127 | BCTX | +$4,353 | +$4,500 |
| ross_snse_20260218 | SNSE | -$207 | +$9,373 |
| ross_envb_20260219 | ENVB | +$2 | $0 |
| ross_mlec_20260220 | MLEC | +$244 | +$5,612 |
| ross_edhl_20260220 | EDHL | +$1,632 | -$112 |

---

## Statistical Summary

| Metric | Value |
|--------|------:|
| Win Rate | 65.7% (23/35) |
| Average Bot P&L | +$3,454 |
| Average Ross P&L | +$12,371 |
| Median Delta | -$3,300 |
| Best Case (BCTX) | 96.7% capture |
| Worst Case (NPT) | -$63,461 delta |
| Direction Match Rate | 74.3% (26/35) |

### Top 5 Gaps to Address (largest absolute delta)

1. **NPT** (-$63K) — Chinese IPO blue sky short squeeze. Ross used full buying power; bot took small position.
2. **PAVM** (-$44K) — Bot captured only 0.2%. Scaling gap.
3. **MLEC Feb 13** (-$43K) — 3-minute news breakout. MACD + reentry guards heavily blocked.
4. **HIND** (-$41K) — Improved from $0 to $14K but still far from Ross's $55K. Needs aggressive scaling.
5. **LRHC** (-$30K) — Cup & handle VWAP break. Only 2.8% capture.

---

## Observations

1. **Scaling remains the #1 gap** — Top 5 underperformers are all Ross's monster days where he uses full buying power. Bot takes base-hit positions.
2. **Risk management is a clear strength** — Bot turned 4 of Ross's losers into winners (BNAI, EVMN, RVSN, EDHL) and correctly avoided SXTC.
3. **MACD gate is both helpful and harmful** — Blocks bad re-entries (good) but also blocks profitable entries on fast movers like SNSE and MLEC where Ross ignores MACD.
4. **BCTX is the gold standard** — 96.7% capture rate. When the pattern cleanly matches, the bot works.
5. **Guard block inflation** — MLEC Feb 20 has 92 guard blocks (was 23 on old server). Fresh code logs more events but doesn't change P&L.
