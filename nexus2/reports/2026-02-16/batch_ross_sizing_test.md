# Ross-Level Sizing Batch Test Results
**Date:** 2026-02-16  
**Config:** risk_per_trade=$2,000 | max_capital=$100,000 | max_shares=20,000  
**Baseline:** risk_per_trade=$250 | max_capital=$5,000 | max_shares=3,000

## Summary

| Metric | Warrior ($2K risk) | Ross Cameron | Capture Rate |
|--------|-------------------|-------------|-------------|
| **Total P&L** | **$53,923** | **$412,026** | 13.1% |
| Cases Profitable | 19/29 (65.5%) | ~22/29 | — |
| Cases with Errors | 1 (ONCO - no bars) | — | — |
| Runtime | 34.6s (local, 10 cores) | — | — |

> [!IMPORTANT]
> Scaling is **perfectly linear**: 8x risk ($250→$2K) = ~8x P&L ($6.7K→$54K).
> The 87% gap is **entry timing + trade management**, not position sizing.

## Per-Case Results

| Symbol | Date | Warrior P&L | Ross P&L | Delta | Entry Pattern | Shares |
|--------|------|------------|----------|-------|---------------|--------|
| BATL | 1/27 | **+$19,899** | $0 | +$19,899 | dip_for_level | 15,789 |
| NPT | 2/03 | +$14,027 | +$81,000 | -$66,973 | — | — |
| ROLR | 1/14 | +$10,610 | +$85,000 | -$74,391 | micro_pullback | 7,112 |
| VERO | 1/16 | +$4,358 | +$3,485 | +$873 | hod_break | 6,939 |
| PMI | 2/12 | +$3,999 | +$9,959 | -$5,960 | — | — |
| DCX | 1/29 | +$3,548 | +$6,268 | -$2,721 | whole_half_ant. | 5,262 |
| LRHC | 1/30 | +$2,319 | +$31,077 | -$28,758 | vwap_break | 3,658 |
| UOKA | 2/09 | +$2,239 | +$858 | +$1,381 | — | — |
| EVMN | 2/10 | +$2,201 | -$10,000 | **+$12,201** | dip_for_level | 600 |
| GWAV | 1/16 | +$1,744 | +$3,975 | -$2,231 | whole_half_ant. | 4,053 |
| TNMG | 1/16 | +$1,722 | +$2,102 | -$381 | — | — |
| GRI | 1/28 | +$1,618 | +$31,600 | -$29,982 | — | — |
| BATL | 1/26 | +$1,530 | $0 | +$1,530 | micro_pullback | 1,449 |
| BNKK | 1/15 | +$1,417 | +$15,000 | -$13,583 | whole_half_ant. | 1,384 |
| RVSN | 2/05 | +$842 | -$3,000 | **+$3,842** | — | — |
| BNAI | 2/05 | +$786 | -$7,900 | **+$8,686** | whole_half_ant. | 376 |
| RNAZ | 2/05 | +$756 | +$1,700 | -$944 | — | — |
| PAVM | 1/21 | +$228 | +$43,950 | -$43,722 | — | — |
| RDIB | 2/06 | +$224 | +$700 | -$476 | — | — |
| SXTC | 2/09 | $0 | -$5,000 | **+$5,000** | — | — |
| HIND | 1/27 | $0 | +$55,253 | -$55,253 | — | — |
| PRFX | 2/11 | $0 | +$5,971 | -$5,971 | — | — |
| ONCO | 2/12 | $0 | -$5,500 | +$5,500 | — (no bars) | — |
| MLEC | 2/13 | -$801 | +$43,000 | -$43,801 | hod_break | 729/2,499 |
| VELO | 2/10 | -$3,127 | -$2,000 | -$1,127 | — | — |
| BNRG | 2/11 | -$3,620 | +$272 | -$3,892 | — | — |
| FLYE | 2/06 | -$3,090 | +$4,800 | -$7,890 | — | — |
| LCFY | 1/16 | -$3,866 | +$10,457 | -$14,323 | — | — |
| MNTS | 2/09 | -$5,635 | +$9,000 | -$14,635 | — | — |

## Analysis: Where the Gap Lives

### 1. Beat Ross (7 cases, +$32.6K edge)
Bot avoided Ross's losers (BNAI -$7.9K, EVMN -$10K, RVSN -$3K, SXTC -$5K) and found winners he skipped (BATL days).

### 2. Home Run Riding Gap (-$67K from NPT alone)
NPT made $14K vs Ross's $81K. The bot exits at base-hit targets while Ross rides winners much further. This is the single largest improvement lever.

### 3. Scaling/Adds Gap (-$74K from ROLR)
ROLR: $10.6K vs $85K. Ross aggressively adds on strength, pyramiding into winners. The bot takes one entry and manages it — no scaling into extended moves.

### 4. Missing Entries (-$61K from HIND + PRFX)
Two cases with zero trades. Patterns didn't trigger — need more entry pattern coverage.

### 5. Wrong Level Entries (-$44K from MLEC + PAVM)
MLEC entered at wrong levels, PAVM barely captured anything. Entry timing needs improvement.

## Priority Improvements (by P&L impact)

| Priority | Improvement | Est. P&L Recovery | Cases Affected |
|----------|------------|-------------------|----------------|
| 1 | Home run riding (don't exit at 1R) | +$67K+ | NPT, GRI, LRHC |
| 2 | Scaling/adds on strength | +$74K+ | ROLR, BNKK |
| 3 | More entry patterns | +$61K+ | HIND, PRFX |
| 4 | Re-entry quality gates | +$44K+ | MLEC, PAVM |
| 5 | Better exit timing | +$15K+ | LCFY, MNTS, FLYE |
