# Backend Status: Stop-Overwrite & Ghost Trade Fixes

**Agent:** Backend Specialist  
**Date:** 2026-03-02  
**Reference:** `handoff_specialist_stop_overwrite.md`

---

## Summary

Both bugs fixed and A/B tested. **Neither fix changed sim P&L** ($355,039, 79.5% capture, unchanged). Both are **code safety and data quality** improvements that matter for LIVE mode and analysis accuracy, not sim P&L.

---

## Fix 1: Stop-Overwrite Bug — COMPLETE ✅

### Changes Made

| # | File | Line | Change |
|---|------|------|--------|
| 1 | `warrior_engine_entry.py` | 1443-1451 | `actual_stop_price=None` (was `fill - 15¢`) |
| 2 | `warrior_engine_entry.py` | 1503 | `actual_stop = mental_stop` (was `fill - 15¢`) |
| 3 | `warrior_engine_entry.py` | 1518-1523 | `actual_stop_price=None` (second update call) |
| 4 | `warrior_entry_execution.py` | 584 | `actual_stop_price=None` (extracted copy) |
| 5 | `warrior_entry_execution.py` | 637, 652 | Same fix as #2 and #3 in extracted copy |
| 6 | `warrior_db.py` | 327-395 | Failsafe: reject stop ≥ entry with WARNING |

### Why $0 Sim Impact

In sim, `_get_order_status = None` (sim_context.py:521), so the fill poll loop never runs. `actual_fill_price` always equals `entry_price`, making `entry - 0.15` always below entry. The inverted stop bug only triggers in **LIVE mode** when broker fills above quote due to slippage.

The planner's +$15K estimate assumed the MNTS DB record (`stop=$8.40, entry=$7.80`) came from batch test — it likely came from a different code path or live run. The MNTS -$15.5K sim loss is from price action (held to EOD), not an inverted stop.

### LIVE Mode Value

> [!IMPORTANT]
> This fix is **critical for LIVE safety**. Without it, any trade where broker fills above quote price (common with momentum stocks) gets an inverted stop that can never fire, causing bag-holding to EOD.

The failsafe in `warrior_db.py` adds a second layer: even if a future caller passes a bad stop, it will be rejected with a WARNING log.

### A/B Test Result

```
Improved:  0/39 | Regressed: 0/39 | Unchanged: 39/39
Net change: $+0.00
```

---

## Fix 2: Ghost Trade DB Bug — COMPLETE ✅

### Changes Made

| # | File | Line | Change |
|---|------|------|--------|
| 1 | `warrior_db.py` | 493-519 | New: `get_all_warrior_trades_by_symbol()` returns ALL active records |
| 2 | `sim_context.py` | 363-376 | `sim_execute_exit`: close ALL records (was `.first()`) |
| 3 | `sim_context.py` | 707-722 | EOD close: close ALL records (was `.first()`) |

### Why $0 Sim Impact

Ghost records had `$0 P&L` and `exit_reason=null`. Closing them properly doesn't change MockBroker's `realized_pnl` (which is the batch test's P&L source). The fix improves **data quality**: clean trade counts, accurate win rates, and correct trigger analysis.

### A/B Test Result

```
Improved:  0/39 | Regressed: 0/39 | Unchanged: 39/39
Net change: $+0.00
```

---

## Baseline

```
39 cases, $355,038.66, 79.5% capture
Saved: 2026-03-02 ~22:00
```

---

## Testable Claims (for Testing Specialist)

| # | Claim | File:Line | Verification |
|---|-------|-----------|-------------|
| 1 | `update_warrior_fill` accepts `actual_stop_price=None` without error | `warrior_db.py:330` | `grep "actual_stop_price: float = None"` |
| 2 | Failsafe rejects stop ≥ entry | `warrior_db.py:363` | `grep "actual_stop_price >= actual_entry_price"` |
| 3 | `get_all_warrior_trades_by_symbol` exists and returns list | `warrior_db.py:493` | `grep "def get_all_warrior_trades_by_symbol"` |
| 4 | `sim_context.py` EOD close uses `get_all_warrior_trades_by_symbol` | `sim_context.py:~710` | `grep "get_all_warrior_trades_by_symbol" sim_context.py` |
| 5 | `sim_context.py` exit callback uses `get_all_warrior_trades_by_symbol` | `sim_context.py:~363` | Same grep |
| 6 | No stop recalculation from fill price in `warrior_engine_entry.py` | `warrior_engine_entry.py:1443` | `grep "actual_stop_price=None" warrior_engine_entry.py` |

---

## Open Questions for Coordinator

1. **MNTS -$15.5K**: The stop-overwrite fix doesn't explain this sim loss. A separate investigation is needed to determine why the monitor's stop isn't firing (could be a monitor stop calculation issue separate from the DB stop).

2. **LIVE mode deployment**: These fixes should be deployed to VPS before next trading session. The stop-overwrite fix is safety-critical for live orders.

3. **Ghost trades in LIVE DB**: The planner noted 34 orphaned records in the live `warrior.db`. A cleanup script may be needed to close stale `status=open` records that could interfere with re-entry guards and restart recovery.
