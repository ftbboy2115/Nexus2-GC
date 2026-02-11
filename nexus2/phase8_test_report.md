# Phase 8 Test Report — Trade Contamination Fix

**Date**: 2026-02-10  
**Tester**: Testing Specialist (AI)  
**Context**: Phase 8 fixed trade contamination between batch runs via in-memory SQLite isolation per worker process.

---

## Test 1: Determinism ✅ PASS

Ran `ross_rolr_20260114` twice via `/warrior/sim/run_batch_concurrent` and compared P&L.

| Metric | Run 1 | Run 2 | Match |
|--------|-------|-------|-------|
| `realized_pnl` | $1,622.73 | $1,622.73 | ✅ Exact |
| `bar_count` | 653 | 653 | ✅ Exact |
| `runtime_seconds` | 17.05s | 12.08s | N/A |

**Verdict**: P&L is deterministic across runs. The original bug (orphaned trades causing P&L drift) is fixed.

---

## Test 2: No Orphaned Trades ✅ PASS

Queried VPS database after Test 1 runs:

```sql
SELECT COUNT(*) as orphan_count, GROUP_CONCAT(DISTINCT status) as statuses 
FROM warrior_trades WHERE is_sim=1 
AND status IN ('open','pending_fill','pending_exit','partial','scaling');
```

**Result**: `0|` — zero orphaned sim trades remain.

**Verdict**: Purge and EOD close logic working correctly. No trade state leaks between runs.

---

## Test 3: Full 21-Case Baseline ✅ PASS

Ran all 21 cases via `/warrior/sim/run_batch_concurrent` with empty body `{}`.

| # | Case ID | Symbol | Date | Bars | P&L | Ross P&L | Delta |
|---|---------|--------|------|------|-----|----------|-------|
| 1 | ross_lcfy_20260116 | LCFY | 2026-01-16 | 652 | -$482.56 | $10,456.94 | -$10,939.50 |
| 2 | ross_pavm_20260121 | PAVM | 2026-01-21 | 683 | $554.49 | $43,950.00 | -$43,395.51 |
| 3 | ross_batl_20260126 | BATL | 2026-01-26 | 960 | -$1,730.49 | $0.00 | -$1,730.49 |
| 4 | ross_rolr_20260114 | ROLR | 2026-01-14 | 653 | $1,622.73 | $85,000.00 | -$83,377.27 |
| 5 | ross_bnkk_20260115 | BNKK | 2026-01-15 | 680 | $36.98 | $15,000.00 | -$14,963.02 |
| 6 | ross_tnmg_20260116 | TNMG | 2026-01-16 | 695 | -$376.05 | $2,102.25 | -$2,478.30 |
| 7 | ross_gwav_20260116 | GWAV | 2026-01-16 | 540 | $630.63 | $3,974.68 | -$3,344.05 |
| 8 | ross_vero_20260116 | VERO | 2026-01-16 | 960 | -$302.65 | $3,484.88 | -$3,787.53 |
| 9 | ross_gri_20260128 | GRI | 2026-01-28 | 563 | $201.41 | $31,599.98 | -$31,398.57 |
| 10 | ross_lrhc_20260130 | LRHC | 2026-01-30 | 903 | $0.00 | $31,076.62 | -$31,076.62 |
| 11 | ross_hind_20260127 | HIND | 2026-01-27 | 612 | $0.00 | $55,252.51 | -$55,252.51 |
| 12 | ross_dcx_20260129 | DCX | 2026-01-29 | 668 | $118.26 | $6,268.28 | -$6,150.02 |
| 13 | ross_npt_20260203 | NPT | 2026-02-03 | 656 | $1,732.62 | $81,000.00 | -$79,267.38 |
| 14 | ross_bnai_20260205 | BNAI | 2026-02-05 | 778 | $66.70 | -$7,900.00 | $7,966.70 |
| 15 | ross_rnaz_20260205 | RNAZ | 2026-02-05 | 529 | $0.00 | $1,700.00 | -$1,700.00 |
| 16 | ross_rvsn_20260205 | RVSN | 2026-02-05 | 243 | $0.00 | -$3,000.00 | $3,000.00 |
| 17 | ross_flye_20260206 | FLYE | 2026-02-06 | 466 | $0.00 | $4,800.00 | -$4,800.00 |
| 18 | ross_rdib_20260206 | RDIB | 2026-02-06 | 348 | $27.76 | $700.00 | -$672.24 |
| 19 | ross_mnts_20260209 | MNTS | 2026-02-09 | 686 | -$248.40 | $9,000.00 | -$9,248.40 |
| 20 | ross_sxtc_20260209 | SXTC | 2026-02-09 | 426 | $0.00 | -$5,000.00 | $5,000.00 |
| 21 | ross_uoka_20260209 | UOKA | 2026-02-09 | 905 | $244.94 | $858.00 | -$613.06 |

### Summary

| Metric | Value |
|--------|-------|
| **Total Bot P&L** | $2,096.37 |
| **Total Ross P&L** | $370,324.14 |
| **Delta** | -$368,227.77 |
| **Cases Run** | 21 |
| **Cases Profitable (P&L > 0)** | 10 |
| **Cases Flat (P&L == 0)** | 5 |
| **Cases Losing (P&L < 0)** | 6 |
| **Cases With Errors** | 0 |
| **Total Runtime** | 136.78s |

### Observations

- **No errors** across all 21 cases.
- **10/21 cases** produced positive P&L (48% win rate).
- **5 cases** produced zero P&L (LRHC, HIND, RNAZ, RVSN, FLYE) — likely no entry triggered.
- **ROLR determinism confirmed** — $1,622.73 matches Test 1 exactly.
- **Bot beat Ross on 3 cases**: BNAI (+$7,966.70 vs Ross), RVSN (+$3,000), SXTC (+$5,000) — all cases where Ross lost money.
- **Massive delta gap** to Ross P&L ($368K) — expected at this stage; bot strategy captures small moves while Ross uses larger position sizes and different entry patterns.

---

## Overall Verdict

| Test | Result |
|------|--------|
| Test 1: Determinism | ✅ **PASS** |
| Test 2: No Orphaned Trades | ✅ **PASS** |
| Test 3: Full 21-Case Baseline | ✅ **PASS** (no errors) |

**Phase 8 trade contamination fix is verified and working correctly.**
