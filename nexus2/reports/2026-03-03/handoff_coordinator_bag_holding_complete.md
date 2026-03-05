# Coordinator Handoff: Bag Holding Investigation Complete

**Date:** 2026-03-03 07:26 ET  
**VPS:** Deployed at commit `7fd0d14`, healthy, PAPER mode

---

## What Shipped Today

1. **Stop-overwrite bug fix** (commit `ee1a538`) — LIVE safety. `update_warrior_fill()` was recalculating stop as `fill_price - 15¢`, which could invert the stop above entry when broker fills above quote. Now preserves original consolidation stop. Files: `warrior_engine_entry.py`, `warrior_entry_execution.py`, `warrior_db.py` (failsafe guard).

2. **Ghost trade DB fix** (commit `ee1a538`) — Data quality. EOD close now closes ALL open DB records for a symbol via `get_all_warrior_trades_by_symbol()`, not just `.first()`. Files: `sim_context.py`, `warrior_db.py`.

3. **Tech stop cap setting** (commit `7fd0d14`) — Wired but DISABLED (`tech_stop_max_pct = 0.0`). All sweep values net negative. Files: `warrior_monitor.py`, `warrior_types.py`.

4. **Re-entry cooldown** (earlier commit) — `live_reentry_cooldown_minutes = 10` in `warrior_types.py`.

## What Was Tested and Failed (All Net Negative)

| Approach | Net Δ | Verdict |
|----------|-------|---------|
| Entry candle low | -$85K | Too tight |
| 50¢ fixed cap | -$21K | Still too tight |
| 5% entry cap | -$55K | Worse for cheap stocks |
| MFE trail (3%/50%) | -$215K | Kills winners |
| Tech stop cap 10-25% | -$78K to -$122K | All net negative |

**Conclusion:** Blanket stop-tightening is a dead end. Wide stops ARE the edge — they let winners survive pullbacks.

## Dead Code Left In Place

- `_check_mfe_trail()` function in `warrior_monitor_exit.py` ~line 401 — not wired, available for future param sweep
- `tech_stop_max_pct` setting in `warrior_types.py` — set to 0.0 (disabled)

## Baseline

39 cases, **$355,039**, 79.5% capture. Saved in `nexus2/reports/gc_diagnostics/baseline.json`.

## Next Task: Review Live Trades This Morning

Clay wants to look at trades taken this morning that have lost. Check the VPS dashboard or API:
```
ssh root@100.113.178.7 "curl -s http://localhost:8000/warrior/positions"
ssh root@100.113.178.7 "tail -200 ~/Nexus2/data/server.log | grep -i 'entry\|exit\|stop\|warrior'"
```

## Key Reports

- `nexus2/reports/2026-03-02/research_bag_holding_deep_analysis.md` — Planner's per-case analysis
- `nexus2/reports/2026-03-02/research_mnts_stop_failure.md` — MNTS root cause
- `nexus2/reports/2026-03-03/backend_status_tech_stop_cap_sweep.md` — Sweep results
