# Warrior Batch Test Results — 2026-02-18

**Run time:** 155.14s (concurrent mode, ~5s/case average)
**Date:** 2026-02-18 11:30 ET

---

## Summary

| Metric | Value |
|--------|-------|
| Cases Run | 30 |
| Cases Profitable | 18 (60%) |
| Bot Total P&L | **+$101,256.40** |
| Ross Total P&L | +$413,626.08 |
| Delta (bot − Ross) | **-$312,369.68** |
| Capture Rate | 24.5% of Ross's P&L |
| Errors | 0 |

> [!IMPORTANT]
> Bot is profitable overall (+$101K across 30 cases) but only captures ~25% of Ross's gains.
> The biggest gaps are on Ross's monster days (HIND, MLEC, NPT, PAVM) where scaling aggressively is key.

---

## Per-Case Results

### ✅ Bot Matched or Beat Ross (9 cases)

| Case | Symbol | Bot P&L | Ross P&L | Delta | Notes |
|------|--------|---------|----------|-------|-------|
| ross_vero_20260116 | VERO | +$19,072 | +$3,485 | **+$15,587** | Bot outperformed 5.5x |
| ross_evmn_20260210 | EVMN | +$3,182 | -$10,000 | **+$13,182** | Bot profitable on Ross's loser |
| ross_bnai_20260205 | BNAI | +$1,455 | -$7,900 | **+$9,355** | Bot avoided fatal add |
| ross_batl_20260126 | BATL | +$7,740 | $0 | **+$7,740** | Bot found trade Ross missed |
| ross_sxtc_20260209 | SXTC | $0 | -$5,000 | **+$5,000** | Bot correctly avoided |
| ross_uoka_20260209 | UOKA | +$5,646 | +$858 | **+$4,788** | Bot scaled better |
| ross_rvsn_20260205 | RVSN | +$201 | -$3,000 | **+$3,201** | Bot avoided hail mary |
| ross_onco_20260212 | ONCO | -$5,178 | -$5,500 | **+$322** | Slightly less loss |
| ross_tnmg_20260116 | TNMG | +$2,152 | +$2,102 | **+$50** | Near-perfect match ⭐ |

### ⚠️ Bot Underperformed Ross (21 cases)

| Case | Symbol | Bot P&L | Ross P&L | Delta | Gap |
|------|--------|---------|----------|-------|-----|
| ross_hind_20260127 | HIND | $0 | +$55,253 | -$55,253 | Bot didn't trade |
| ross_npt_20260203 | NPT | +$17,539 | +$81,000 | -$63,461 | 22% capture |
| ross_pavm_20260121 | PAVM | +$105 | +$43,950 | -$43,845 | 0.2% capture |
| ross_mlec_20260213 | MLEC | +$290 | +$43,000 | -$42,710 | 0.7% capture |
| ross_lrhc_20260130 | LRHC | +$869 | +$31,077 | -$30,208 | 2.8% capture |
| ross_gri_20260128 | GRI | +$5,351 | +$31,600 | -$26,249 | 16.9% capture |
| ross_rolr_20260114 | ROLR | +$61,566 | +$85,000 | -$23,434 | 72.4% capture |
| ross_lcfy_20260116 | LCFY | -$4,833 | +$10,457 | -$15,290 | Loss vs win |
| ross_mnts_20260209 | MNTS | -$6,544 | +$9,000 | -$15,544 | Loss vs win |
| ross_bnkk_20260115 | BNKK | +$180 | +$15,000 | -$14,820 | 1.2% capture |
| ross_flye_20260206 | FLYE | -$3,866 | +$4,800 | -$8,666 | Loss vs win |
| ross_prfx_20260211 | PRFX | $0 | +$5,971 | -$5,971 | Bot didn't trade |
| ross_dcx_20260129 | DCX | +$559 | +$6,268 | -$5,709 | 8.9% capture |
| ross_pmi_20260212 | PMI | +$4,999 | +$9,959 | -$4,960 | 50.2% capture |
| ross_bnrg_20260211 | BNRG | -$4,526 | +$272 | -$4,797 | Loss vs small win |
| ross_batl_20260127 | BATL | -$3,300 | $0 | -$3,300 | Bot lost on no-trade |
| ross_velo_20260210 | VELO | -$3,908 | -$2,000 | -$1,908 | Bigger loss |
| ross_gwav_20260116 | GWAV | +$2,179 | +$3,975 | -$1,795 | 54.8% capture |
| ross_vhub_20260217 | VHUB | $0 | +$1,600 | -$1,600 | Bot didn't trade |
| ross_rnaz_20260205 | RNAZ | +$426 | +$1,700 | -$1,274 | 25% capture |
| ross_rdib_20260206 | RDIB | -$99 | +$700 | -$799 | Small loss vs win |

