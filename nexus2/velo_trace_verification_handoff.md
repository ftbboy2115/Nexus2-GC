# Auditor Handoff: VELO Trace Results Verification

## Context

Backend agent added trace logging and ran both GUI and batch paths for VELO. Read:
- `nexus2/velo_divergence_auditor_handoff.md` — original evidence
- `nexus2/velo_divergence_audit_report.md` — first audit (partially disproven)

## Trace Results Summary

| Metric | GUI Path | Batch Path |
|--------|----------|------------|
| P&L | -$389.82 | +$21.36 |
| Exit | technical_stop @ $13.44 | eod_close @ $14.98 |
| step_clock traces | 960 | 502 |
| evaluate_position traces | 399 | 203 |
| sim_get_price traces | **0** | **0** |
| _get_price_with_fallbacks traces | **0** | **0** |

## Previous Audit Claims — Status

The first auditor claimed live API fallback contamination via `_get_price_with_fallbacks`. Traces show this function was **never called** (0 traces). That theory is disproven.

The backend agent says: "The monitor uses `_get_prices_batch` (L1213-1223 in `step_clock`) which calls `broker.get_price()` directly — completely bypassing `sim_get_price` and `_get_price_with_fallbacks`."

## Audit Questions

1. **Where does the $13.44 price come from?** If `_get_price_with_fallbacks` never fires and `sim_get_price` never fires, how does `evaluate_position` get a price? Trace the code path from `_check_all_positions` → `evaluate_position` to find the actual price resolution mechanism.

2. **Why do evaluate_position counts differ (399 vs 203)?** Is this purely step count (960 vs 502) or does the monitor background loop contribute extra calls? The ratio (~0.4 per step) is similar for both paths.

3. **Is the $13.44 from the historical bar data at the wrong clock time?** VELO premarket on Feb 10 was ~$13.x. If the broker price hasn't been updated past premarket levels when the monitor evaluates, it would see $13.x.

4. **Verify the backend agent's claim** that `step_clock` uses `_get_prices_batch` at L1213-1223. Check what this function does and whether it bypasses `_get_price_with_fallbacks`.

## Files to Audit

- `warrior_monitor_exit.py` — `evaluate_position`, `_get_price_with_fallbacks`, how price is passed to evaluate_position
- `warrior_monitor.py` — `_check_all_positions`, how it calls evaluate_position
- `warrior_sim_routes.py` — `step_clock` L1180-1230, `_get_prices_batch` at L1213
- `mock_broker.py` — `get_price()`, how/when prices are updated

## Deliverable

Write report to `nexus2/velo_trace_verification_report.md`. Focus on the actual price resolution path, not hypotheses.
