# Algo Lab Generated Strategies

## Overview

Strategies discovered and validated by the R&D Lab's multi-agent system.

**System**: Algo Lab (R&D Lab)  
**Status**: 🔬 Experimental

---

## How Algo Lab Strategies Work

1. **Researcher Agent** hypothesizes new patterns
2. **Coder Agent** implements as scanner/monitor configs
3. **Evaluator Agent** backtests against historical data
4. **Promotion** to production if metrics pass thresholds

---

## Strategy Definition Format

Each generated strategy produces a configuration with:

```python
ScannerConfig:
  min_gap_percent: float
  min_volume: int
  max_float: int
  min_relative_volume: float
  # ... scanner criteria

MonitorConfig:
  entry_pattern: str  # PMH, ORB, PULLBACK, etc.
  stop_method: str    # candle_low, atr_based, fixed
  take_profit_r: float
  # ... trade management
```

---

## Current Experimental Strategies

| Strategy | Status | Win Rate | Notes |
|----------|--------|----------|-------|
| *(none promoted yet)* | - | - | - |

Strategies are added here as they pass evaluation thresholds.

---

## Evaluation Criteria

For a strategy to be promoted:

| Metric | Threshold |
|--------|-----------|
| Win Rate | > 50% |
| Profit Factor | > 1.5 |
| Min Trades | ≥ 20 in backtest |
| Max Drawdown | < 15% |

---

## Adding a New Algo Strategy

When the R&D Lab promotes a strategy:

1. Document core logic here
2. Include backtest results
3. Note any unique entry/exit rules
4. Reference the ScannerConfig/MonitorConfig

---

## Relationship to Established Strategies

Algo Lab strategies are **experimental** and may:
- Combine elements from Warrior + KK approaches
- Test novel patterns not in established methodologies
- Have different risk parameters

They should NOT be confused with production Warrior or KK strategies.
