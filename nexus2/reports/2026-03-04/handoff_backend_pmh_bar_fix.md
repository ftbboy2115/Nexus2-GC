# Backend Specialist Follow-up: PMH Bar Fetching Bug

**Date:** 2026-03-04 10:04 ET  
**From:** Coordinator  
**To:** Backend Specialist  
**Priority:** URGENT — affects live trading NOW  
**Previous:** `nexus2/reports/2026-03-04/backend_status_entry_guard_fixes.md`  
**Output:** `nexus2/reports/2026-03-04/backend_status_pmh_bar_fix.md`

---

## Bug

Server logs show:
```
[Warrior PMH] CANF: No pre-market bars found in Polygon data
[Warrior PMH] VCIG: No pre-market bars found in Polygon data
```

**But CANF clearly has massive premarket activity** — chart shows a run from $4 to $15 between 4:00-9:30 AM ET. Polygon definitely has these bars.

## Likely Root Causes (investigate both)

### 1. Bar limit too small
If `_get_intraday_bars(symbol, "1min", limit=100)` is used, and it's now 10:00 AM (30 min into regular hours), the 100 bars returned may all be regular-hours bars. Premarket bars (4:00-9:30 = 330 min) would require a larger limit.

**Fix:** Request enough bars to cover the full premarket window. At minimum `limit=400` to cover premarket + first hour of regular trading.

### 2. Timezone mismatch
The bar timestamps from Polygon may be in UTC. If the code filters for `timestamp < 9:30 AM` without timezone conversion, it would compare against 9:30 UTC (4:30 AM ET), missing most premarket bars.

**Fix:** Ensure all timestamp comparisons use Eastern Time or convert bar timestamps to ET before filtering.

## Verification

```powershell
# Check if PMH is now being logged correctly after fix
ssh root@100.113.178.7 "grep 'Warrior PMH' ~/Nexus2/data/server.log | tail -10"
```

Expected: CANF should show a PMH value around $15 (the premarket peak), not "No pre-market bars found".

```powershell
# Batch test regression check
python scripts/gc_quick_test.py --all --diff
```
