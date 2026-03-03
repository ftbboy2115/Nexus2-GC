# Deep Analysis: Bag Holding, Ghost Trade Bug, and Stop-Overwrite Bug

**Agent:** Backend Planner
**Date:** 2026-03-02
**Reference:** `handoff_planner_bag_holding_deep.md`
**Data:** 42 real trades across 38 cases (34 ghost trades filtered)

---

## Executive Summary

This investigation uncovered **two bugs** and a **data quality problem** that were masking the true performance picture:

1. **Ghost Trade DB Bug** — 34 of 76 trade records are orphaned scale-in rows with `exit_reason=null`, inflating trigger counts and destroying win rate accuracy. `hod_break` is actually 60% win rate (not 10.3%).
2. **Stop-Overwrite Bug** — `update_warrior_fill()` replaces the consolidation-based stop with `fill_price - 15¢`, which can set the stop ABOVE entry price (MNTS: stop=$8.40, entry=$7.80).
3. **Wide stops on low-priced stocks** — 5 `technical_stop` losses totaling -$43K from stops at 15-22% of entry price.

> [!IMPORTANT]
> The original analysis using raw 76-trade data produced **misleading conclusions**. `hod_break` was reported as the worst trigger (10.3% win rate) but is actually the 2nd best (60% win rate, $9K avg). All prior recommendations based on the raw data should be reconsidered.

---

## Bug #1: Ghost Trade DB Records (34 orphaned rows)

### Evidence

**Total trades in DB:** 76
**Real trades (exit_reason IS NOT NULL):** 42
**Ghost trades (exit_reason IS NULL, pnl=$0):** 34

### Root Cause (VERIFIED)

Scale-ins create new DB rows, but exit/EOD close only updates the first record found.

