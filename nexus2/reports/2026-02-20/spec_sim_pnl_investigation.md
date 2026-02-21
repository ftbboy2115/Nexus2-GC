# Sim Engine P&L Investigation — Technical Specification

**Date:** 2026-02-20
**Agent:** Backend Planner
**Reference:** `handoff_backend_planner_sim_pnl.md`

---

## Executive Summary

The MLEC batch test reports `entry_price=19.96`, `exit_price=18.91`, `shares=1302`, `pnl=+$244.19`. These numbers are internally inconsistent: `(19.96 - 18.91) × 1302 = +$1,367` for a short, or `-$1,367` for a long. Neither matches `+$244.19`. This investigation traces the root cause through code evidence.

**Root Cause:** The per-trade result fields (`entry_price`, `exit_price`, `shares`, `pnl`) are read from **four independent fields** in `warrior_db`, and the `pnl` is accumulated across **multiple partial exits** while `exit_price` only reflects the **final exit**. The displayed `entry_price` and `exit_price` do NOT represent the actual fills used for P&L calculation.

---

## A. Existing Architecture Analysis

### Two Independent P&L Systems

The sim engine maintains **two completely separate P&L calculations**:

| System | Location | Formula | Used For |
|--------|----------|---------|----------|
| **MockBroker** | [mock_broker.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/simulation/mock_broker.py#L437) | `(current_price - avg_entry_price) × sell_qty` | Top-level `total_pnl` in result |
| **warrior_db** | [warrior_db.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/db/warrior_db.py#L390-L393) | `(exit_price - entry) × remaining_quantity` | Per-trade `pnl` in result (the one displayed) |

### Result Assembly

In [_run_single_case_async](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L586-L630):

```python
# Top-level P&L: from MockBroker
account = ctx.broker.get_account()
realized = round(account.get("realized_pnl", 0), 2)  # Line 588

# Per-trade P&L: from warrior_db
for wt in result.get("trades", []):
    trades.append({
        "entry_price": round(float(wt.get("entry_price", 0)), 2),     # L602
        "exit_price": round(float(wt.get("exit_price", 0)), 2),       # L603
        "shares": wt.get("quantity", 0),                               # L604
        "pnl": round(float(wt.get("realized_pnl", 0)), 2),            # L605
    })
```

**Key insight:** The `pnl` field shown to the user comes from `warrior_db.realized_pnl` (accumulated across partials), NOT from MockBroker's calculation.

---

## B. Root Cause Analysis

### B.1: P&L is Accumulated Across Multiple Exits

**Finding:** `log_warrior_exit` accumulates P&L across partial and full exits
**File:** [warrior_db.py:390-404](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/db/warrior_db.py#L390-L404)
**Code:**
```python
# Full exit (L390-393):
remaining_pnl = (exit_price - entry) * trade.remaining_quantity
trade.realized_pnl = str(round(float(trade.realized_pnl or "0") + remaining_pnl, 2))

# Partial exit (L401-404):
partial_pnl = (exit_price - entry) * quantity_exited
trade.realized_pnl = str(round(float(trade.realized_pnl or "0") + partial_pnl, 2))
```

**Scenario that produces the observed discrepancy:**

1. **Entry** at $X (say $19.96), 1302 shares
2. **Partial exit** of ~651 shares at a higher price (say $20.15) → P&L += +$0.19 × 651 = +$123.69
3. **Full exit** of remaining ~651 shares at $18.91 → P&L += ($18.91 - $19.96) × 651 = -$683.55
4. **But**: The PARTIAL exit P&L is already banked. Total = +$123.69 + (-$683.55) would be negative
5. **Or**: With different partial sizing/pricing, the partial could dominate

The exact arithmetic depends on WHEN the partial is taken and at WHAT price.

### B.2: exit_price Only Shows the LAST Exit

**Finding:** `exit_price` is ONLY set on full exit, not partial
**File:** [warrior_db.py:386](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/db/warrior_db.py#L384-L394)
**Code:**
```python
if quantity_exited is None or quantity_exited >= trade.remaining_quantity:
    # Full exit
    trade.exit_price = str(exit_price)  # <-- ONLY set here
    ...
else:
    # Partial exit
    # exit_price NOT updated in the DB record
```

**Conclusion:** The `exit_price=$18.91` in the result is the LAST (full) exit price, but `realized_pnl=$244.19` includes P&L from EARLIER partial exits at different (higher) prices.

### B.3: shares Shows INITIAL Quantity

**Finding:** The result reads `wt.get("quantity", 0)` which is the INITIAL entry quantity
**File:** [sim_context.py:604](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L604)
**Code:** `"shares": wt.get("quantity", 0)`

The `quantity` field in warrior_db is the original entry quantity (1302), not the shares at final exit (which could be fewer due to partials).

### B.4: Wall-Clock Timestamps

**Finding:** `log_warrior_entry` uses `now_utc()` for `entry_time`
**File:** [warrior_db.py:295](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/db/warrior_db.py#L295)
**Code:** `entry_time=now_utc()`

**Finding:** `log_warrior_exit` uses `now_utc()` for `exit_time`
**File:** [warrior_db.py:387](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/db/warrior_db.py#L387)
**Code:** `trade.exit_time = now_utc()`

**Conclusion:** Both entry and exit timestamps are wall-clock time, not simulated market time. This explains why `entry_time=2026-02-20T23:16:57Z` (6:16 PM ET), well after market close.

---

## C. Full P&L Flow Trace

```
enter_position() [warrior_engine_entry.py:955]
    └─ _submit_order() → sim_submit_order_historical() [sim_context.py:446]
        └─ MockBroker.submit_bracket_order() [mock_broker.py:171]
            └─ _fill_entry_order() [mock_broker.py:286]
                ├─ Creates MockPosition(avg_entry_price=fill_price)
                └─ Updates cash
    └─ log_warrior_entry(entry_price=...) [warrior_db.py:262]
        └─ Stores entry_price as STRING in SQL

evaluate_position() [warrior_monitor_exit.py:1189]
    └─ _check_base_hit_target() [L733]
        └─ Returns WarriorExitSignal(exit_price=current_price, shares_to_exit=N)

handle_exit() [warrior_monitor_exit.py:1305]
    └─ _execute_exit(signal) → sim_execute_exit() [sim_context.py:307]
        ├─ MockBroker.sell_position() [mock_broker.py:415]
        │   └─ pnl = (current_price - avg_entry_price) × sell_qty
        │   └─ _realized_pnl += pnl  ← MockBroker's P&L
        └─ log_warrior_exit() [warrior_db.py:370]
            └─ pnl = (exit_price - entry) × remaining_quantity
            └─ realized_pnl += pnl  ← warrior_db's P&L (ACCUMULATED)

_run_single_case_async() [sim_context.py:526]
    ├─ Result total_pnl: from ctx.broker.get_account()["realized_pnl"]  ← MockBroker
    └─ Result trade.pnl:  from warrior_db "realized_pnl"               ← warrior_db
```

### Where MockBroker and warrior_db P&L DIVERGE

| Scenario | MockBroker | warrior_db | Match? |
|----------|-----------|------------|--------|
| Single entry, single exit, no partials | ✅ `(exit - avg_entry) × qty` | ✅ `(exit - entry) × qty` | **Usually yes** (avg_entry == entry for single entry) |
| Single entry, partial then full | ✅ Correct: each sell uses `current_price` and `avg_entry_price` | ✅ Correct: each exit calculated independently against stored `entry_price` | **Yes** (same entry_price used) |
| Scale-in (multiple entries, avg price shifts) | ✅ Uses updated `avg_entry_price` | ❌ Uses ORIGINAL `entry_price` (may have been updated by `complete_scaling`) | **May diverge** |
| Limit fill at different price than quote | ✅ Uses actual fill price | ❌ Initial write uses quote, `update_warrior_fill` should correct it | **Usually corrected** |

---

## D. Investigative Findings for the MLEC Case

### D.1: The +$244.19 P&L Is Likely Correct (Accumulated)

Given the `exit_mode=base_hit` and `exit_reason=mental_stop`, the trade lifecycle was likely:

1. Enter 1302 shares at ~$19.96
2. `base_hit` mode with `enable_partial_then_ride` enabled → partial exit of ~651 shares at a profit (candle trail or flat target hit)
3. Remainder switches to `home_run` mode → gets stopped out at $18.91 (mental_stop)
4. Total `realized_pnl` = partial_pnl + (loss on remaining) = +$244.19

The `exit_reason=mental_stop` on the record is from the FINAL full exit, which was a loss. But the partial was profitable enough to make the total positive.

### D.2: The $18.91 exit_price Is the FINAL Exit Only

The `exit_price` field only gets written on full exit (L386 of warrior_db.py). The earlier partial exit price is NOT recorded in this field. So the displayed exit_price=$18.91 is misleading — it's only the last chunk.

### D.3: The Short Position Hypothesis Is Ruled Out

The sim engine is long-only:
- `_fill_entry_order` always creates `side="buy"` orders (L319)
- `submit_bracket_order` always uses `side="buy"` (L384)
- `sim_submit_order_historical` passes `side="buy"` (L1161 of warrior_engine_entry.py)
- No short-selling logic exists anywhere in the entry or sim code

---

## E. Issues Identified and Recommendations

### Issue #1: Displayed `exit_price` is Misleading for Partial Exits

**Problem:** Users see `entry_price=19.96, exit_price=18.91, pnl=+244` and can't reconcile
**Root cause:** `exit_price` only shows final exit, P&L is accumulated
**Recommendation:** Add `partial_exits` list to per-trade result, or compute `avg_exit_price` that accounts for all exits

### Issue #2: Wall-Clock Timestamps in Sim Mode

**Problem:** `entry_time=2026-02-20T23:16:57Z` vs actual sim time during replay
**Root cause:** `log_warrior_entry` and `log_warrior_exit` use `now_utc()` unconditionally
**Recommendation:** Pass simulated time from `ctx.clock` when in sim mode

### Issue #3: Display Doesn't Show Partial Flow

**Problem:** No way to tell from the result that a partial exit occurred
**Root cause:** Only final state is serialized from warrior_db
**Recommendation:** Include `partial_taken`, `remaining_quantity`, and individual exit records in the per-trade result

### Issue #4: Two P&L Systems Can Diverge

**Problem:** `total_pnl` (from MockBroker) and per-trade `pnl` (from warrior_db) may not agree
**Root cause:** Independent calculations, different entry price sources (MockBroker uses `avg_entry_price`, warrior_db uses stored string `entry_price`)
**Recommendation:** Single source of truth for P&L. Either derive from MockBroker consistently, or make warrior_db the sole P&L authority.

---

## F. Change Surface Enumeration

If the above recommendations are approved for implementation:

| # | File | Change | Priority |
|---|------|--------|----------|
| 1 | `sim_context.py` L601-615 | Include `partial_taken`, `remaining_quantity` in per-trade result | Medium |
| 2 | `sim_context.py` L601-615 | Compute weighted `avg_exit_price` for display | Medium |
| 3 | `warrior_db.py` L295 | Use sim clock time when `is_sim=True` | Low |
| 4 | `warrior_db.py` L387 | Use sim clock time when in sim context | Low |
| 5 | `sim_context.py` L601-615 | Add sim clock times from `sim_time` field in MockOrder | Low |
| 6 | `warrior_db.py` L396-404 | Store partial exit price/shares for audit | Medium |

---

## G. Risk Assessment

- **Issue #1** (misleading exit_price) is purely cosmetic/display — does NOT affect trading decisions
- **Issue #2** (wall-clock timestamps) makes logs confusing but doesn't affect P&L accuracy
- **Issue #3** (no partial visibility) makes debugging hard but doesn't affect correctness
- **Issue #4** (two P&L systems) could cause real discrepancies if scale-ins shift `avg_entry_price` in MockBroker

**The +$244.19 P&L value itself is likely CORRECT** — it's just that the displayed `entry_price` and `exit_price` don't tell the full story when partials are involved.
