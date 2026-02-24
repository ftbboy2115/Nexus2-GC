# Handoff: Validate Guard Tuning Fixes

**Date:** 2026-02-24
**From:** Coordinator
**To:** Audit Validator
**Reference:** `nexus2/reports/2026-02-24/backend_status_guard_tuning.md`

---

## Claims to Verify

### Claim 1: `max_reentry_count` default is now 5
```powershell
Select-String -Path "nexus2\domain\automation\warrior_types.py" -Pattern "max_reentry_count"
```
Expect: `max_reentry_count: int = 5`

### Claim 2: No `pnl_above_threshold` or `price_past_target` in guard code
```powershell
Select-String -Path "nexus2\domain\automation\warrior_entry_guards.py" -Pattern "pnl_above_threshold|price_past_target"
```
Expect: **0 results** (code deleted)

### Claim 3: `macd_histogram_tolerance` exists in engine config
```powershell
Select-String -Path "nexus2\domain\automation\warrior_engine_types.py" -Pattern "macd_histogram_tolerance"
```
Expect: `macd_histogram_tolerance: float = -0.02`

### Claim 4: MACD gate uses histogram comparison, not binary `is_macd_bullish`
```powershell
Select-String -Path "nexus2\domain\automation\warrior_entry_guards.py" -Pattern "is_macd_bullish" -Context 2,2
```
Expect: Either 0 results in `_check_macd_gate()`, or `is_macd_bullish` used only in logging, not as the gate condition. The gate should now use `histogram < tolerance`.

Also verify the actual logic:
```powershell
Select-String -Path "nexus2\domain\automation\warrior_entry_guards.py" -Pattern "histogram.*tolerance|macd_histogram_tolerance" -Context 1,2
```

### Claim 5: Tests all pass
```powershell
cd "c:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus"; python -m pytest nexus2/tests/ -x -q --tb=short 2>&1
```
Expect: 757+ passed, 0 failures

---

## Output

Write to: `nexus2/reports/2026-02-24/validation_guard_tuning.md`
