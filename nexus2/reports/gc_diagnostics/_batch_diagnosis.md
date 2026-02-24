# Batch Diagnosis Report

**Generated:** 2026-02-24 08:37:57

```
Batch Diagnosis Report (35 cases)
Bot Total: $161,115.70 | Ross Total: $432,999.62 | Capture: 37.2%

Issue Priority Ranking:
[P1-CRIT] GUARD_BLOCKED: 11 cases, ~$222,197 P&L gap
   Cases: PAVM, ROLR, LRHC, HIND, BCTX, RNAZ, MNTS, PRFX (+3 more)
   Fix: Review MACD and reentry guard aggressiveness
[P2-HIGH] STOP_HIT: 12 cases, ~$162,405 P&L gap
   Cases: BATL, BNKK, GWAV, GRI, DCX, NPT, BNAI, RVSN (+4 more)
   Fix: Evaluate stop width -- may be too tight or too wide
[P3-MED] OVERSIZED: 3 cases, ~$50,480 P&L gap
   Cases: BATL, VERO, SXTC
   Fix: Review position sizing relative to stop distance
[P4-LOW] NO_RE_ENTRY: 6 cases, ~$31,782 P&L gap
   Cases: LCFY, FLYE, RDIB, VELO, BNRG, ONCO
   Fix: Add re-entry logic after stop-out on strong runners
[P5] UNKNOWN: 1 cases, ~$1,600 P&L gap
   Cases: VHUB
   Fix: Manual investigation needed
[P6] OK: 1 cases, ~$50 P&L gap
   Cases: TNMG
   Fix: No action needed
[P6] PARTIAL: 1 cases, ~$2 P&L gap
   Cases: ENVB
   Fix: Fine-tune entry timing and scaling

Guard Blocks: 11283 total ()

Guard Effectiveness Analysis:
  Analyzed: 2255 blocks | Correct: 1374 | Missed: 835 | Accuracy: 0.622
  Net Guard Impact: $-1,363.28 (negative = guards saved money)
    reentry_loss: 3311 blocks, accuracy=313/476, impact=$-711.97
    macd: 5860 blocks, accuracy=715/1144, impact=$-640.41
    position: 2055 blocks, accuracy=331/574, impact=$-8.11
    sim_cooldown: 57 blocks, accuracy=15/15, impact=$-2.80

Per-Case Summary (sorted by delta, worst first):
  NPT: Bot $17,538.56 vs Ross $81,000.00 (delta $-63,461.44) -- STOP_HIT: Technical stop triggered
  MLEC: Bot $-2,997.38 vs Ross $43,000.00 (delta $-45,997.38) -- GUARD_BLOCKED: Guards blocked 878 re-entry attempts (878 blocks) + OVERSIZED: Position size $58,026 + STOP_HIT: Technical stop triggered
  PAVM: Bot $105.11 vs Ross $43,950.00 (delta $-43,844.89) -- GUARD_BLOCKED: Guards blocked 54 re-entry attempts (54 blocks) + STOP_HIT: Technical stop triggered
  HIND: Bot $14,110.46 vs Ross $55,252.51 (delta $-41,142.05) -- GUARD_BLOCKED: Guards blocked 474 re-entry attempts (474 blocks) + STOP_HIT: Technical stop triggered
  LRHC: Bot $868.68 vs Ross $31,076.62 (delta $-30,207.94) -- GUARD_BLOCKED: Guards blocked 54 re-entry attempts (54 blocks) + STOP_HIT: Technical stop triggered
  GRI: Bot $5,351.11 vs Ross $31,599.98 (delta $-26,248.87) -- STOP_HIT: Technical stop triggered
  ROLR: Bot $61,565.78 vs Ross $85,000.00 (delta $-23,434.22) -- GUARD_BLOCKED: Guards blocked 220 re-entry attempts (220 blocks) + STOP_HIT: Technical stop triggered
  MNTS: Bot $-7,046.15 vs Ross $9,000.00 (delta $-16,046.15) -- GUARD_BLOCKED: Guards blocked 165 re-entry attempts (165 blocks) + HELD_TO_CLOSE: Bot held losing position until close + OVERSIZED: Position size $51,072
  LCFY: Bot $-4,832.56 vs Ross $10,456.94 (delta $-15,289.50) -- NO_RE_ENTRY: Bot never attempted re-entry after stop-out + OVERSIZED: Position size $41,327 + STOP_HIT: Technical stop triggered
  BNKK: Bot $180.09 vs Ross $15,000.00 (delta $-14,819.91) -- STOP_HIT: Technical stop triggered
  SNSE: Bot $-207.14 vs Ross $9,373.32 (delta $-9,580.46) -- GUARD_BLOCKED: Guards blocked 110 re-entry attempts (110 blocks) + HELD_TO_CLOSE: Bot held losing position until close
  FLYE: Bot $-3,866.10 vs Ross $4,800.00 (delta $-8,666.10) -- NO_RE_ENTRY: Bot never attempted re-entry after stop-out + STOP_HIT: Technical stop triggered
  PRFX: Bot $0.00 vs Ross $5,970.90 (delta $-5,970.90) -- GUARD_BLOCKED: Guards blocked 108 re-entry attempts (108 blocks) + OVERSIZED: Position size $44,400
  DCX: Bot $558.95 vs Ross $6,268.28 (delta $-5,709.33) -- STOP_HIT: Technical stop triggered
  BNRG: Bot $-4,525.50 vs Ross $271.74 (delta $-4,797.24) -- NO_RE_ENTRY: Bot never attempted re-entry after stop-out + OVERSIZED: Position size $44,608 + STOP_HIT: Technical stop triggered
  MLEC: Bot $1,060.39 vs Ross $5,612.00 (delta $-4,551.61) -- GUARD_BLOCKED: Guards blocked 880 re-entry attempts (880 blocks) + OVERSIZED: Position size $126,045 + STOP_HIT: Technical stop triggered
  PMI: Bot $7,051.50 vs Ross $9,959.30 (delta $-2,907.80) -- STOP_HIT: Technical stop triggered
  VELO: Bot $-3,908.42 vs Ross $-2,000.00 (delta $-1,908.42) -- NO_RE_ENTRY: Bot never attempted re-entry after stop-out + STOP_HIT: Technical stop triggered
  GWAV: Bot $2,179.45 vs Ross $3,974.68 (delta $-1,795.23) -- STOP_HIT: Technical stop triggered
  VHUB: Bot $0.00 vs Ross $1,600.00 (delta $-1,600.00) -- UNKNOWN: Needs manual review
  RNAZ: Bot $425.81 vs Ross $1,700.00 (delta $-1,274.19) -- GUARD_BLOCKED: Guards blocked 162 re-entry attempts (162 blocks) + STOP_HIT: Technical stop triggered
  RDIB: Bot $-98.70 vs Ross $700.00 (delta $-798.70) -- NO_RE_ENTRY: Bot never attempted re-entry after stop-out + STOP_HIT: Technical stop triggered
  BCTX: Bot $4,352.97 vs Ross $4,500.00 (delta $-147.03) -- GUARD_BLOCKED: Guards blocked 175 re-entry attempts (175 blocks) + OVERSIZED: Position size $68,882
  ENVB: Bot $1.50 vs Ross $0.00 (delta $1.50) -- PARTIAL: Bot profitable but below Ross
  TNMG: Bot $2,151.95 vs Ross $2,102.25 (delta $49.70) -- OK: Bot captured most of Ross P&L
  ONCO: Bot $-5,178.24 vs Ross $-5,500.00 (delta $321.76) -- NO_RE_ENTRY: Bot never attempted re-entry after stop-out + STOP_HIT: Technical stop triggered
  EDHL: Bot $1,632.00 vs Ross $-111.78 (delta $1,743.78) -- STOP_HIT: Technical stop triggered
  RVSN: Bot $200.87 vs Ross $-3,000.00 (delta $3,200.87) -- STOP_HIT: Technical stop triggered
  UOKA: Bot $5,645.68 vs Ross $858.00 (delta $4,787.68) -- STOP_HIT: Technical stop triggered
  BATL: Bot $7,740.00 vs Ross $0.00 (delta $7,740.00) -- STOP_HIT: Technical stop triggered
  BNAI: Bot $1,454.67 vs Ross $-7,900.00 (delta $9,354.67) -- STOP_HIT: Technical stop triggered
  SXTC: Bot $6,600.00 vs Ross $-5,000.00 (delta $11,600.00) -- OVERSIZED: Position size $47,850 + STOP_HIT: Technical stop triggered
  VERO: Bot $19,071.95 vs Ross $3,484.88 (delta $15,587.07) -- OVERSIZED: Position size $44,694 + STOP_HIT: Technical stop triggered
  EVMN: Bot $10,635.45 vs Ross $-10,000.00 (delta $20,635.45) -- STOP_HIT: Technical stop triggered
  BATL: Bot $23,292.96 vs Ross $0.00 (delta $23,292.96) -- OVERSIZED: Position size $53,556 + STOP_HIT: Technical stop triggered
```
