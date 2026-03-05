# Technical Spec: Filter Delimiter & Reason Category Grouping

> **For:** Backend Specialist (implementation)
> **From:** Backend Planner (research)
> **Handoff:** `handoff_filter_delimiter_and_grouping.md`

---

## A. Existing Pattern Analysis

All data explorer filtering goes through three shared helpers and one SQL-layer function.
The frontend sends multi-select filters as comma-joined strings; the backend splits on comma.

| Function | File | Lines | Purpose |
|----------|------|-------|---------|
| `_apply_exact_time_filter` | `data_routes.py` | 21–36 | In-memory timestamp filter, splits on `,` at **line 35** |
| `_apply_multi_select` | `data_routes.py` | 38–57 | In-memory multi-select filter, splits on `,` at **line 44** |
| `apply_generic_filters` | `data_routes.py` | 59–139 | SQLAlchemy query filter, splits on `,` at **line 92** |
| NAC entry_time filter | `data_routes.py` | 208–214 | Inline split on `,` at **line 211** |
| Frontend join | `data-explorer.tsx` | 291 | `Array.from(valueSet).join(',')` |

---

## B. Change Surface Enumeration

| # | File | Change | Location | Atomic? |
|---|------|--------|----------|---------|
| 1 | `data-explorer.tsx` | Change join delimiter `,` → `\|` | Line 291 | Must ship with #2–5 |
| 2 | `data_routes.py` | Change split in `_apply_exact_time_filter` | Line 35 | Yes |
| 3 | `data_routes.py` | Change split in `_apply_multi_select` + remove debug logging | Lines 42–57 | Yes |
| 4 | `data_routes.py` | Change split in `apply_generic_filters` | Line 92 | Yes |
| 5 | `data_routes.py` | Change split in NAC `entry_time` inline handler | Line 211 | Yes |
| 6 | `data_routes.py` | Update docstrings referencing "comma-separated" | Lines 23, 28, 39, 65–67 | Yes |
| 7 | `data_routes.py` | Add `_categorize_reason()` function | New function, after line 57 | No |
| 8 | `data_routes.py` | Modify trade-events `reason` filter to use category matching | Line 801 | Yes |
| 9 | `data_routes.py` | Modify `get_trade_events_distinct` for `reason` column grouping | Lines 871–895 | Yes |

---

## C. Detailed Change Specifications

### Change Point #1 — Frontend delimiter (CRITICAL — must deploy with backend)
**What:** Change multi-select join from `,` to `|`
**File:** `nexus2/frontend/src/pages/data-explorer.tsx`
**Location:** Line 291, inside `fetchData` callback
**Current Code:**
```typescript
                    params.set(key, Array.from(valueSet).join(','))
```
**Replacement:**
```typescript
                    params.set(key, Array.from(valueSet).join('|'))
```

---

### Change Point #2 — `_apply_exact_time_filter` split delimiter
**File:** `nexus2/api/routes/data_routes.py`
**Location:** Line 35, function `_apply_exact_time_filter`
**Current Code:**
```python
    value_set = {v.strip() for v in filter_value.split(',')}
```
**Replacement:**
```python
    value_set = {v.strip() for v in filter_value.split('|')}
```
**Also update docstring** at line 23 and 28: change "comma-separated" → "pipe-separated"

---

