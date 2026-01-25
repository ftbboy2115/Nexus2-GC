# Simulation vs Live Trading Fidelity

> Last updated: 2026-01-25

This document maps the alignment between the **MockMarket simulation** and **live Warrior trading** to clarify what the simulation tests accurately vs. known gaps.

---

## Code Path Alignment

### ✅ Shared Logic (Same Code)

| Component | File | Notes |
|-----------|------|-------|
| **Entry triggers** | `warrior_engine_entry.py` | ORB, PMH, DIP detection |
| **Entry guards** | `warrior_engine_entry.py` | MACD gate, VWAP, score checks, blacklist |
| **Position sizing** | `warrior_engine_entry.py` | Candle low stop, ATR risk calc |
| **Exit mode selection** | `warrior_engine_entry.py` | base_hit vs home_run by quality score |
| **Monitor exit logic** | `warrior_monitor_exit.py` | Mental stops, profit targets, partials |
| **Technical validation** | `warrior_engine_entry.py` | VWAP/EMA checks |

### ⚠️ Different Paths (Sim vs Live)

| Aspect | Simulation (MockBroker) | Live (AlpacaBroker) |
|--------|-------------------------|---------------------|
| **Order submission** | `sim_submit_order()` callback | `AlpacaBroker.submit_bracket_order()` |
| **Position sell** | `MockBroker.sell_position()` | `AlpacaBroker.close_position()` |
| **Fill execution** | Instant at current price | Real order flow |
| **Order types** | All recorded as "limit" | Actual limit orders |

---

## Execution Realism

### What Sim Does Accurately

- ✅ **Trigger detection timing** - same clock logic
- ✅ **Entry guard filtering** - identical checks
- ✅ **Position sizing math** - same calculations
- ✅ **Exit rule evaluation** - same monitor logic
- ✅ **Quality score → exit mode** - same mapping

### What Sim Simplifies

| Gap | Sim Behavior | Live Reality | Impact |
|-----|--------------|--------------|--------|
| **Slippage** | None - exact price fills | ~0.1-0.5% on volatile stocks | P&L optimistic |
| **Partial fills** | Always 100% fill | May get partials | Position size may differ |
| **Fill delay** | Instant | 100ms-2s typical | Timing differs |
| **Bid/ask spread** | Not modeled | Real spread cost | Entry/exit prices differ |
| **Pre/post market** | Fills anytime | Market hours restrictions | Sim allows unrealistic fills |
| **Order rejections** | Only buying power | Broker/exchange rejections | Fewer failures in sim |

---

## Callback Mapping

```
SIMULATION PATH:
warrior_engine_entry.enter_position()
  → engine._submit_order (sim_submit_order callback)
    → MockBroker.submit_bracket_order()

warrior_monitor_exit.evaluate_exits()
  → warrior_sim_routes.process_exit_signal()
    → MockBroker.sell_position()

LIVE PATH:
warrior_engine_entry.enter_position()
  → engine._submit_order (alpaca callback)
    → AlpacaBroker.submit_bracket_order()

warrior_monitor_exit.evaluate_exits()
  → (same logic, different callback)
    → AlpacaBroker.close_position()
```

---

## Known Acceptable Gaps

1. **Instant fills** - acceptable for logic testing
2. **No slippage** - live P&L will be ~1-3% worse
3. **No partial fills** - position sizes match in sim
4. **Pre-market fills** - sim allows, live may differ

## Future Improvements (Not Urgent)

- [ ] Add configurable slippage model (e.g., 0.2% per trade)
- [ ] Model bid/ask spread impact
- [ ] Simulate fill delays for realism
- [ ] Add random partial fill simulation

---

## Summary

**Simulation fidelity: ~85% for logic, ~50% for execution**

The sim is reliable for testing:
- Entry trigger accuracy
- Exit rule behavior
- Position sizing calculations

The sim is NOT reliable for:
- Actual P&L prediction
- Fill quality assessment
- Order rejection handling
