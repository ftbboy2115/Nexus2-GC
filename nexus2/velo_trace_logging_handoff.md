# Backend Handoff: VELO Trace Logging

## Context

Read `nexus2/velo_divergence_auditor_handoff.md` and `nexus2/velo_divergence_audit_report.md` for full context.

**Problem**: GUI path (`load_historical` + `step_clock`) produces P&L=-$389.82 for VELO. Batch (`run_batch`) produces +$21.36. The GUI sees $13.x prices after entry while batch sees $15.x. Both use the same historical bars from Feb 10.

**What we know**: The $13.x prices match Feb 10 premarket levels (before the $14.90 entry), NOT today's live market (~$11). So the source is likely historical data from the wrong clock position, not live APIs.

**What we need**: Empirical trace data to identify exactly WHERE the $13.x prices come from.

## Trace Points to Add

All traces use `logger.warning` with prefix `[TRACE-VELO]` for easy filtering. These are TEMPORARY and will be removed after diagnosis.

### Trace 1: `_get_price_with_fallbacks` (warrior_monitor_exit.py L62-136)

After L79 (`price = await monitor._get_price(position.symbol)`), add:
```python
logger.warning(
    f"[TRACE-VELO] _get_price_with_fallbacks: symbol={position.symbol}, "
    f"primary_price={price}, sim_mode={monitor.sim_mode}, "
    f"sim_clock={getattr(monitor, '_sim_clock', None) and monitor._sim_clock.get_time_string()}"
)
```

Also add traces at each fallback trigger (L82, L98, L111) to confirm whether they fire:
```python
logger.warning(f"[TRACE-VELO] Schwab fallback TRIGGERED for {position.symbol}")
logger.warning(f"[TRACE-VELO] FMP fallback TRIGGERED for {position.symbol}")
logger.warning(f"[TRACE-VELO] Alpaca position fallback TRIGGERED for {position.symbol}")
```

### Trace 2: `_monitor_loop` (warrior_monitor.py L509-533)

Inside the loop, before `_check_all_positions`, add:
```python
logger.warning(
    f"[TRACE-VELO] _monitor_loop firing: sim_mode={self.sim_mode}, "
    f"sim_clock={getattr(self, '_sim_clock', None) and self._sim_clock.get_time_string()}, "
    f"positions={list(self._positions.keys())}"
)
```

### Trace 3: `step_clock` (warrior_sim_routes.py ~L1182)

Before `check_entry_triggers` and `_check_all_positions` calls, add:
```python
logger.warning(
    f"[TRACE-VELO] step_clock tick: sim_time={clock.get_time_string()}, "
    f"minute={i}, broker_price={broker.get_price('VELO') if broker else 'N/A'}"
)
```

### Trace 4: `evaluate_position` (warrior_monitor_exit.py)

At the top of `evaluate_position`, add:
```python
logger.warning(
    f"[TRACE-VELO] evaluate_position: symbol={position.symbol}, "
    f"entry_price={position.avg_price}, current_stop={position.current_stop}"
)
```

### Trace 5: `sim_get_price` callback (warrior_sim_routes.py, inside load_historical_test_case)

In the `sim_get_price` function defined inside `load_historical_test_case` (~L870), add:
```python
logger.warning(
    f"[TRACE-VELO] sim_get_price: symbol={symbol}, "
    f"clock_time={clock.get_time_string()}, "
    f"price={loader.get_price_at(symbol, clock.get_time_string())}"
)
```

## Rules

- Use `logger.warning` (not debug/info) so traces appear in server.log
- Prefix ALL traces with `[TRACE-VELO]`
- Do NOT change any logic — only ADD trace logging
- Do NOT modify entry, exit, or stop logic
- After adding traces, deploy to VPS using `/deploy-to-vps` workflow

## Verification

After deployment, run on fresh server:
```powershell
# Clear logs
ssh root@100.113.178.7 "> /root/Nexus2/data/server.log"

# Run GUI path
Invoke-RestMethod -Uri "http://100.113.178.7:8000/warrior/sim/load_historical?case_id=ross_velo_20260210" -Method Post -ContentType "application/json" -TimeoutSec 120
Invoke-RestMethod -Uri "http://100.113.178.7:8000/warrior/sim/step?minutes=960&headless=true" -Method Post -ContentType "application/json" -TimeoutSec 300

# Extract traces
ssh root@100.113.178.7 "grep 'TRACE-VELO' /root/Nexus2/data/server.log | head -100"
```
