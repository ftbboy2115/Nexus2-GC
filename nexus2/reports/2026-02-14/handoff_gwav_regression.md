# GWAV Regression Investigation

## Problem
GWAV (ross_gwav_20260116) P&L dropped from **+$630.63** to **+$215.91** (-$414.72) after HOD_BREAK implementation.

## Verified Facts

**Fact 1: Entry trigger is identical**
- Both runs: `whole_half_anticipatory` at $5.47
- Exit mode: `home_run` in both runs
- File: `nexus2/domain/automation/warrior_entry_patterns.py`

**Fact 2: Share count changed**
- Baseline: ~505 shares (local proxy, VPS didn't log trade details in baseline)
- Current VPS: 505 shares at $5.47
- VPS P&L: $215.91 (current) vs $630.63 (baseline)

**Fact 3: Only two files changed between baseline and current**
```
nexus2/domain/automation/warrior_engine_entry.py   (line 999: entry_triggered=True restored)
nexus2/domain/automation/warrior_entry_patterns.py (HOD_BREAK exemption + trace cleanup)
```
Verified via: `git diff 3abf885..5def3a5 --stat`

**Fact 4: GWAV does NOT use HOD_BREAK**
- Entry trigger is `whole_half_anticipatory`, not `hod_break`
- HOD_BREAK changes should not directly affect GWAV

## Open Questions for Investigation

1. **Did GWAV's trade count change?** Compare number of trades in baseline vs current run. The baseline comparison file may not have trade-level detail.
2. **Is the P&L difference from exit timing?** Same entry but different exit bar = different P&L. Check if `home_run` exit logic interacts with entry_triggered state.
3. **Could there be a state leak between test cases?** GWAV runs as case #8 in the batch. If a prior case (BNKK, TNMG) changed behavior, could GWAV's timing shift?
4. **Was the baseline $630.63 actually correct?** Check if the Feb 14 baseline was from a clean run or had trace logging that affected timing.

## Starting Points

- `warrior_entry_patterns.py` — `detect_whole_half_anticipatory` function
- `warrior_monitor_exit.py` — `home_run` exit logic
- `warrior_sim_routes.py` — batch runner, check for state leakage between cases
- Server logs: `grep "GWAV" /tmp/server.log` on VPS after running single-case test

## Suggested Approach

1. Run GWAV individually on VPS: `curl -s -X POST http://localhost:8000/warrior/sim/run -H "Content-Type: application/json" -d '{"case_id":"ross_gwav_20260116"}' | python3 -m json.tool`
2. Compare single-case P&L with batch P&L — if different, it's a state leak
3. If same, check git log for any changes between baseline commit and current that could affect `whole_half_anticipatory` or `home_run`

## Output
Write findings to: `nexus2/reports/2026-02-14/investigation_gwav_regression.md`