### Change Point #3 — `_apply_multi_select` split delimiter + remove debug logging
**File:** `nexus2/api/routes/data_routes.py`
**Location:** Lines 38–57, function `_apply_multi_select`
**Current Code:**
```python
def _apply_multi_select(entries: List[dict], column: str, filter_value: Optional[str]) -> List[dict]:
    """Filter in-memory entries by comma-separated multi-select values."""
    if not filter_value:
        return entries
    import logging
    _log = logging.getLogger("data_routes.multi_select")
    value_set = {v.strip() for v in filter_value.split(',')}
    has_empty = '(empty)' in value_set
    value_set.discard('(empty)')
    _log.info(f"[DEBUG] column={column}, filter_value={filter_value!r}, value_set={value_set}, has_empty={has_empty}")
    # Sample first 3 entries to see what column values look like
    for e in entries[:3]:
        _log.info(f"[DEBUG] entry[{column}]={e.get(column)!r}, str={str(e.get(column) or '')!r}")
    result = [
        e for e in entries
        if str(e.get(column) or '') in value_set
        or (has_empty and not e.get(column))
    ]
    _log.info(f"[DEBUG] before={len(entries)}, after={len(result)}")
    return result
```
**Replacement:**
```python
def _apply_multi_select(entries: List[dict], column: str, filter_value: Optional[str]) -> List[dict]:
    """Filter in-memory entries by pipe-separated multi-select values."""
    if not filter_value:
        return entries
    value_set = {v.strip() for v in filter_value.split('|')}
    has_empty = '(empty)' in value_set
    value_set.discard('(empty)')
    return [
        e for e in entries
        if str(e.get(column) or '') in value_set
        or (has_empty and not e.get(column))
    ]
```

> [!IMPORTANT]
> This removes the `import logging`, the `_log` variable, and all 3 `_log.info` calls (Part 3 of the handoff).

---

### Change Point #4 — `apply_generic_filters` split delimiter
**File:** `nexus2/api/routes/data_routes.py`
**Location:** Line 92, function `apply_generic_filters`
**Current Code:**
```python
        # Split comma-separated values
        value_list = [v.strip() for v in value.split(',')]
```
**Replacement:**
```python
        # Split pipe-separated values
        value_list = [v.strip() for v in value.split('|')]
```
**Also update docstring** at lines 65–67: change "US,CN" → "US|CN" and ">=5,<=10" → ">=5|<=10"

---

### Change Point #5 — NAC trades `entry_time` inline split
**File:** `nexus2/api/routes/data_routes.py`
**Location:** Line 211, inside `get_nac_trades`
**Current Code:**
```python
            for t in entry_time.split(','):
```
**Replacement:**
```python
            for t in entry_time.split('|'):
```
**Also update comment** on line 206: change "comma-separated" → "pipe-separated"

---

### Change Point #6 — New `_categorize_reason()` function
**File:** `nexus2/api/routes/data_routes.py`
**Location:** Insert AFTER `_apply_multi_select` (after line 57), BEFORE `apply_generic_filters` (line 59)
**New Code:**
```python
def _categorize_reason(reason: str) -> str:
    """Map verbose reason strings to filterable categories."""
    if not reason:
        return ''
    prefixes = [
        'Re-entry cooldown', 'BLOCKED', 'Exit (candle_under_candle)',
        'Exit (topping_tail)', 'Exit (mental_stop)', 'Exit (technical_stop)',
        'Exit fill confirmed', 'Exit callback failed', 'Fill confirmed',
        'MACD GATE', 'REJECTED - spread', 'TOP_3_ONLY', 'EoD entry cutoff',
        'Re-entry BLOCKED', 'Stop moved', 'Orphan auto-closed',
    ]
    for prefix in prefixes:
        if reason.startswith(prefix):
            return prefix
    if reason.startswith('Added ') and 'shares @' in reason:
        return 'Added shares'
    if 'Entry:' in reason and 'shares @' in reason:
        return 'Entry'
    return reason  # Keep as-is if no category matches
```

---

### Change Point #7 — Trade events `reason` filter: category matching
**File:** `nexus2/api/routes/data_routes.py`
**Location:** Line 801, inside `get_trade_events`
**Current Code:**
```python
    all_events = _apply_multi_select(all_events, "reason", reason)
```
**Replacement:**
```python
    # Reason uses category matching instead of exact match
    if reason:
        reason_categories = {v.strip() for v in reason.split('|')}
        has_empty = '(empty)' in reason_categories
        reason_categories.discard('(empty)')
        all_events = [
            e for e in all_events
            if _categorize_reason(str(e.get('reason') or '')) in reason_categories
            or (has_empty and not e.get('reason'))
        ]
```

---