**Code Path 1 — Scale-in creates new DB row:**
**File:** [warrior_engine_entry.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py#L1258-L1284)
```python
# Line 1258-1267: Each scale-in calls log_warrior_entry with a NEW order_id
from nexus2.db.warrior_db import log_warrior_entry, set_entry_order_id
log_warrior_entry(
    trade_id=order_id,       # NEW unique ID for each scale-in
    symbol=symbol,
    entry_price=float(entry_price),
    ...
)
```

**Code Path 2 — EOD close finds only FIRST record:**
**File:** [sim_context.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L704-L719)
```python
# Line 709: Uses get_warrior_trade_by_symbol which returns .first()
trade = get_warrior_trade_by_symbol(pos_symbol)
if trade:
    log_warrior_exit(
        trade_id=trade["id"],  # Only closes the FIRST record
        exit_price=float(eod_price),
        exit_reason="eod_close",
        quantity_exited=pos_qty,
    )
```

**Code Path 3 — `.first()` returns arbitrary single record:**
**File:** [warrior_db.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/db/warrior_db.py#L445-L473)
```python
# Line 469: Returns only the FIRST matching active record
trade = db.query(WarriorTradeModel).filter(
    WarriorTradeModel.symbol == symbol,
    WarriorTradeModel.status.in_(active_statuses)
).first()  # ← Only 1 of N records!
```

### Impact

| Metric | Raw (76 trades) | Clean (42 trades) | Correction |
|--------|:---:|:---:|:---|
| `hod_break` win% | **10.3%** | **60%** | 24 ghost trades inflated count |
| `hod_break` count | 29 | 5 | 24 were orphaned scale-ins |
| `micro_pullback` count | 8 | 2 | 6 were orphaned scale-ins |
| `micro_pullback` avg | $12.5K | $36K | Ghost $0 trades dragged down avg |

### LIVE Mode Risk

> [!WARNING]
> In LIVE mode, orphaned `status=open` records would interfere with:
> - `get_warrior_trade_by_symbol()` returning a stale record instead of the active one
> - Re-entry guards that check for existing open trades
> - Restart recovery (`get_open_warrior_trades()`) creating phantom positions
>
> **This bug likely already affects live trading.** Needs investigation.

### Fix Options

**Option A (Recommended):** At EOD close, close ALL open records for the symbol:
```python
# sim_context.py line 709 — replace single lookup with loop
trades = get_all_warrior_trades_by_symbol(pos_symbol)  # New function
for trade in trades:
    log_warrior_exit(trade_id=trade["id"], ...)
```

**Option B:** Don't create new DB rows for scale-ins. Instead update the existing record's shares/avg_price. This matches how `WarriorPosition` works in-memory.

---

## Bug #2: Stop-Overwrite in update_warrior_fill

### Evidence

MNTS trade data:
```json
{
  "entry_price": 7.80,
  "stop_price": "8.4",
  "stop_method": "consolidation_low_capped",
  "support_level": "5.88"
}
```

Stop $8.40 is **above** entry $7.80 — the stop can never fire.

### Root Cause (VERIFIED)

**File:** [warrior_engine_entry.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py#L1443-L1449)
```python
# Line 1443-1449: Overwrites consolidation stop with fill_price - 15¢
mental_stop_cents = Decimal(str(engine.monitor.settings.mental_stop_cents))
actual_fill_decimal = Decimal(str(actual_fill_price))
actual_stop = actual_fill_decimal - mental_stop_cents / 100
update_warrior_fill(
    trade_id=order_id,
    actual_stop_price=float(actual_stop),  # ← Overwrites consolidation stop!
)
```

The same pattern appears at line 1503:
```python
actual_stop = actual_fill_decimal - Decimal(str(engine.monitor.settings.mental_stop_cents)) / 100
```

And in the extracted copy at [warrior_entry_execution.py:584](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_execution.py#L583-L584):
```python
actual_stop = actual_fill_decimal - mental_stop_cents / 100
```

**Mechanism:** `mental_stop_cents=15` → formula is `fill_price - $0.15`. If MockBroker fills at $8.55 (limit order offset from $7.80 + 1.015 multiplier), then `$8.55 - $0.15 = $8.40` → stop ABOVE entry.

### Impact

- MNTS lost **-$15,503** because stop could never trigger → held to EOD
- Any case where fill price is significantly higher than quote price will have a broken stop

### Fix

Preserve the originally calculated consolidation stop. Don't overwrite it with `fill - 15¢`:
```python
# Instead of: actual_stop = fill_price - mental_stop_cents / 100
# Do: Keep the original mental_stop from calculate_stop_price()
# Add failsafe: if actual_stop >= actual_fill_price: actual_stop = fill - fallback
```

---

## Clean Entry Trigger Correlation

| Trigger | Count | Total PnL | Avg PnL | Win% | Avg Hold | Avg Stop% |
|---------|------:|----------:|--------:|-----:|---------:|----------:|
| **whole_half_anticipatory** | 23 | +$127,796 | +$5,556 | 70% | 106m | 11.3% |
| **dip_for_level** | 11 | +$74,826 | +$6,802 | 64% | 176m | 15.5% |
| **micro_pullback** | 2 | +$71,995 | +$35,997 | 100% | 37m | 20.8% |
| **hod_break** | 5 | +$45,278 | +$9,056 | 60% | 353m | 12.1% |
| **pmh_break** | 1 | -$1,053 | -$1,053 | 0% | 27m | 10.1% |

**Corrected insights:**
- All triggers are actually profitable on aggregate
- `whole_half_anticipatory` is the workhorse (23 trades, 70% win rate)
- `hod_break` is NOT bad — 60% win rate with $9K avg. The 353m avg hold is from BATL (+$53K) which held to EOD as a winner
- Only `pmh_break` is negative (1 trade sample)

---

## Exit Reason Distribution (Clean)

| Exit Reason | Count | Total PnL | Avg PnL |
|-------------|------:|----------:|--------:|
| mental_stop | 32 | +$274,049 | +$8,564 |
| profit_target | 1 | +$45,238 | +$45,238 |
| after_hours_exit | 4 | +$42,806 | +$10,702 |
| **technical_stop** | **5** | **-$43,251** | **-$8,650** |

`technical_stop` is the ONLY exit reason with negative P&L. All 5 are low-priced stocks ($2-6) with 15-22% stops.

---

## Time-to-Profit Analysis (Clean)

| Metric | Winners | Losers |
|--------|--------:|-------:|
| Count | 27 | 13 |
| Avg Hold | 118 min | 187 min |
| **Median Hold** | **32 min** | **88 min** |
| Avg PnL | +$14,411 | -$5,411 |

Winners resolve 2.75x faster (median). Time bucket analysis:

| Bucket | Wins | Losses | Net PnL |
|--------|-----:|-------:|--------:|
| 0-5m | 4 | 1 | +$50,213 |
| 5-15m | 5 | 1 | +$11,116 |
| **15-60m** | **9** | **4** | **+$164,536** |
| 60-240m | 4 | 4 | +$21,047 |
| 240m+ | 5 | 3 | +$71,834 |

The 15-60m bucket is the sweet spot (+$164K). After 60m, risk/reward deteriorates to 50%.

---

## Top 10 Losses (All Real Trades)

| # | Trigger | Entry | Exit | Stop% | Hold | PnL | Exit Reason |
|---|---------|------:|-----:|------:|-----:|----:|-------------|
| 1 | whole_half_anticipatory | $7.80 | $6.14 | -7.7% | 690m | **-$15,503** | after_hours_exit |
| 2 | hod_break | $5.68 | $4.96 | 9.0% | 406m | -$13,241 | technical_stop |
| 3 | dip_for_level | $2.23 | $1.42 | 22.4% | 47m | -$12,150 | technical_stop |
| 4 | whole_half_anticipatory | $2.44 | $1.74 | 20.5% | 19m | -$10,515 | technical_stop |
| 5 | whole_half_anticipatory | $19.42 | $15.24 | 2.6% | 8m | -$5,137 | mental_stop |
| 6 | whole_half_anticipatory | $4.42 | $4.01 | 11.3% | 15m | -$4,045 | technical_stop |
| 7 | dip_for_level | $3.22 | $3.00 | 15.5% | 88m | -$3,300 | technical_stop |
| 8 | whole_half_anticipatory | $20.58 | $19.20 | 5.4% | 110m | -$3,240 | mental_stop |
| 9 | whole_half_anticipatory | $8.43 | $7.91 | 5.9% | 192m | -$1,428 | mental_stop |
| 10 | pmh_break | $4.95 | $4.63 | 10.1% | 27m | -$1,053 | mental_stop |

**Pattern in losses #1-4 and #6-7:** Low-priced stocks ($2-8) with stops 9-22% from entry, losing 10-36% of entry price. The 50¢ max stop cap creates inverted risk/reward on stocks under $5.

---

## Recommendations (Prioritized by Impact)

### Priority 1: Fix Stop-Overwrite Bug (~$15.5K, CRITICAL)

**Change Point #1:**
- **File:** `warrior_engine_entry.py` lines 1443-1449
- **Current:** `actual_stop = actual_fill_decimal - mental_stop_cents / 100`
- **Fix:** Pass original `mental_stop` through the fill update path, don't recalculate

**Change Point #2:**
- **File:** `warrior_entry_execution.py` line 584
- **Current:** Same formula
- **Fix:** Same — preserve original stop

**Change Point #3 (failsafe):**
- **File:** `warrior_db.py` `update_warrior_fill()`
- **Add:** `if actual_stop_price >= actual_entry_price: log WARNING, clamp to entry - fallback`

### Priority 2: Fix Ghost Trade DB Bug (DATA QUALITY)

**Change Point #1:**
- **File:** `sim_context.py` lines 704-719
- **Current:** Single `get_warrior_trade_by_symbol` → `.first()`
- **Fix:** New function `close_all_open_trades_for_symbol()` that loops ALL active records

**Change Point #2:**
- **File:** `warrior_db.py`
- **Add:** `get_all_warrior_trades_by_symbol()` returning all active records (not `.first()`)
- **Add:** Bulk close function

### Priority 3: Cap Stop % for Low-Priced Stocks (~$43K, HIGH)

5 of 42 trades lost -$43K via `technical_stop` with 15-22% stop distances. For stocks under $5, a 50¢ stop = 10-25%.

**Options:**
- Cap `max_stop_pct` dynamically based on price tier (e.g., 5% cap for stocks under $5)
- Or: block `dip_for_level` entries on stocks under $3 (both ONCO and the BATL dip-loss were $2-3 stocks)

### Priority 4: MFE Trail (requires wiring, MEDIUM)

`_check_mfe_trail` exists at [warrior_monitor_exit.py:402](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py#L402-L460) but `enable_mfe_trail`, `mfe_trail_activation_pct`, `mfe_trail_give_back_pct` are NOT in `WarriorMonitorSettings`. Must be added to `warrior_types.py` and the function wired into `evaluate_position` before param sweep is possible.

### Priority 5: Time-Based Breakeven (SPECULATIVE)

Winners hold 32m median, losers 88m. A "move to breakeven after 60m if red" rule could help, but the 240m+ bucket is still net positive (+$72K), so blanket time rules are risky.

---

## Wiring Checklist for Backend Specialist

- [ ] Fix stop-overwrite in `warrior_engine_entry.py:1443-1449`
- [ ] Fix stop-overwrite in `warrior_entry_execution.py:584`
- [ ] Add failsafe guard in `warrior_db.py:update_warrior_fill()`
- [ ] Add `get_all_warrior_trades_by_symbol()` to `warrior_db.py`
- [ ] Update `sim_context.py:709` EOD close to close ALL records
- [ ] Add MFE trail settings to `WarriorMonitorSettings` in `warrior_types.py`
- [ ] Wire `_check_mfe_trail` into `evaluate_position`
- [ ] Run batch test to verify no P&L regression

---

## Data Files

- **Analysis JSON:** `nexus2/reports/2026-03-02/analysis_bag_holding_deep.json`
- **Analysis script:** `scripts/gc_bag_holding_analysis.py`
- **Clean analysis script:** `/tmp/gc_clean_analysis.py`
