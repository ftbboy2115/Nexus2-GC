# MACD Block Bucket Analysis

**Generated:** 2026-02-24 22:06:38

```
MACD Block Bucket Analysis (35 cases, 8589 MACD blocks)
============================================================

Histogram Distribution:
            <-0.50:    68 blocks
    -0.50 to -0.30:  ███  298 blocks
    -0.30 to -0.10:  ███████  734 blocks
    -0.10 to -0.05:  █████████  865 blocks
    -0.05 to -0.02:  ████████████████████████████████████████  3,739 blocks
  (Note: -0.02 to 0 = tolerance zone, not blocked)

Bucket Classification:
Bucket                           |  Count |     % |  Avg Hist | SAVED |  COST | NEUTRAL | Net P&L/sh
----------------------------------------------------------------------------------------------------
A (deeply negative)              |  1,100 | 12.8% |   -0.2542 |   207 |   492 |     401 | $  1747.62
B (near-zero oscillation)        |  7,489 | 87.2% |   -0.0271 |   938 |  2429 |    4122 | $  3292.58

  A (deeply negative):
    Histogram range: [-0.8739, -0.1039]
    Block accuracy: 29.6% (207/699)
    Net impact: $1747.62/share (positive = guards COST money)

  B (near-zero oscillation):
    Histogram range: [-0.0886, -0.0001]
    Block accuracy: 27.9% (938/3367)
    Net impact: $3292.58/share (positive = guards COST money)

============================================================
RECOMMENDATION:

  >>> INSUFFICIENT DATA for Bucket C <<<
  Could not compute enough trajectories to classify B vs C.
  Review tolerance threshold separately.

  Bucket B accuracy is 27.9% — consider widening tolerance from -0.02.

  Bucket A accuracy: 29.6% — deeply negative blocks are questionably blocked.

Top 10 Symbols by MACD Block Count:
  BATL: 5872 blocks
  MLEC: 946 blocks
  ROLR: 297 blocks
  VERO: 293 blocks
  TNMG: 264 blocks
  PAVM: 234 blocks
  UOKA: 176 blocks
  PRFX: 176 blocks
  LRHC: 88 blocks
  RNAZ: 88 blocks

```

## Raw Data Summary

- Total MACD blocks: 8589
- Unparseable blocks: 340
- Trajectories computed: 0
- Trajectories failed: 7489
- Counterfactual matched: 4079/8589

### Per-Bucket Breakdown

**Bucket A:** 1100 blocks, avg hist=-0.2542, saved=207, cost=492, neutral=401, net_pnl=$1747.62/sh

**Bucket B:** 7489 blocks, avg hist=-0.0271, saved=938, cost=2429, neutral=4122, net_pnl=$3292.58/sh

