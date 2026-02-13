# Auditor Handoff: VELO GUI vs Batch P&L Divergence

## Objective

Determine the root cause of the VELO P&L divergence between the GUI simulation path (`load_historical` + `step_clock`) and the sequential batch runner (`run_batch`).

## Empirical Evidence (Verified)

### Result Summary

| Path | P&L | Reproducible |
|------|-----|--------------|
| `run_batch` (sequential) | +$21.36 | Yes, every fresh server |
| `load_historical` + `step_clock` (GUI) | -$389.82 | Yes, every fresh server |

Both produce the same entry: 178 shares VELO @ $14.90, stop=$13.50, trigger=whole_half_anticipatory, exit_mode=home_run

### Evidence 1: Different Price Sequences

Batch evaluate_position prices (chronological after entry):
```
$14.9, $15.44, $15.23, $15.0, $15.19, $14.90, $15.25, $15.63...
Prices go UP, never hits stop, EOD close at $14.98
```

GUI path evaluate_position prices (immediately after entry):
```
$13.765, $13.775, $13.77, $13.75, $13.77, $13.60, $13.55, $13.44
STOP HIT at $13.44 (stop was $13.47)
```

### Evidence 2: Batch TML Has No Exit Event

Batch TML shows only ENTRY + FILL_CONFIRMED. Server log shows `[Warrior DB] Logged exit: VELO @ $14.98 (eod_close)`. Position is force-closed at EOD by batch runner code at warrior_sim_routes.py L1487-1521.

### Evidence 3: GUI Path Has TWO Entry Events

```
15:23:47 | ENTRY | VELO | 178 @ $14.9
15:23:47 | FILL_CONFIRMED | VELO
15:24:16 | ENTRY | VELO | 178 @ $14.9    (SECOND entry, 29s later)
15:24:16 | FILL_CONFIRMED | VELO
15:24:17 | TECHNICAL_STOP_EXIT | VELO | -$389.82
```

### Evidence 4: Monitor Lifecycle Differs

```
15:23:26 | Warrior Monitor Started (interval: 2s)
15:23:44 | Warrior Monitor Stopped           (batch stops it)
15:23:47 | Added VELO (batch load)
15:23:48 | Warrior Monitor Started (2s)      (batch restarts in finally)
15:24:16 | Added VELO again                  (GUI step adds VELO again)
```

Batch stops monitor at L1394-1396. `load_historical_test_case` does NOT stop it.

### Evidence 5: Both Use home_run Exit Mode

Volume explosion (14.5x) overrides session_exit_mode=base_hit to home_run in both paths.

## Files to Audit

- `warrior_sim_routes.py` - `load_historical_test_case` (L690-1050), `step_clock` (L1120-1260), `run_batch_tests` (L1326-1600)
- `warrior_monitor.py` - `_monitor_loop` (L509), `start`/`stop` (L481-500), `_check_all_positions`
- `warrior_monitor_exit.py` - `evaluate_position`
- `warrior_engine_entry.py` - `check_entry_triggers`

## Audit Questions

1. Why does the GUI path see $13.x prices while the batch sees $15.x prices after the same entry?
2. Why are there TWO entry events in the GUI path?
3. Does the monitor background loop interfere with `step_clock`?
4. Does `purge_sim_trades` or EOD force-close materially affect results?

## Disproven Theories

| Theory | Evidence |
|--------|----------|
| on_profit_exit callback missing | GUI EVMN orders show re-entries working |
| Engine config defaults differ | Both enter with same 178 shares, same price |
| Bar loader contamination | Fresh server gives same divergent results |

## Methodology

Per `.agent/knowledge/debugging_methodology.md`, this is a **runtime divergence** problem ("two runners producing different P&L"). Multiple hypotheses have been proposed and disproven. The recommended Combined Workflow is:

1. Audit to identify the exact decision points where behavior diverges
2. Recommend specific trace points for instrumentation (the coordinator will assign a backend specialist to implement them)

## Expected Deliverables

1. Identify WHERE in the code the price sequences diverge — trace `get_price_at` calls, `SimulationClock` state, and `HistoricalBarLoader` lookups
2. Identify WHY there are two ENTRY events in the GUI path
3. If root cause is definitively provable from code alone, state it with exact line-number proof
4. If not provable from code alone, produce a **trace logging plan**: file, function, line number, what to log, format `[TRACE-VELO] {description}: {value}`

Write report to `nexus2/velo_divergence_audit_report.md`.
