# Guard Effectiveness Analysis — Backend Handoff

**Date:** 2026-02-23  
**From:** Coordinator  
**To:** Backend Specialist  
**Spec:** [spec_guard_effectiveness_analysis.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-02-23/spec_guard_effectiveness_analysis.md)

---

## Objective

Implement two features to measure whether entry guards are helping or hurting Warrior bot profitability:

1. **Phase 1 — A/B Batch Runs:** Add `skip_guards` param so batch can run with guards disabled
2. **Phase 2 — Counterfactual Analysis:** Enrich guard blocks with price/time, then retroactively check whether each block was correct

---

## Verified Facts

Guard blocks are stored in `TradeEventModel` with `event_type == "GUARD_BLOCK"`:
- **File:** `nexus2/adapters/simulation/sim_context.py:697-714`
- **Fields:** `new_value` = guard type, `reason` = block reason, `symbol` = stock

Guard checks live in `check_entry_guards()`:
- **File:** `nexus2/domain/automation/warrior_entry_guards.py:35-168`
- Guards: top_x picks, min score, blacklist, fail limit, MACD gate, position guards, cooldown, spread filter
- Technical validation (VWAP/EMA) is in `validate_technicals()` (line 344-464)

Batch endpoint:
- **File:** `nexus2/api/routes/warrior_sim_routes.py:1611-1660`
- Model: `BatchTestRequest` with `case_ids` and `include_trades` params
- Calls `run_batch_concurrent(cases, yaml_data)` from `sim_context.py`

---

## Phase 1: A/B Batch Runs

### Task List

1. **Add `skip_guards: bool = False` to `BatchTestRequest`** in `warrior_sim_routes.py`

2. **Thread `skip_guards` through the sim pipeline:**
   - `run_batch_concurrent_endpoint` → pass `request.skip_guards` to `run_batch_concurrent()`
   - `run_batch_concurrent()` → pass to each `_run_case_sync()` call
   - `_run_case_sync()` → set `engine.skip_guards = True` on the `WarriorEngine` instance

3. **Respect `skip_guards` in `check_entry_guards()`** in `warrior_entry_guards.py`:
   ```python
   if getattr(engine, 'skip_guards', False):
       assert getattr(engine, '_sim_mode', False), "skip_guards only allowed in simulation"
       logger.info(f"[Guard A/B] {watched.symbol}: Guards SKIPPED (A/B test mode)")
       return True, ""
   ```

4. **Also skip `validate_technicals()` when `skip_guards=True`** — otherwise VWAP/EMA gates still block. In `enter_position()` at `warrior_engine_entry.py:~1017`:
   ```python
   # After check_entry_guards passes, also skip technicals if skip_guards
   if not getattr(engine, 'skip_guards', False):
       tech_ok, tech_reason = await validate_technicals(engine, watched, entry_price)
       if not tech_ok:
           # ... existing rejection logic
   ```

5. **Safety assertion:** `skip_guards` MUST only work in sim mode. Add an early check in the endpoint:
   ```python
   if request.skip_guards:
       # Only allowed in sim context (this endpoint IS sim-only, but be explicit)
       pass  # The endpoint is already under /warrior/sim/, just document it
   ```

### Verification
- Run `POST /warrior/sim/run_batch_concurrent` with `{"skip_guards": false}` → record P&L
- Run `POST /warrior/sim/run_batch_concurrent` with `{"skip_guards": true}` → record P&L
- Compare results — if guards-off P&L > guards-on P&L, guards are too aggressive

---

## Phase 2: Counterfactual Guard Analysis

### Task List

1. **Enrich guard block logging with price and time context**

   In `warrior_entry_guards.py`, where `log_warrior_guard_block()` is called, ensure the block event includes:
   - `blocked_price`: the entry price that was about to be used
   - `blocked_time`: the sim clock time (or real time)
   
   The `log_warrior_guard_block()` function in `trade_event_service.py` should accept these additional params and store them. Use the existing `reason` field or add to metadata.

   **Open Question:** Investigate how `log_warrior_guard_block()` currently stores data — does it have a metadata/JSON field, or only `new_value` + `reason` strings? Adapt accordingly.

2. **Create `analyze_guard_outcomes()` function in `sim_context.py`**

   After a sim case completes (after all bars processed), call this function:
   ```python
   def analyze_guard_outcomes(guard_blocks, bars, symbol):
       """Check what price did after each guard block."""
       outcomes = []
       for block in guard_blocks:
           # Find bars after the block time
           # Check price at +5, +15, +30 min
           # Calculate MFE (max favorable excursion) and MAE (max adverse excursion)
           # Tag as CORRECT_BLOCK or MISSED_OPPORTUNITY based on 15-min price
           ...
       return outcomes
   ```
   
   **Key logic:** A block is "correct" if price at +15 min is LOWER than the blocked entry price. "Missed opportunity" if price is HIGHER.

3. **Add `guard_analysis` to case results**

   In the case result dict (sim_context.py ~line 716-729), add:
   ```python
   "guard_analysis": {
       "total_blocks": len(guard_blocks),
       "correct_blocks": sum(1 for o in outcomes if o["outcome"] == "CORRECT_BLOCK"),
       "missed_opportunities": sum(1 for o in outcomes if o["outcome"] == "MISSED_OPPORTUNITY"),
       "guard_accuracy": correct / total if total > 0 else 0,
       "net_guard_impact": sum(o["hypothetical_pnl_15m"] for o in outcomes),
       "by_guard_type": { ... per-type breakdown ... },
       "details": outcomes,  # Full list for debugging
   }
   ```

4. **Update diagnosis script** (`scripts/gc_batch_diagnose.py`)

   Add a "Guard Effectiveness" section to the report that summarizes:
   - Overall guard accuracy across all cases
   - Per-guard-type accuracy and net P&L impact
   - Top 5 worst missed opportunities (biggest hypothetical P&L lost)

### Verification
- Run batch with Phase 2 enabled
- Verify `guard_analysis` appears in each case result
- Check that per-guard accuracy rates are reasonable (not all 0% or 100%)
- Validate that "MISSED_OPPORTUNITY" blocks make intuitive sense by spot-checking a few

---

## Output

Write status report to: `nexus2/reports/2026-02-23/backend_status_guard_effectiveness.md`

Include:
- Files modified with line numbers
- A/B test results (Phase 1)
- Sample guard analysis output (Phase 2)
- Any design decisions made
