# Audit Validator Handoff: EMA Fix Claims

**Date:** 2026-03-04 12:29 ET  
**From:** Coordinator  
**To:** Audit Validator  
**Source:** `nexus2/reports/2026-03-04/backend_status_ema_fix.md`  
**Output:** `nexus2/reports/2026-03-04/validation_ema_fix.md`

---

## Claims to Verify (7)

From the specialist's status report. Verify each with code evidence.

### Claim 1: Bar reversal removed
`closes[::-1]` removed from `_get_200_ema` in `warrior_scanner_service.py`.

### Claim 2: Sanity check added
EMA values where ratio vs price >100x or <0.01x are discarded with WARNING log.

### Claim 3: `adjusted=true` added to Polygon daily bars
`get_daily_bars()` call now includes `adjusted=true` parameter.

### Claim 4: Misleading comment fixed
Line ~1183 comment about "most recent first" corrected.

### Claim 5: Health metrics never gated entries
Git history confirms `compute_position_health` and `room_to_ema` were always display-only since creation on Jan 17, 2026.

### Claim 6: gc_quick_test.py improved
New test cases are now separated from genuine improvements in diff output.

### Claim 7: Batch test — 0 regressions
39 comparable cases unchanged.
