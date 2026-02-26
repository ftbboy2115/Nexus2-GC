# Session Handoff — Feb 25-26, 2026

## What We Accomplished
Three parameter changes improved Warrior bot P&L from **$155K → $359K (+131%)**:
1. `max_stop_pct` = 0.10 in `warrior_engine_types.py` (was 1.0)
2. `partial_exit_fraction` = 0.25 in `warrior_types.py` (was 0.50)
3. `max_scale_count` = 4 in `warrior_types.py` (was 2)

All committed at `249337a`, deployed to VPS.

## What We're Working On Next
**10s vs 1min forensic comparison**. With the above settings:
- 1min bars: $359K (82.8% capture)
- 10s bars: $149K (34.4% capture)

The $210K gap needs investigation. Script ready: `scripts/gc_10s_forensic.py`

Run: `python scripts/gc_10s_forensic.py` (server must be running, ~4 min)

Clay's direction: research root causes first, design hybrid approach, validate against full batch to avoid overfitting.

## Key Files
- Sweep results: `nexus2/reports/gc_diagnostics/sweep_*.json`
- Diagnostic: `scripts/gc_trade_management_diagnostic.py`
- Param sweep: `scripts/gc_param_sweep.py`
- 10s forensic (NEW): `scripts/gc_10s_forensic.py`
- Settings: `data/warrior_monitor_settings.json`
