# Exit Logic Tuning — Research & Spec

## Context
After HOD_BREAK implementation, VPS baseline is **$7,408** across 29 test cases (17 profitable).
Entries are working well. The next P&L lever is **exit/trade management** tuning.

## Evidence: Exits Are the Bottleneck

| Case | Entry OK? | P&L | Problem |
|------|-----------|-----|---------|
| MLEC | ✅ hod_break fires | -$412 | Good entry at $10.12/$8.71, exits too early or at loss |
| LCFY | ✅ hod_break fires | -$483 | 3 hod_break entries, all lose on exits |
| BATL 126 | ✅ micro_pullback | -$176 | Entries fine, exits don't capture upside |

Ross made **$43K on MLEC** and **$10.5K on LCFY**. Our entries match his timing but exits capture nothing.

## Prior Audit Reference
A trade management audit was completed on Feb 13:
`nexus2/reports/2026-02-13/audit_trade_management.md` (if it exists, check `nexus2/trade_management_audit.md` as well)

Key findings from that audit should be reviewed before proposing changes.

## Open Questions for Research

1. **What exit modes are being used?** Catalog all `exit_mode` values across the 29 VPS batch cases. Which exit modes correlate with profitable vs unprofitable trades?
2. **Base hit vs home_run**: What are the current thresholds? Are `base_hit` exits cutting winners short?
3. **Trailing stop behavior**: How does the candle-low trailing stop work? Is it getting triggered by normal pullbacks within winning trades?
4. **Stop placement on HOD_BREAK entries**: Where is the stop placed for hod_break entries? Is it too tight?
5. **Time stop**: Was disabled (commit `dcd999f`). Should it be re-evaluated for specific patterns?

## Starting Points

- `warrior_monitor_exit.py` — all exit logic
- `warrior_monitor_scale.py` — scale/add logic
- `warrior_engine_types.py` — `ExitMode` enum, config thresholds
- `nexus2/reports/2026-02-13/audit_trade_management.md` — prior audit
- Batch results: focus on MLEC, LCFY, BATL 126 trade details

## Scope
**Research and spec only** — do NOT implement changes. Produce a spec with:
1. Current exit parameters and their P&L impact
2. Specific parameters to tune (with before/after values)
3. Expected P&L impact per change
4. Recommended implementation order

## Output
Write findings to: `nexus2/reports/2026-02-14/spec_exit_logic_tuning.md`
