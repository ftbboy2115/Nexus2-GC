# Audit Validator Handoff: Scanner Pipeline + Diagnostic Verification

## Objective

Independently verify claims from two agent reports:
1. **Code Auditor** → `nexus2/reports/2026-02-13/scanner_pipeline_audit.md`
2. **Backend Diagnostic** → `nexus2/reports/2026-02-13/scanner_diagnostic_results.md` + `nexus2/cli/scan_diagnostic.py`

Also investigate one KNOWN BUG the auditor missed (see T3).

## Verification Tasks

### T1: Verify Auditor Claims (C1-C7)

Run each command from the auditor's report (section "Verification Commands for Audit Validator") and verify the expected output:

```powershell
cd "c:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus"

# C1: _check_dollar_volume is dead code
Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern "_check_dollar_volume"
# Expected: Only the def line and method body. NOT called from _evaluate_symbol().

# C2: _check_price_pillar has no scan_logger
$lines = Get-Content "nexus2\domain\scanner\warrior_scanner_service.py"
$lines[1531..1549] | Select-String "scan_logger"
# Expected: No matches

# C3: _calculate_gap_pillar has no scan_logger
$lines[1551..1580] | Select-String "scan_logger"
# Expected: No matches

# C4: high_float_threshold = 30M
Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern "high_float_threshold.*30"

# C5: etb_high_float_threshold = 10M
Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern "etb_high_float_threshold.*10"

# C6: 200 EMA room at 15%
Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern "min_room_to_200ema_pct"

# C7: Commit f501ef6
git show f501ef6 --stat
```

### T2: Verify Backend Diagnostic Tool

1. Run the diagnostic for PMI and verify output matches the saved report:
```powershell
cd "c:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus"
python -m nexus2.cli.scan_diagnostic PMI 2026-02-12
```
2. Verify the `--all-test-cases` flag works (reads warrior_setups.yaml):
```powershell
python -m nexus2.cli.scan_diagnostic --all-test-cases
```
3. Check the code quality of `nexus2/cli/scan_diagnostic.py`:
   - Does it properly load .env?
   - Does it handle API errors gracefully?
   - Does it correctly calculate gap% (open vs prev_close)?

### T3: KNOWN BUG — MGRT gap_too_low Contradiction (AUDITOR MISSED THIS)

> [!CAUTION]
> The auditor did NOT catch this bug. This is a coordinator-identified issue requiring independent investigation.

In the **Data Explorer → Warrior Scans** tab (screenshot from Feb 13 at 08:29), MGRT shows:
- `gap_pct`: **112.39** (that's 112% gap!)
- `result`: FAIL
- `reason`: **gap_too_low**

This is clearly wrong — 112% gap should easily pass the min 4% gap threshold. Investigate:

1. Look at `_calculate_gap_pillar()` in `warrior_scanner_service.py` — what could cause a 112% gap stock to fail with "gap_too_low"?
2. Is the gap being recalculated and coming back wrong? Is there a stale data issue?
3. Check the scan_history.json or telemetry DB for MGRT entries on Feb 13

```powershell
# Search for gap pillar logic
Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern "_calculate_gap_pillar" -Context 0,30

# Search for gap_too_low anywhere
Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern "gap_too_low"
```

Also check the Data Explorer scan results API:
```powershell
# Check what the telemetry DB shows for MGRT
ssh root@100.113.178.7 "sqlite3 /root/Nexus2/data/telemetry.db \"SELECT * FROM warrior_scan_results WHERE symbol='MGRT' ORDER BY timestamp DESC LIMIT 5\""
```

## Deliverable

Write validation report to `nexus2/reports/2026-02-13/scanner_audit_validation.md` with:

### Required Format
```markdown
## Validation Report: Scanner Pipeline Audit + Diagnostic

### Auditor Claims Verified
| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| C1 | _check_dollar_volume is dead code | PASS/FAIL | [exact command output] |
| C2 | ... | ... | ... |
...

### Backend Diagnostic Verified
| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| D1 | PMI diagnostic output matches saved report | PASS/FAIL | ... |
| D2 | --all-test-cases flag works | PASS/FAIL | ... |
| D3 | Code quality acceptable | PASS/FAIL | ... |

### MGRT Gap Bug Investigation
| Finding | Evidence |
|---------|----------|
| Root cause | [what you found] |
| Why 112% gap fails as gap_too_low | [explanation] |
| Fix recommendation | [what to change] |

### Overall Rating
- **HIGH**: All claims verified
- **MEDIUM**: Minor issues (cosmetic)
- **LOW**: Major issues (requires rework)
```
