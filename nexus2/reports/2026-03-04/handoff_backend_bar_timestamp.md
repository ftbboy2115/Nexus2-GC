# Backend Specialist Handoff: Add Timestamp to Bar Dataclass

**Date:** 2026-03-04 11:12 ET  
**From:** Coordinator  
**To:** Backend Specialist  
**Research:** `nexus2/reports/2026-03-04/research_pmh_data_source.md`  
**Output:** `nexus2/reports/2026-03-04/backend_status_bar_timestamp.md`

---

## Root Cause

`Bar` dataclass in `warrior_callbacks.py:264-270` has no `timestamp` field. Polygon's OHLCV data includes timestamps, but they're dropped during conversion to `Bar`. The PMH code can't filter pre-9:30 bars because there's no timestamp to filter on.

## Fix

### 1. Add `timestamp` to Bar dataclass
**File:** `nexus2/domain/automation/warrior_callbacks.py` (~line 264)

Add an optional `timestamp` field:
```python
@dataclass
class Bar:
    open: float
    high: float
    low: float
    close: float
    volume: int
    timestamp: Optional[datetime] = None  # UTC datetime from data provider
```

### 2. Pass timestamp through in all 5 conversion points
The planner identified 5 places where `Bar` objects are created. In each, pass the Polygon timestamp. Check the research report for exact file/line references.

### 3. Update PMH derivation in warrior_engine.py
Once Bar has timestamps, the `_get_premarket_high()` logic should work as designed — filter bars where `timestamp < 9:30 AM ET`.

## Important Notes
- `timestamp` must be Optional with default None to avoid breaking existing callers
- Only Polygon bars will have timestamps initially — that's fine, they're the primary source
- FMP fallback remains as secondary (unreliable — uses 30-min bars, gave $8.73 when PMH was ~$15)

## Verification

```powershell
# After deploying, check server logs for PMH values
ssh root@100.113.178.7 "grep 'Warrior PMH' ~/Nexus2/data/server.log | tail -10"

# Should show actual $ values derived from Polygon bars, not "No pre-market bars found"

# Batch test
python scripts/gc_quick_test.py --all --diff
```
