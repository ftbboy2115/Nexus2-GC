# Handoff: Audit Validator — Verify Exit Logic Leakage Audit

**Date:** 2026-02-16  
**From:** Coordinator  
**To:** Audit Validator (`@agent-audit-validator.md`)

---

## Your Task

Verify the 8 claims made by the Code Auditor in:  
`nexus2/reports/2026-02-16/audit_exit_logic_leakage.md`

**Read that report first**, then independently verify each claim below.

---

## Claims to Verify

### Claim 1: `session_exit_mode` defaults to `"base_hit"` and is NOT in `warrior_settings.json`
- **Auditor says:** `warrior_types.py:119` — `session_exit_mode: str = "base_hit"`
- **Auditor says:** No `session_exit_mode` in any `.json` file
- **Verify:** `view_file` on `warrior_types.py` around line 119, and search for `session_exit_mode` in `data/warrior_settings.json`

### Claim 2: Home run promotion requires 5x+ RVOL
- **Auditor says:** `warrior_engine_entry.py:1144-1150` — `elif entry_volume_ratio >= 5.0: selected_exit_mode = "home_run"`
- **Verify:** `view_file` on `warrior_engine_entry.py` around lines 1144-1150

### Claim 3: `_check_profit_target` is dead code (never called)
- **Auditor says:** Function defined at `warrior_monitor_exit.py:626` but has zero callers
- **Verify:** Search for `_check_profit_target` across ALL `.py` files in `nexus2/`. Should appear only at the definition, nowhere as a function call.

### Claim 4: Base hit exits 100% of shares (no partial)
- **Auditor says:** `warrior_monitor_exit.py:755-764` — `shares_to_exit=position.shares` (full position)
- **Verify:** `view_file` on lines 749-764 to confirm `shares_to_exit=position.shares`

### Claim 5: Candle trail activation is fixed at +15¢
- **Auditor says:** `warrior_types.py:127` — `base_hit_trail_activation_cents: Decimal = Decimal("15")`
- **Verify:** `view_file` on line 127

### Claim 6: Flat fallback is +18¢
- **Auditor says:** `warrior_types.py:122` — `base_hit_profit_cents: Decimal = Decimal("18")`
- **Auditor says:** Used at `warrior_monitor_exit.py:774-775` as fallback when trail can't activate
- **Verify:** Both locations

### Claim 7: Topping tail runs BEFORE mode-aware exit and exits all shares
- **Auditor says:** Check order in `evaluate_position()` at `warrior_monitor_exit.py:901`
- **Verify:** `view_file_outline` on `warrior_monitor_exit.py` and check the order of exit checks in `evaluate_position`

### Claim 8: Scaling is blocked when price is past profit target
- **Auditor says:** `warrior_engine_entry.py:898-913` blocks scale-ins via `price_past_target`
- **Verify:** `view_file` on lines 898-913 for the `price_past_target` check

---

## Exit Flow Order — Verify Complete Sequence
The auditor claims this execution order in `evaluate_position()`:
```
CHECK 0:   _check_after_hours_exit
CHECK 0.5: _check_spread_exit
CHECK 0.7: _check_time_stop (DISABLED)
CHECK 1:   _check_stop_hit
CHECK 2:   _check_candle_under_candle
CHECK 3:   _check_topping_tail
CHECK 4:   MODE-AWARE (_check_base_hit_target or _check_home_run_exit)
```
**Verify:** Read `evaluate_position` and confirm the exact order of `await` calls.

---

## Deliverable

Write validation report to:  
`nexus2/reports/2026-02-16/validation_exit_logic_audit.md`

Use the mandatory format:
```
**Claim:** [what the auditor said]
**Verification Command:** [exact command or view_file call]
**Actual Output:** [copy-pasted output]
**Result:** PASS / FAIL
**Notes:** [any discrepancies]
```

Include overall quality rating (HIGH / MEDIUM / LOW).