---

## Key Observations

### 1. Scaling is the #1 Gap
The biggest deltas are on Ross's monster days: HIND ($55K miss), NPT ($63K gap), PAVM ($44K gap), MLEC ($43K gap). Ross uses **full buying power** on high-conviction plays — the bot takes small base-hit positions and doesn't scale aggressively enough.

### 2. Bot Avoids Ross's Bad Trades Well
On Ross's losing days (BNAI -$7.9K, EVMN -$10K, SXTC -$5K, RVSN -$3K), the bot either stayed flat or profited. This is a **strong signal** — the risk management is working. The bot turned 4 of Ross's losers into winners/flat.

### 3. "Didn't Trade" Cases
HIND ($0 vs $55K), PRFX ($0 vs $6K), VHUB ($0 vs $1.6K) — bot found no valid entry trigger. These need investigation into whether the entry patterns simply don't match Ross's actual entries (breaking news timing, pre-8AM entries, etc.)

### 4. Loss vs Win Inversions (Concerning)
LCFY (-$4.8K vs +$10.5K), MNTS (-$6.5K vs +$9K), FLYE (-$3.9K vs +$4.8K), BNRG (-$4.5K vs +$272) — bot entered but with wrong timing/exits, turning winners into losers.

### 5. Near-Perfect Cases
TNMG (+$2,152 vs +$2,102, delta +$50) and ROLR (+$61.6K vs +$85K, 72% capture) show the bot CAN work well when the pattern aligns.

---

## Trade Detail (Cases with Visible Trades)

> [!NOTE]
> Many cases show `trades: []` but non-zero `realized_pnl`, meaning trades happened but
> weren't captured in `warrior_db`. The P&L comes from MockBroker's account-level tracking.

| Case | Entry Trigger | Entry $ | Shares | Stop Method | Exit Mode |
|------|--------------|---------|--------|-------------|-----------|
| BATL 01/26 | micro_pullback | $2.93 | 3,021 | consolidation_low | base_hit |
| ROLR 01/14 | micro_pullback | $3.85 | 8,891 | consolidation_low | base_hit |
| GWAV 01/16 | whole_half_anticipatory | $5.47 | 5,067 | consolidation_low | home_run |
| VERO 01/16 | hod_break | $2.90 | 8,675 | consolidation_low | base_hit |
| UOKA 02/09 | whole_half_anticipatory | $2.43 | 5,596 | consolidation_low | base_hit |

---

## Recommendations (Priority Order)

1. **Scaling Engine** — Implement aggressive adds on strength for high-conviction setups. This alone could close 50%+ of the delta.
2. **Entry Pattern Coverage** — Investigate HIND/PRFX/VHUB to understand which Ross entry patterns the bot doesn't detect.
3. **Loss-vs-Win Inversions** — Debug LCFY, MNTS, FLYE to understand why timing/exits fail on these.
4. **Trade DB Logging** — Fix the gap where `trades: []` but `realized_pnl != 0`. Need full lifecycle in `warrior_db`.
