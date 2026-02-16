# Handoff: Code Auditor — Exit Logic P&L Leakage Audit

**Date:** 2026-02-16  
**From:** Coordinator  
**To:** Code Auditor (`@agent-code-auditor.md`)

---

## Context

Warrior bot captures only **13% of Ross Cameron's P&L** in batch testing.  
The **exit logic** is suspected as the primary source of P&L leakage — the bot exits too early on winners.

**Key evidence:** NPT made +$14K vs Ross's +$81K. ROLR made +$10.6K vs Ross's +$85K.

**Full batch results:** `nexus2/reports/2026-02-16/batch_ross_sizing_test.md`

---

## Verified Facts (with evidence)

1. **Exit logic is in `warrior_monitor_exit.py` (~1189 lines)**  
   - File: `nexus2/domain/automation/warrior_monitor_exit.py`

2. **Exit mode selection at line 52-54:**  
   - Code: `if position.exit_mode_override: return position.exit_mode_override; return monitor.settings.session_exit_mode`  
   - Default is `"base_hit"` (warrior_types.py:119)

3. **Base hit profit target checked at `_check_profit_target` (line 626)**  
   - Exits when `current_price >= position.profit_target`

4. **Base hit candle trail at `_check_base_hit_target` (line 686)**  
   - Activates at +15¢, trails using 2-bar low
   - Fallback: flat +18¢ exit if no bars available

5. **Home run mode parameters (warrior_types.py:131-134):**  
   - 50% partial at 2R, trail after 1.5R, 20% trail below high

---

## Open Questions (INVESTIGATE FROM SCRATCH)

> [!IMPORTANT]
> These are investigation questions. Do NOT rubberstamp coordinator assumptions.

1. **In `base_hit` mode, what exactly causes early exits?**
   - Is the candle trail too tight (2-bar low)?
   - Is the +15¢ activation too low for higher-priced stocks?
   - Does the +18¢ flat fallback fire often? On which cases?

2. **What triggers a `home_run` exit vs `base_hit` exit?**
   - Is `exit_mode_override` ever set on positions? Where in the code?
   - Are positions always defaulting to `base_hit` regardless of quality?

3. **What is the actual exit flow ordering?**
   - List every exit check function in execution order
   - Which ones fire first vs last?
   - Are there early returns preventing later checks from running?

4. **For the NPT case specifically:**
   - At $2K risk, the bot made $14K (entered at ~$X, exited at ~$Y)
   - What exit mode/trigger caused the exit?
   - Was the candle trail responsible, or the profit target?

5. **Is there scaling/add-on logic?**
   - Search for functions that add shares to existing positions
   - Does the bot ever scale in? If not, where would it plug in?

6. **What's the relationship between `_check_profit_target` and `_check_base_hit_target`?**
   - Do they compete? Which runs first?
   - Could the profit target be exiting before the trail gets a chance to ride?

---

## Files in Scope

| File | Purpose |
|------|---------|
| `warrior_monitor_exit.py` | All exit logic |
| `warrior_types.py` | Exit mode configs, position fields |
| `warrior_monitor.py` | Monitor orchestration |
| `warrior_engine.py` | Position lifecycle, profit exit handling |

---

## Deliverable

Write an audit report to:  
`nexus2/reports/2026-02-16/audit_exit_logic_leakage.md`

Use the **mandatory evidence format** for every finding:
```
**Finding:** [description]
**File:** [absolute path]:[line number]
**Code:** [exact snippet]
**Verified with:** [command]
**Conclusion:** [reasoning]
```
