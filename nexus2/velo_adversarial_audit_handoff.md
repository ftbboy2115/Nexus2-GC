# Adversarial Audit: VELO Trace Claims

## Your Role

You are challenging the backend agent's conclusions about the VELO P&L divergence. Your job is to DISPROVE their claims, not confirm them. If you cannot disprove a claim, explain exactly why it holds up under scrutiny.

## Backend Agent's Claims to Challenge

### Claim B1: "sim_get_price never fires (0 traces)"

The backend agent placed a trace in the `sim_get_price` callback inside `load_historical_test_case` and got 0 hits.

**Challenge**: Did they place the trace in the right function? There may be MULTIPLE price callbacks wired into the monitor. Check:
- Where exactly was the trace placed? (warrior_sim_routes.py ~L865)
- Is `sim_get_price` actually the callback wired to `monitor._get_price`?
- Or does `step_clock` use a DIFFERENT price resolution path?
- Could the trace be in a code path that's never reached because of how `set_callbacks` wires things?

### Claim B2: "_get_price_with_fallbacks never fires (0 traces)"

The backend agent says the fallback chain at warrior_monitor_exit.py L62-136 was never called.

**Challenge**: The trace was placed inside `_get_price_with_fallbacks`. But `evaluate_position` fired 399 times. How does `evaluate_position` get a price WITHOUT calling `_get_price_with_fallbacks`? Either:
- (a) There's a DIFFERENT code path into evaluate_position that pre-fetches the price
- (b) The trace was placed wrong
- (c) evaluate_position doesn't use `_get_price_with_fallbacks` at all

**Verify**: Read `evaluate_position` and trace how it gets `current_price`. Does it call `_get_price_with_fallbacks`, or does it receive the price as a parameter?

### Claim B3: "step_clock uses _get_prices_batch which calls broker.get_price() directly"

The backend agent claims `step_clock` at L1213-1223 uses `_get_prices_batch` to bypass the sim callbacks entirely.

**Challenge**: 
- Does `_get_prices_batch` exist at that line? What does it actually do?
- Is `_get_prices_batch` a monitor callback that was wired to a sim function, or is it a hardcoded call?
- If it calls `broker.get_price()`, when is the broker's price updated to $13.44? The broker should have the entry price ($14.90) or the latest bar price.

### Claim B4: "The divergence is just timing — monitor fires more in GUI"

The backend agent says GUI gets 399 evaluate_position calls vs batch 203, and at one particular tick the price happens to be $13.44 (below stop), triggering a stop-out.

**Challenge**:
- If both paths use `broker.get_price()`, they should see the SAME price at the SAME sim clock time. The broker price is set by `step_clock` advancing through bars. How can the same sim clock time produce different prices?
- The GUI steps 960 times (04:00→20:00), batch steps 502 (04:00→12:22). Does VELO's historical data show $13.44 at some point between 12:22 and 20:00 that the batch never reaches?
- OR: does the monitor background loop call `_check_all_positions` BETWEEN step_clock iterations, at a moment when the broker price is stale/wrong?

### Critical Question: Where is $13.44 in the historical data?

The VELO test case has 472 bars. Find the bar(s) where price = $13.44 or close to it. Is this:
- (a) A premarket bar (before 09:30)?
- (b) An afternoon bar (after 12:22, which batch never reaches)?
- (c) NOT in the historical data at all (meaning the price comes from somewhere else)?

This is the most important question. Answer it definitively.

## Files to Examine

- `warrior_monitor_exit.py` — `evaluate_position` (how does it get price?), `_get_price_with_fallbacks`
- `warrior_sim_routes.py` — `step_clock` L1180-1230 (what is `_get_prices_batch`?), `sim_get_price` callback
- `warrior_monitor.py` — `_check_all_positions` (how does it call evaluate_position?)
- `mock_broker.py` — `get_price()`, `set_price()`, when/how prices update
- `warrior_setups.yaml` — VELO test case bars, find where $13.44 appears

## Deliverable

Write report to `nexus2/velo_adversarial_audit_report.md`. For each claim (B1-B4), state CONFIRMED or DISPROVEN with exact line-number evidence.
