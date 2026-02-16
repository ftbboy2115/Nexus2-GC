# Handoff: Backend Planner — Fix 1: Partial-Then-Ride Technical Spec

**Date:** 2026-02-16  
**From:** Coordinator  
**To:** Backend Planner (`@agent-backend-planner.md`)

---

## Context

Warrior bot exits winners at +15¢/+18¢ (100% of shares). We need to implement **partial exits** — sell 50% at the base_hit trail, then switch the remaining 50% to home_run trailing mode.

This is **Fix 1** of 5 iterative A/B tests. It must be toggleable via a config flag.

### Completed Reports (READ FIRST)
1. `nexus2/reports/2026-02-16/audit_exit_logic_leakage.md` — Code Auditor's 8 root causes
2. `nexus2/reports/2026-02-16/validation_exit_logic_audit.md` — Validator confirmed all 8 claims PASS
3. `nexus2/reports/2026-02-16/research_homerun_scaling_methodology.md` — Strategy Expert's Ross methodology

### Strategy Context
- Read `.agent/strategies/warrior.md` for Ross Cameron methodology
- Key insight: Ross always takes partials at structural levels, never full exits on winners

---

## Verified Facts (with evidence)

1. **`_check_base_hit_target` defined at `warrior_monitor_exit.py:686-800`**
   - Two exit points: candle trail hit (L749-764), flat +18¢ fallback (L786-800)
   - Both use `shares_to_exit=position.shares` (100% exit)

2. **`partial_taken: bool = False` exists on `WarriorPosition` (`warrior_types.py:162`)**

3. **`partial_exit_fraction: float = 0.5` exists on `WarriorMonitorSettings` (`warrior_types.py:70`)**

4. **`exit_mode_override: Optional[str] = None` exists on `WarriorPosition` (`warrior_types.py:180`)**

5. **`_check_home_run_exit` at L803-893 already works** — trails 20% below high, partial at 2R

6. **`evaluate_position` dispatches at L989-1007** based on `get_effective_exit_mode()`

---

## Open Questions (INVESTIGATE FROM SCRATCH)

> [!IMPORTANT]
> The coordinator has reviewed the code but may have missed edge cases.
> Your job is to map the FULL change surface independently.

1. **What happens when `position.shares` is decremented after partial?**
   - Does `handle_exit()` at L1017+ use `signal.shares_to_exit` or `position.shares`?
   - Will the remaining shares be tracked correctly for the next eval cycle?

2. **Does `position.shares -= shares_to_exit` (as done in home_run mode L866) work across monitor evaluation cycles?**
   - How does `_check_all_positions` iterate? Will modified shares persist?
   - Is position state preserved between eval cycles?

3. **When switching to home_run mode, should `candle_trail_stop` be reset to `None`?**
   - Home run uses `position.current_stop` and `position.high_since_entry`
   - Will leftover `candle_trail_stop` from base_hit interfere?

4. **Does `warrior_settings.json` persistence need updating to include the new config toggle?**
   - Check `save_warrior_settings` / `load_warrior_settings` / `get_config_dict`
   - Does the settings system auto-pick up new dataclass fields?

5. **Are there tests in `test_warrior_monitor.py` that need updating?**
   - Search for tests covering `_check_base_hit_target`
   - What test patterns exist for partial exits?

6. **What happens with the `trade_event_service` logging?**
   - Home_run mode calls `trade_event_service.log_warrior_breakeven` on partial
   - Should base_hit partial also log events?

---

## Expected Deliverable

Write a technical spec to:  
`nexus2/reports/2026-02-16/spec_partial_then_ride.md`

Include:
- A. Existing pattern analysis (use `_check_home_run_exit` partial at L852-891 as template)
- B. Complete change surface enumeration (ALL files needing changes)
- C. Detailed change specs with current code at each change point
- D. Wiring checklist for the Backend Specialist
- E. Risk assessment (what could break, what to test)
