# Batch Diagnosis Report

**Generated:** 2026-03-02 08:53:22

```
Batch Diagnosis Report (38 cases)
Bot Total: $386,670.23 | Ross Total: $439,574.87 | Capture: 88.0%

Issue Priority Ranking:
[P1-CRIT] GUARD_BLOCKED: 15 cases, ~$252,783 P&L gap
   Cases: PAVM, ROLR, GWAV, LRHC, HIND, NPT, RNAZ, FLYE (+7 more)
   Fix: Review MACD and reentry guard aggressiveness
[P2-HIGH] OVERSIZED: 13 cases, ~$228,008 P&L gap
   Cases: BATL, BATL, TNMG, VERO, BCTX, SXTC, EVMN, BNRG (+5 more)
   Fix: Review position sizing relative to stop distance
[P3-MED] STOP_HIT: 6 cases, ~$51,548 P&L gap
   Cases: LCFY, BNKK, GRI, DCX, BNAI, EDHL
   Fix: Evaluate stop width -- may be too tight or too wide
[P4-LOW] NO_RE_ENTRY: 4 cases, ~$13,292 P&L gap
   Cases: RVSN, VELO, ONCO, AIDX
   Fix: Add re-entry logic after stop-out on strong runners

Guard Blocks: 124315 total ()

Per-Case Summary (sorted by delta, worst first):
  MLEC: Bot $-578.33 vs Ross $43,000.00 (delta $-43,578.33) -- GUARD_BLOCKED: Guards blocked 4964 re-entry attempts (4964 blocks) + OVERSIZED: Position size $87,526 + STOP_HIT: Technical stop triggered
  ROLR: Bot $45,723.39 vs Ross $85,000.00 (delta $-39,276.61) -- GUARD_BLOCKED: Guards blocked 1362 re-entry attempts (1362 blocks) + OVERSIZED: Position size $87,828
  HIND: Bot $19,354.14 vs Ross $55,252.51 (delta $-35,898.37) -- GUARD_BLOCKED: Guards blocked 1706 re-entry attempts (1706 blocks) + OVERSIZED: Position size $88,224 + STOP_HIT: Technical stop triggered
  PAVM: Bot $19,046.82 vs Ross $43,950.00 (delta $-24,903.18) -- GUARD_BLOCKED: Guards blocked 15168 re-entry attempts (15168 blocks) + OVERSIZED: Position size $53,114 + STOP_HIT: Technical stop triggered
  MNTS: Bot $-15,502.64 vs Ross $9,000.00 (delta $-24,502.64) -- GUARD_BLOCKED: Guards blocked 2153 re-entry attempts (2153 blocks) + HELD_TO_CLOSE: Bot held losing position until close + OVERSIZED: Position size $72,649
  LRHC: Bot $10,810.77 vs Ross $31,076.62 (delta $-20,265.85) -- GUARD_BLOCKED: Guards blocked 92 re-entry attempts (92 blocks) + STOP_HIT: Technical stop triggered
  GRI: Bot $17,004.23 vs Ross $31,599.98 (delta $-14,595.75) -- STOP_HIT: Technical stop triggered
  BNKK: Bot $1,103.99 vs Ross $15,000.00 (delta $-13,896.01) -- STOP_HIT: Technical stop triggered
  NPT: Bot $68,021.20 vs Ross $81,000.00 (delta $-12,978.80) -- GUARD_BLOCKED: Guards blocked 6 re-entry attempts (6 blocks) + STOP_HIT: Technical stop triggered
  UOKA: Bot $-11,096.65 vs Ross $858.00 (delta $-11,954.65) -- GUARD_BLOCKED: Guards blocked 1355 re-entry attempts (1355 blocks) + OVERSIZED: Position size $40,383 + STOP_HIT: Technical stop triggered
  GWAV: Bot $-6,526.10 vs Ross $3,974.68 (delta $-10,500.78) -- GUARD_BLOCKED: Guards blocked 250 re-entry attempts (250 blocks) + OVERSIZED: Position size $104,972 + STOP_HIT: Technical stop triggered
  SNSE: Bot $343.14 vs Ross $9,373.32 (delta $-9,030.18) -- GUARD_BLOCKED: Guards blocked 136 re-entry attempts (136 blocks) + STOP_HIT: Technical stop triggered
  MLEC: Bot $-3,240.21 vs Ross $5,612.00 (delta $-8,852.21) -- GUARD_BLOCKED: Guards blocked 4964 re-entry attempts (4964 blocks) + OVERSIZED: Position size $53,096 + STOP_HIT: Technical stop triggered
  ONCO: Bot $-13,805.64 vs Ross $-5,500.00 (delta $-8,305.64) -- NO_RE_ENTRY: Bot never attempted re-entry after stop-out + STOP_HIT: Technical stop triggered
  RDIB: Bot $-5,137.12 vs Ross $700.00 (delta $-5,837.12) -- GUARD_BLOCKED: Guards blocked 374 re-entry attempts (374 blocks) + STOP_HIT: Technical stop triggered
  DCX: Bot $666.56 vs Ross $6,268.28 (delta $-5,601.72) -- STOP_HIT: Technical stop triggered
  FLYE: Bot $1,878.74 vs Ross $4,800.00 (delta $-2,921.26) -- GUARD_BLOCKED: Guards blocked 231 re-entry attempts (231 blocks) + OVERSIZED: Position size $78,008 + STOP_HIT: Technical stop triggered
  AIDX: Bot $-1,428.48 vs Ross $546.10 (delta $-1,974.58) -- NO_RE_ENTRY: Bot never attempted re-entry after stop-out + STOP_HIT: Technical stop triggered
  RNAZ: Bot $95.94 vs Ross $1,700.00 (delta $-1,604.06) -- GUARD_BLOCKED: Guards blocked 226 re-entry attempts (226 blocks) + STOP_HIT: Technical stop triggered
  NDRA: Bot $-1,053.00 vs Ross $13.15 (delta $-1,066.15) -- OVERSIZED: Position size $63,137 + STOP_HIT: Technical stop triggered
  RVSN: Bot $-4,045.47 vs Ross $-3,000.00 (delta $-1,045.47) -- NO_RE_ENTRY: Bot never attempted re-entry after stop-out + OVERSIZED: Position size $43,612 + STOP_HIT: Technical stop triggered
  ENVB: Bot $12,037.50 vs Ross $12,716.00 (delta $-678.50) -- GUARD_BLOCKED: Guards blocked 91 re-entry attempts (91 blocks) + STOP_HIT: Technical stop triggered
  BNRG: Bot $360.50 vs Ross $271.74 (delta $88.76) -- OVERSIZED: Position size $49,323 + STOP_HIT: Technical stop triggered
  VERO: Bot $3,578.92 vs Ross $3,484.88 (delta $94.04) -- OVERSIZED: Position size $88,318 + STOP_HIT: Technical stop triggered
  EDHL: Bot $672.57 vs Ross $-111.78 (delta $784.35) -- STOP_HIT: Technical stop triggered
  BCTX: Bot $5,768.45 vs Ross $4,500.00 (delta $1,268.45) -- OVERSIZED: Position size $90,709
  VELO: Bot $-33.50 vs Ross $-2,000.00 (delta $1,966.50) -- NO_RE_ENTRY: Bot never attempted re-entry after stop-out + STOP_HIT: Technical stop triggered
  LCFY: Bot $13,544.89 vs Ross $10,456.94 (delta $3,087.95) -- STOP_HIT: Technical stop triggered
  PMI: Bot $15,256.23 vs Ross $9,959.30 (delta $5,296.93) -- OVERSIZED: Position size $57,953 + STOP_HIT: Technical stop triggered
  TNMG: Bot $8,629.83 vs Ross $2,102.25 (delta $6,527.58) -- OVERSIZED: Position size $87,742 + STOP_HIT: Technical stop triggered
  BNAI: Bot $5,682.14 vs Ross $-7,900.00 (delta $13,582.14) -- STOP_HIT: Technical stop triggered
  SXTC: Bot $8,850.10 vs Ross $-5,000.00 (delta $13,850.10) -- OVERSIZED: Position size $54,029 + STOP_HIT: Technical stop triggered
  BATL: Bot $10,310.81 vs Ross $-6,700.00 (delta $17,010.81) -- OVERSIZED: Position size $87,426 + STOP_HIT: Technical stop triggered
  VHUB: Bot $20,516.05 vs Ross $1,600.00 (delta $18,916.05) -- OVERSIZED: Position size $81,160 + STOP_HIT: Technical stop triggered
  BATL: Bot $26,757.46 vs Ross $0.00 (delta $26,757.46) -- OVERSIZED: Position size $95,419 + STOP_HIT: Technical stop triggered
  PRFX: Bot $41,999.37 vs Ross $5,970.90 (delta $36,028.47) -- OVERSIZED: Position size $73,747 + STOP_HIT: Technical stop triggered
  BATL: Bot $48,748.70 vs Ross $0.00 (delta $48,748.70) -- OVERSIZED: Position size $88,310 + STOP_HIT: Technical stop triggered
  EVMN: Bot $42,354.93 vs Ross $-10,000.00 (delta $52,354.93) -- OVERSIZED: Position size $126,437
```
