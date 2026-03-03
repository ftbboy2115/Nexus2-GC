# Handoff: Fix Stop-Overwrite and Ghost Trade Bugs

**Agent:** Backend Specialist  
**Date:** 2026-03-02  
**Baseline:** 39 cases, $355,039, 79.5% capture (saved 2026-03-02 17:53)

---

## A/B Testing Protocol

Fix one bug at a time. After each fix:
1. Restart uvicorn server
2. Run `python scripts/gc_quick_test.py --all --diff`
3. If net positive or neutral → commit and proceed to next fix
4. If net negative → investigate why and report before proceeding

---

## Fix 1: Stop-Overwrite Bug (CRITICAL — est. +$15K)

`update_warrior_fill()` recalculates stop as `fill_price - 15¢`. When MockBroker fills above quote, the stop ends up ABOVE entry and can never fire.

**Evidence:** MNTS entry $7.80, stop stored as $8.40 (above entry).

### Change Point #1 — warrior_engine_entry.py:1443-1449
```python
# CURRENT (line 1443-1449):
mental_stop_cents = Decimal(str(engine.monitor.settings.mental_stop_cents))
actual_fill_decimal = Decimal(str(actual_fill_price))
actual_stop = actual_fill_decimal - mental_stop_cents / 100
update_warrior_fill(
    trade_id=order_id,
    actual_stop_price=float(actual_stop),  # ← Overwrites consolidation stop!
)

# FIX: Don't recalculate stop. Pass None to preserve original:
update_warrior_fill(
    trade_id=order_id,
    actual_stop_price=None,  # Preserve original consolidation stop
)
# Or: pass the original mental_stop from calculate_stop_price if available
```

### Change Point #2 — warrior_engine_entry.py:~1503
Same formula, same fix.

### Change Point #3 — warrior_entry_execution.py:584
Same formula, same fix.

### Change Point #4 — warrior_db.py:update_warrior_fill()
Add failsafe: if `actual_stop_price` is provided AND `>= actual_entry_price`, log WARNING and skip the overwrite.

### Verification
```powershell
python scripts/gc_quick_test.py --all --diff
```
Expected: MNTS should improve significantly (+$15K). No other cases should regress.

---

## Fix 2: Ghost Trade DB Bug (DATA QUALITY — est. neutral P&L)

Scale-ins create new DB rows via `log_warrior_entry()`, but EOD close only closes the first record found by `get_warrior_trade_by_symbol().first()`. 34 orphaned records.

### Change Point #1 — warrior_db.py
Add `get_all_warrior_trades_by_symbol(symbol)` that returns ALL active records (not `.first()`).

### Change Point #2 — sim_context.py:709
Replace single-record close with loop over all active records:
```python
# CURRENT (line 709):
trade = get_warrior_trade_by_symbol(pos_symbol)
if trade:
    log_warrior_exit(trade_id=trade["id"], ...)

# FIX:
trades = get_all_warrior_trades_by_symbol(pos_symbol)
for trade in trades:
    log_warrior_exit(trade_id=trade["id"], ...)
```

### Verification
```powershell
python scripts/gc_quick_test.py --all --diff
```
Expected: P&L should be approximately unchanged (ghost records had $0 P&L). The improvement is data quality — clean analysis numbers.

---

## DO NOT Fix in This Session

- MFE trail wiring (Priority 4 — needs param sweep, defer)
- Low-priced stock stop cap (Priority 3 — needs more analysis)
- Time-based breakeven (Priority 5 — speculative)

## Reference

- Planner report: `nexus2/reports/2026-03-02/research_bag_holding_deep_analysis.md`
- Write status to: `nexus2/reports/2026-03-02/backend_status_stop_overwrite_fix.md`
