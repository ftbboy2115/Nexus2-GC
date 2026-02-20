# Handoff: Backend Specialist — Sim Engine Display Fixes

## Context

The P&L investigation (`spec_sim_pnl_investigation.md`) found that the sim engine's **P&L calculations are correct**, but the **trade detail display** is misleading when partial exits occur. Three fixes are needed.

## Verified Facts

**Finding:** Per-trade result is assembled in `_run_single_case_async`
**File:** `nexus2/adapters/simulation/sim_context.py:601-615`
**Code:**
```python
trades.append({
    "entry_price": round(float(wt.get("entry_price", 0)), 2),
    "exit_price": round(float(wt.get("exit_price", 0)), 2),
    "shares": wt.get("quantity", 0),
    "pnl": round(float(wt.get("realized_pnl", 0)), 2),
})
```
**Verified with:** Backend Planner spec, `spec_sim_pnl_investigation.md` Section A
**Conclusion:** This is the single point to enrich trade detail output.

---

**Finding:** `exit_price` only set on full exit, not partial
**File:** `nexus2/db/warrior_db.py:386`
**Code:** `trade.exit_price = str(exit_price)` — only in full exit branch
**Verified with:** Backend Planner spec, Section B.2
**Conclusion:** Partial exit prices are lost.

---

**Finding:** Timestamps use `now_utc()` unconditionally
**File:** `nexus2/db/warrior_db.py:295` (entry) and `:387` (exit)
**Code:** `entry_time=now_utc()` and `trade.exit_time = now_utc()`
**Verified with:** Backend Planner spec, Section B.4
**Conclusion:** Sim runs show wall-clock time instead of simulated market time.

## Implementation Tasks

### Fix #1: Enrich Trade Detail with Partial Exit Info (Priority: Medium)

**File:** `nexus2/adapters/simulation/sim_context.py` ~L601-615

Add these fields to the per-trade dict:
- `partial_taken: bool` — whether a partial exit occurred
- `partial_exit_count: int` — number of partial exits
- `remaining_quantity: int` — quantity at final exit (if partial, this < shares)
- `avg_exit_price: float` — volume-weighted average exit price across all exits

> [!IMPORTANT]
> The source data for partial exits is in `warrior_db`. Investigate what fields are available on the trade record. You may need to also:
> - Track partial exit prices/quantities in `warrior_db.py` during `log_warrior_exit` (partial branch ~L401)
> - Add fields like `partial_exit_prices` (JSON string) to the warrior trade record

### Fix #2: Use Sim Clock for Timestamps in Sim Mode (Priority: Low)

**Files:** `nexus2/db/warrior_db.py:295` and `:387`

When running in sim context, pass the simulated bar time instead of `now_utc()`.

> [!IMPORTANT]
> Investigate how sim time is available. Look for `ctx.clock` or `sim_time` in `SimContext`. The fix should be backward-compatible — live trading must continue using `now_utc()`.

### Fix #3: Document Dual P&L System (Priority: Low)

Add a code comment at the top of `_run_single_case_async` explaining the two P&L sources (MockBroker vs warrior_db) and when they can diverge. This is documentation only, no code logic change.

## Verification

After implementing:
1. Run MLEC batch test: `Invoke-RestMethod -Method POST -Uri "http://localhost:8000/warrior/sim/run_batch_concurrent" -ContentType "application/json" -Body '{"case_ids": ["ross_mlec_20260220"], "include_trades": true}' | ConvertTo-Json -Depth 10`
2. Confirm trade output includes new fields (`partial_taken`, `avg_exit_price`, etc.)
3. Confirm timestamps reflect simulated market time (should be ~09:30-09:45 range for MLEC)
4. Run full test suite: `python -m pytest nexus2/tests/ -x -q`

## Output
Write status to: `nexus2/reports/2026-02-20/backend_status_sim_display_fixes.md`
