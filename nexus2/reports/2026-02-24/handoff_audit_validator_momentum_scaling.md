# Handoff: Validate Momentum Scaling Implementation

**Date:** 2026-02-24
**From:** Coordinator
**To:** Audit Validator
**Reference:** `nexus2/reports/2026-02-24/backend_status_momentum_scaling.md`

---

## Your Task

Verify the 5 claims from the Backend Specialist's status report. For each claim, run the specified verification command, inspect the code at the specified location, and report PASS/FAIL with evidence.

---

## Claims to Verify

### Claim 1: Momentum settings exist in `warrior_types.py`
**Assertion:** Lines 115-118 contain `enable_momentum_adds`, `momentum_add_interval`, `momentum_add_size_pct`, `max_momentum_adds`. Lines 210-211 contain `last_momentum_add_price`, `momentum_add_count` on WarriorPosition.

**Verify with:**
```powershell
Select-String -Path "nexus2\domain\automation\warrior_types.py" -Pattern "enable_momentum_adds|momentum_add_interval|momentum_add_size_pct|max_momentum_adds|last_momentum_add_price|momentum_add_count"
```

---

### Claim 2: `check_momentum_add()` function exists with correct trigger criteria
**Assertion:** `warrior_monitor_scale.py` contains `async def check_momentum_add` that:
- Gates on `enable_momentum_adds` 
- Checks `momentum_add_count >= max_momentum_adds`
- Requires position green (`current_price > entry_price`)
- Checks price moved up at least `momentum_add_interval` since last add
- Returns dict with `"trigger": "momentum"`

**Verify with:**
```powershell
Select-String -Path "nexus2\domain\automation\warrior_monitor_scale.py" -Pattern "check_momentum_add|trigger.*momentum"
```
Then view lines 164-254 to confirm logic flow.

---

### Claim 3: Monitor loop integration  
**Assertion:** `warrior_monitor.py` imports and calls `check_momentum_add()` as fallback after pullback check.

**Verify with:**
```powershell
Select-String -Path "nexus2\domain\automation\warrior_monitor.py" -Pattern "check_momentum_add|momentum_add" -Context 2,3
```

---

### Claim 4: `execute_scale_in()` tracks momentum state
**Assertion:** `warrior_monitor_scale.py` has code that, when `trigger == "momentum"`, updates `position.last_momentum_add_price` and increments `position.momentum_add_count`.

**Verify with:**
```powershell
Select-String -Path "nexus2\domain\automation\warrior_monitor_scale.py" -Pattern "last_momentum_add_price|momentum_add_count" -Context 1,2
```

---

### Claim 5: API fields wired in `warrior_routes.py`
**Assertion:** `warrior_routes.py` includes `enable_momentum_adds`, `momentum_add_interval`, `momentum_add_size_pct`, `max_momentum_adds`, and `enable_improved_scaling` in request model, GET response, and PUT handler.

**Verify with:**
```powershell
Select-String -Path "nexus2\api\routes\warrior_routes.py" -Pattern "enable_momentum_adds|momentum_add_interval|enable_improved_scaling"
```
Expect at least 3 matches (request model, GET response, PUT handler).

---

### Claim 6 (Coordinator-added): Independent counters
**Assertion:** Momentum adds use `momentum_add_count`/`max_momentum_adds` independently from pullback's `scale_count`/`max_scale_count`.

**Verify:** Check that `check_momentum_add()` uses `momentum_add_count >= max_momentum_adds` (NOT `scale_count`), and `check_scale_opportunity()` uses `scale_count >= max_scale_count` (NOT `momentum_add_count`).

**Known concern:** `execute_scale_in()` line 380 increments `scale_count` for ALL add types. This means momentum adds also bump the pullback counter. Document whether this is intentional or a cross-contamination issue.

---

## Output

Write validation report to: `nexus2/reports/2026-02-24/validation_momentum_scaling.md`
