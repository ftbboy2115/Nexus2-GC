# Backend Planner Handoff: LATE_ENTRY P1 Investigation

## Context

Batch diagnosis (35 test cases) shows bot captures only **27.9% of Ross's P&L** ($120K vs $433K).
The **#1 issue is LATE_ENTRY**: 11 cases, ~$312K P&L gap. Bot enters 1-2 hours after Ross.

**WB is NOT supposed to be limited to market hours.** Ross trades premarket (7-9 AM) and WB should too.

## Verified Facts

**sim_context.py:207** — Sim engine defaults to 9:30 AM start:
```
Verified via: Select-String -Path "nexus2\adapters\simulation\sim_context.py" -Pattern "start_time"
Line 205: start_time = ET.localize(trade_date.replace(hour=hour, minute=minute, second=0))
Line 207: start_time = ET.localize(trade_date.replace(hour=9, minute=30, second=0))
```
Line 205 uses custom hour/minute if provided; line 207 is the DEFAULT fallback of 9:30 AM.

**warrior_scanner_service.py:602-613** — Scanner HAS premarket support:
```
Verified via: Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern "premarket"
Line 605: is_premarket = current_et.hour < 9 or (current_et.hour == 9 and current_et.minute < 30)
Line 612: gainers = self.market_data.get_premarket_gainers(...)
```
Scanner checks if premarket and uses different gainer source.

**warrior_engine_entry.py** — ORB trigger is 9:30-specific but other triggers may work premarket:
```
Verified via: Select-String -Path "nexus2\domain\automation\warrior_engine_entry.py" -Pattern "9:30|premarket"
Line 576: # ORB trigger at 9:30
Line 150: Check if there's active trading happening (not dead premarket)
Line 1102: naturally have wide 5-bar consolidation lows during sparse premarket periods
```

## Open Questions (Investigate These)

1. **What determines the sim start time for each test case?**
   - Does `warrior_setups.yaml` have a `start_hour`/`start_minute` field per case?
   - How many of the 11 LATE_ENTRY cases have bars BEFORE 9:30 in their bar data?
   - File: `nexus2/tests/test_cases/warrior_setups.yaml`
   - File: `nexus2/adapters/simulation/sim_context.py` — trace the `hour`/`minute` params

2. **Are there time gates in the entry engine that block premarket entries?**
   - Line 150 of `warrior_engine_entry.py` says "Check if there's active trading happening (not dead premarket)" — what does this actually do? Does it REJECT entries?
   - Line 1102 mentions "sparse premarket periods" affecting consolidation lows — does the stop method break in premarket?
   - File: `nexus2/domain/automation/warrior_engine_entry.py`

3. **Which entry triggers work in premarket vs only after 9:30?**
   - ORB is clearly 9:30-only. What about: `micro_pullback`, `dip_buy`, `breakout`, `momentum`?
   - Does `check_entry_triggers()` have any time-based filtering?
   - File: `nexus2/domain/automation/warrior_engine_entry.py`

4. **For the 11 LATE_ENTRY cases, what does the bar data look like?**
   - Cases: LCFY, FLYE, RDIB, MNTS, BNRG (plus ~6 more from batch diagnosis)
   - Do the Polygon bars start at 4:00 AM (premarket) or 9:30 AM?
   - If bars exist before 9:30, the sim is ignoring them. If bars don't exist, it's a data gap.

## Expected Output

Write a technical spec to `nexus2/reports/2026-02-23/spec_late_entry_root_cause.md` with:
- Root cause determination (sim start time? entry gate? bar data gap?)
- Surface area of code changes needed
- Recommended fix approach
- Impact assessment (which of the 11 cases would be fixed)
