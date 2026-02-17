# Handoff: Fix Data Explorer Time Filter (All Tabs)

## Problem Statement

The Data Explorer's `time_from`/`time_to` filters are broken across **all tabs**. When a user selects "Last 1 hour" or sets a manual time range, the Trade Events tab returns 0 results — even when data clearly exists in that window. The investigation confirmed this affects all 9 Data Explorer tabs.

## Verified Facts

### Fact 1: Frontend correctly sends `time_from` and `time_to` as ET-formatted HH:MM strings

**File:** `nexus2/frontend/src/pages/data-explorer.tsx:274-278`
**Code:**
```typescript
if (dateFrom) params.set('date_from', dateFrom)
if (dateTo) params.set('date_to', dateTo)
if (timeFrom) params.set('time_from', timeFrom)
if (timeTo) params.set('time_to', timeTo)
```
**Conclusion:** Frontend sends ET times (e.g., `08:40`) correctly. No frontend changes needed.

---

### Fact 2: Trade Events endpoint has a UTC/ET mismatch

**File:** `nexus2/api/routes/data_routes.py:770-787`
**Code:**
```python
if date_from or date_to or time_from or time_to:
    filtered = []
    for e in all_events:
        created = e.get("created_at", "")
        if len(created) >= 16:
            entry_date = created[:10]
            entry_time = created[11:16]
            if date_from and entry_date < date_from:
                continue
            if date_to and entry_date > date_to:
                continue
            if time_from and entry_time < time_from:
                continue
            if time_to and entry_time > time_to:
                continue
        filtered.append(e)
    all_events = filtered
```
**Bug:** `created_at` is in **UTC** (e.g., `"2026-02-17 14:28:11"`), but `time_from`/`time_to` are **ET** (e.g., `"08:40"`). Comparing `14:28 < 08:40` = False → event filtered out incorrectly.

---

### Fact 3: SQL-based tabs accept `time_from`/`time_to` but silently ignore them

These 3 endpoints have `time_from`/`time_to` params declared but **no code uses them**:

| Endpoint | Lines with params | Lines with date filter | Time filter code |
|----------|------------------|----------------------|------------------|
| `get_warrior_scan_history` | L305-306 | L350-366 | ❌ None |
| `get_catalyst_audits` | L485-486 | L534-548 | ❌ None |
| `get_ai_comparisons` | L620-621 | L662-676 | ❌ None |

**Example** (`get_warrior_scan_history`, line 352-355):
```python
if date_from:
    try:
        et_start = dt.strptime(f"{date_from} 00:00:00", "%Y-%m-%d %H:%M:%S").replace(tzinfo=et_tz)
        utc_start = et_start.astimezone(utc_tz)
        query = query.filter(WarriorScanResult.timestamp >= utc_start)
```
The `time_from` param exists but is never incorporated — it always uses `00:00:00`.

---

### Fact 4: Four endpoints don't even accept `time_from`/`time_to` params

| Endpoint | Function | Line | Missing params |
|----------|----------|------|---------------|
| Warrior Trades | `get_warrior_trades` | L846 | `time_from`, `time_to` |
| NAC Trades | `get_nac_trades` | L126 | `time_from`, `time_to` |
| Quote Audits | `get_quote_audits` | L1013 | `time_from`, `time_to` |
| Validation Log | `get_validation_log` | L1130 | `time_from`, `time_to`, `date_from`, `date_to` |

---

### Fact 5: All SQL-based tabs do proper ET→UTC conversion for `date_from`/`date_to`

The date filter pattern is consistent. Example (`get_warrior_trades`, L921-932):
```python
if date_from:
    try:
        et_start = EASTERN.localize(dt.strptime(f"{date_from} 00:00:00", "%Y-%m-%d %H:%M:%S"))
        query = query.filter(WarriorTradeModel.entry_time >= et_to_utc(et_start))
    except ValueError:
        pass
if date_to:
    try:
        et_end = EASTERN.localize(dt.strptime(f"{date_to} 23:59:59", "%Y-%m-%d %H:%M:%S"))
        query = query.filter(WarriorTradeModel.entry_time <= et_to_utc(et_end))
    except ValueError:
        pass
```
**Note:** Some use `EASTERN.localize()` + `et_to_utc()` (Warrior Trades, NAC Trades, Quote Audits) and others use `.replace(tzinfo=et_tz)` + `.astimezone(utc_tz)` (Warrior Scans, Catalyst Audits, AI Comparisons). Both work but are inconsistent.

---

## Open Questions (For Agent Investigation)

1. **What format does `get_recent_events()` return `created_at` in?** Is it always UTC ISO format? Verify by checking `trade_event_service.py`'s `get_recent_events()` method.

2. **Should the Trade Events endpoint be refactored to use SQL filtering instead of in-memory dict filtering?** Currently it fetches 500 events and filters in Python — this is an architectural question that may be out of scope.

3. **Should a shared helper function be created** for the time-aware date filter logic to reduce duplication across endpoints? Or is the inline approach simpler given the two different patterns (SQL vs dict)?

4. **NAC Scans (`get_scan_history`)** uses log-based filtering, not SQL. Does it need `time_from`/`time_to` support? It's the only remaining log-dependent endpoint.

5. **Edge case: What if `time_from` is provided but `date_from` is not?** The current date filter requires `date_from` to be set. Verify the frontend always sends both together (the `handleTimeWindow` function does, but manual input might not).

---

## Proposed Fix Strategy

### For SQL-based endpoints (7 endpoints):
Incorporate `time_from`/`time_to` into the existing date filter by replacing the hardcoded times:
```python
# Before:
et_start = dt.strptime(f"{date_from} 00:00:00", ...)
# After:
start_time = f"{time_from}:00" if time_from else "00:00:00"
et_start = dt.strptime(f"{date_from} {start_time}", ...)

# Before:
et_end = dt.strptime(f"{date_to} 23:59:59", ...)
# After:
end_time = f"{time_to}:59" if time_to else "23:59:59"
et_end = dt.strptime(f"{date_to} {end_time}", ...)
```

### For Trade Events (dict-based):
Convert `created_at` from UTC to ET before comparing, OR convert `time_from`/`time_to` to UTC before comparing. The agent should determine which is cleaner.

### For endpoints missing params:
Add `time_from`/`time_to` Query params matching the existing pattern.

---

## File to Modify

**Single file:** `nexus2/api/routes/data_routes.py` (1243 lines)

## Verification

After implementation:
1. `python -m py_compile nexus2/api/routes/data_routes.py` — must pass
2. Deploy to VPS and test:
   - Trade Events tab → "Last 1 hour" with symbol filter → should return results
   - Warrior Scans tab → set time range 08:00-10:00 → should filter correctly
   - Test at least 3 different tabs to confirm consistency