### Change Point #8 — Trade events distinct endpoint: reason grouping
**File:** `nexus2/api/routes/data_routes.py`
**Location:** Lines 871–895, function `get_trade_events_distinct`
**Current Code:**
```python
    all_events = trade_event_service.get_recent_events(None, limit=1000)
    
    values = set()
    has_empty = False
    for event in all_events:
        val = event.get(column)
        if val is None or val == '':
            has_empty = True
        elif val is not None:
            values.add(str(val))
    
    result = sorted(list(values))
    if has_empty:
        result.append('(empty)')
    return {"column": column, "values": result}
```
**Replacement:**
```python
    all_events = trade_event_service.get_recent_events(None, limit=1000)
    
    # For reason column, group into categories instead of raw values
    if column == 'reason':
        categories = set()
        has_empty = False
        for event in all_events:
            val = event.get('reason')
            if val is None or val == '':
                has_empty = True
            else:
                categories.add(_categorize_reason(str(val)))
        result = sorted(list(categories))
        if has_empty:
            result.append('(empty)')
        return {"column": column, "values": result}
    
    values = set()
    has_empty = False
    for event in all_events:
        val = event.get(column)
        if val is None or val == '':
            has_empty = True
        elif val is not None:
            values.add(str(val))
    
    result = sorted(list(values))
    if has_empty:
        result.append('(empty)')
    return {"column": column, "values": result}
```

---

## D. Wiring Checklist

- [ ] Frontend: change `.join(',')` → `.join('|')` on line 291
- [ ] `_apply_exact_time_filter`: change `.split(',')` → `.split('|')` + update docstring
- [ ] `_apply_multi_select`: change `.split(',')` → `.split('|')` + remove debug logging + update docstring
- [ ] `apply_generic_filters`: change `.split(',')` → `.split('|')` + update docstring + update comment
- [ ] NAC `entry_time`: change `.split(',')` → `.split('|')` + update comment
- [ ] Add `_categorize_reason()` function after `_apply_multi_select`
- [ ] Trade events: replace `_apply_multi_select(... "reason" ...)` with category matching block
- [ ] Trade events distinct: add `if column == 'reason'` branch with category grouping
- [ ] Run existing tests: `python -m pytest nexus2/tests/api/test_data_routes.py -v`

---

## E. Risk Assessment

### What could go wrong
1. **Frontend/backend mismatch** — If only one side deploys, ALL filters break for ALL tabs. **Deploy atomically.**
2. **Pipe in data values** — The handoff claims pipe doesn't appear in values. This was NOT independently verified. If any column value contains `|`, that filter will break. Low probability but worth noting.
3. **Category mismatch** — If a reason string doesn't match any prefix, it falls through as-is. The distinct endpoint will show the raw value. This is safe but could mean uncategorized reasons appear in the dropdown.
4. **Range filters interaction** — `apply_generic_filters` supports range patterns like `>=5|<=10`. The pipe won't conflict with range operators since `>`, `<`, `=` are not `|`.

### What existing behavior might break
- All multi-select filters across ALL tabs go through the same helpers, so the delimiter change is global
- The `entry_time` filter in NAC trades uses an inline split, not the helpers — must be changed separately
- CSV export (line 583-584) uses commas for CSV format — this is CORRECT and should NOT be changed

### What to test after implementation
1. Run `python -m pytest nexus2/tests/api/test_data_routes.py -v` — existing tests should pass
2. Deploy to VPS and verify:
   - Trade Events → reason dropdown shows ~15 categories instead of 250+
   - Uncheck "Already holding position" → those events disappear
   - Check event_type filter still works (regression test for delimiter change)
   - Check filters on other tabs (Warrior Scans, Quote Audits) still work
3. Verify no debug logging in `_apply_multi_select` output

---

## F. Files Summary

| File | Changes |
|------|---------|
| `nexus2/api/routes/data_routes.py` | 8 change points: delimiter ×4, debug removal, new function, category matching, distinct grouping |
| `nexus2/frontend/src/pages/data-explorer.tsx` | 1 change point: join delimiter |
