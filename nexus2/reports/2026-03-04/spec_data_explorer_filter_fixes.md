# Technical Spec: Data Explorer Multi-Select Filter Fixes

> **Planner:** Backend Planner | **Date:** 2026-03-04
> **Source:** [handoff_data_explorer_filter_fixes.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-03-04/handoff_data_explorer_filter_fixes.md)

---

## A. Existing Pattern Analysis (Template)

The working template is `apply_generic_filters()` at [data_routes.py:38-118](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/data_routes.py#L38-L118).

This function:
1. Accepts `**filters` as `{column_name: comma_separated_string}`
2. Splits on commas → `value_list`
3. Handles `(empty)` → `col.is_(None)`
4. Handles range operators (`>=`, `<=`, `>`, `<`)
5. Handles equality → `col.in_(equality_values)`
6. Combines with `OR` (empty OR equality OR range)

**Working endpoints using this template:**

| Endpoint | Function | Lines | Columns via `apply_generic_filters` |
|----------|----------|-------|-------------------------------------|
| warrior-scans | `get_warrior_scan_history` | 303-428 | symbol, result, country, score, source |
| catalyst-audits | `get_catalyst_audits` | 485-590 | symbol, result, match_type, confidence, source |
| ai-comparisons | `get_ai_comparisons` | 622-721 | symbol, flash_result, pro_result, winner |

For **in-memory** (non-SQLAlchemy) endpoints, a parallel helper exists: `_apply_exact_time_filter()` at [data_routes.py:21-36](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/data_routes.py#L21-L36) — supports comma-separated values with set membership check.

---

## B. Additional Bug: `__EMPTY__` vs `(empty)` Mismatch

> [!IMPORTANT]
> The manual endpoints check for `'__EMPTY__'` to handle NULL, but the **frontend sends `'(empty)'`** (verified at [data-explorer.tsx:745](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/frontend/src/pages/data-explorer.tsx#L745)).
> This means NULL filtering in the manual endpoints was **already broken** — the `__EMPTY__` branches were dead code.
> Migrating to `apply_generic_filters()` fixes this automatically since it handles `(empty)` correctly (line 79-80).

---

## C. Change Surface Enumeration

| # | File | Change | Location | Type |
|---|------|--------|----------|------|
| 1 | `data_routes.py` | Add `_apply_multi_select()` in-memory helper | After line 36 (new function) | NEW |
| 2 | `data_routes.py` | Add `reason` query param + fix `symbol`, `event_type` filtering | `get_trade_events`, lines 752-846 | MODIFY |
| 3 | `data_routes.py` | Replace manual `==` with `apply_generic_filters()` for string cols | `get_warrior_trades`, lines 876-995 | MODIFY |
| 4 | `data_routes.py` | Replace manual `==` with `apply_generic_filters()` for string cols | `get_nac_trades`, lines 125-225 | MODIFY |
| 5 | `data_routes.py` | Replace manual `==` with `apply_generic_filters()` for string cols | `get_quote_audits`, lines 1047-1138 | MODIFY |
| 6 | `data_routes.py` | Replace manual `==` with `apply_generic_filters()` for string cols | `get_validation_log`, lines 1168-1252 | MODIFY |
| 7 | `data_routes.py` | Fix `symbol`, `source`, `catalyst` filtering for in-memory endpoint | `get_scan_history`, lines 232-296 | MODIFY |

---

## D. Detailed Change Specifications

### Change Point #1: New `_apply_multi_select()` helper for in-memory endpoints

**What:** Create a helper like `_apply_exact_time_filter` but for general string columns
**File:** [data_routes.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/data_routes.py)
**Location:** After line 36 (after `_apply_exact_time_filter`)
**Template:** `_apply_exact_time_filter` at lines 21-36
**Approach:** Create helper that:
1. Takes `entries: List[dict]`, `column: str`, `filter_value: Optional[str]`
2. If no filter_value, returns entries unchanged
3. Splits on commas to a set
4. Handles `(empty)` → matches entries where column is None/empty
5. Returns filtered entries where `str(value)` is in the value set

```
def _apply_multi_select(entries: List[dict], column: str, filter_value: Optional[str]) -> List[dict]:
    """Filter in-memory entries by comma-separated multi-select values."""
    if not filter_value:
        return entries
    value_set = {v.strip() for v in filter_value.split(',')}
    has_empty = '(empty)' in value_set
    value_set.discard('(empty)')
    return [
        e for e in entries
        if str(e.get(column) or '') in value_set
        or (has_empty and not e.get(column))
    ]
```

---

### Change Point #2: Trade Events — `get_trade_events` (in-memory)

**File:** [data_routes.py:752-846](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/data_routes.py#L752-L846)

#### 2a. Add `reason` query parameter

**Current code (line 752-766):**
```python
async def get_trade_events(
    limit: int = Query(50, ge=1, le=500, description="Maximum records to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    strategy: Optional[str] = Query(None, description="Filter by strategy: NAC or WARRIOR"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    time_from: Optional[str] = Query(None, description="Start time (HH:MM)"),
    time_to: Optional[str] = Query(None, description="End time (HH:MM)"),
    created_at: Optional[str] = Query(None, description="Filter by exact created_at timestamp"),
    sort_by: str = Query("created_at", description="Column to sort by"),
    sort_dir: str = Query("desc", description="Sort direction: asc or desc"),
):
```

**Approach:** Add `reason: Optional[str] = Query(None, description="Filter by reason")` into the parameter list.

#### 2b. Replace manual `symbol` and `event_type` filters with `_apply_multi_select`

**Current code (lines 776-779):**
```python
    if symbol:
        all_events = [e for e in all_events if e.get("symbol", "").upper() == symbol.upper()]
    if event_type:
        all_events = [e for e in all_events if e.get("event_type") == event_type]
```

**Approach:** Replace with:
```python
    all_events = _apply_multi_select(all_events, "symbol", symbol.upper() if symbol else None)
    all_events = _apply_multi_select(all_events, "event_type", event_type)
    all_events = _apply_multi_select(all_events, "reason", reason)
```

> [!NOTE]
> **Symbol case:** For `symbol`, the frontend sends comma-separated already-uppercase values (they come from distinct values which are stored uppercase). The `_apply_multi_select` helper compares `str(e.get(column) or '')` which preserves case. Since events store symbol uppercase, and filter values come from distinct (uppercase), this should work without `upper()` transformation. But to be safe, the implementer should `.upper()` the filter value string before passing to `_apply_multi_select`.

#### 2c. Add `strategy` to multi-select too

**Current code (line 773):**
```python
    all_events = trade_event_service.get_recent_events(strategy, limit=500)
```

The `strategy` param is passed directly to `get_recent_events()` which handles it internally. This is fine for single values but won't work for multi-select. However, reviewing the handoff, `strategy` is not listed as a broken filter — it's a simple dropdown (WARRIOR/NAC), not a multi-select checkbox. **Leave `strategy` as-is.**

---

### Change Point #3: Warrior Trades — `get_warrior_trades` (SQLAlchemy)

**File:** [data_routes.py:876-995](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/data_routes.py#L876-L995)

**Current code (lines 906-952):**
```python
        # Apply filters (handle __EMPTY__ for NULL filtering)
        if status:
            if status == '__EMPTY__':
                query = query.filter(WarriorTradeModel.status == None)
            else:
                query = query.filter(WarriorTradeModel.status == status)
        if symbol:
            query = query.filter(WarriorTradeModel.symbol == symbol.upper())
        if exit_reason:
            if exit_reason == '__EMPTY__':
                query = query.filter(WarriorTradeModel.exit_reason == None)
            else:
                query = query.filter(WarriorTradeModel.exit_reason == exit_reason)
        if trigger_type:
            ... (same pattern for trigger_type, quote_source, exit_mode, stop_method)
        if is_sim is not None:
            if is_sim.lower() == 'null' or is_sim == '__EMPTY__':
                query = query.filter(WarriorTradeModel.is_sim == None)
            elif is_sim.lower() == 'true':
                query = query.filter(WarriorTradeModel.is_sim == True)
            elif is_sim.lower() == 'false':
                query = query.filter(WarriorTradeModel.is_sim == False)
        if partial_taken is not None:
            ... (same boolean pattern)
```

**Approach:** Replace lines 906-952 with:

1. Use `apply_generic_filters()` for all **string** columns:
```python
        # Apply multi-select filters via generic handler
        query = apply_generic_filters(
            query, WarriorTradeModel,
            status=status,
            symbol=symbol.upper() if symbol else None,
            exit_reason=exit_reason,
            trigger_type=trigger_type,
            quote_source=quote_source,
            exit_mode=exit_mode,
            stop_method=stop_method,
        )
```

2. Keep **boolean** columns (`is_sim`, `partial_taken`) as manual handlers:
```python
        # Boolean columns need special handling (not string-based)
        if is_sim is not None:
            if is_sim.lower() in ('null', '(empty)'):
                query = query.filter(WarriorTradeModel.is_sim == None)
            elif is_sim.lower() == 'true':
                query = query.filter(WarriorTradeModel.is_sim == True)
            elif is_sim.lower() == 'false':
                query = query.filter(WarriorTradeModel.is_sim == False)
        if partial_taken is not None:
            if partial_taken.lower() in ('null', '(empty)'):
                query = query.filter(WarriorTradeModel.partial_taken == None)
            elif partial_taken.lower() == 'true':
                query = query.filter(WarriorTradeModel.partial_taken == True)
            elif partial_taken.lower() == 'false':
                query = query.filter(WarriorTradeModel.partial_taken == False)
```

> [!IMPORTANT]
> Boolean handling change: Replace `'__EMPTY__'` with `'(empty)'` to match what the frontend sends. Also keep `'null'` for backward compat.

---

### Change Point #4: NAC Trades — `get_nac_trades` (SQLAlchemy)

**File:** [data_routes.py:125-225](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/data_routes.py#L125-L225)

**Current code (lines 160-179):**
```python
        # Apply filters (handle __EMPTY__ for NULL filtering)
        if status:
            if status == '__EMPTY__':
                query = query.filter(NACTradeModel.status == None)
            else:
                query = query.filter(NACTradeModel.status == status)
        if symbol:
            query = query.filter(NACTradeModel.symbol == symbol.upper())
        if partial_taken is not None:
            query = query.filter(NACTradeModel.partial_taken == partial_taken)
        if exit_reason:
            if exit_reason == '__EMPTY__':
                query = query.filter(NACTradeModel.exit_reason == None)
            else:
                query = query.filter(NACTradeModel.exit_reason == exit_reason)
        if setup_type:
            if setup_type == '__EMPTY__':
                query = query.filter(NACTradeModel.setup_type == None)
            else:
                query = query.filter(NACTradeModel.setup_type == setup_type)
```

**Approach:** Replace lines 160-179 with:
```python
        # Apply multi-select filters via generic handler
        query = apply_generic_filters(
            query, NACTradeModel,
            status=status,
            symbol=symbol.upper() if symbol else None,
            exit_reason=exit_reason,
            setup_type=setup_type,
        )
        # Boolean column - keep manual handling
        if partial_taken is not None:
            query = query.filter(NACTradeModel.partial_taken == partial_taken)
```

> [!NOTE]
> `partial_taken` is declared as `Optional[bool]` (not `Optional[str]`), so FastAPI already converts it to a Python bool. No string parsing needed — keep as-is.

---

### Change Point #5: Quote Audits — `get_quote_audits` (SQLAlchemy)

**File:** [data_routes.py:1047-1138](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/data_routes.py#L1047-L1138)

**Current code (lines 1078-1095):**
```python
        # Apply filters (handle __EMPTY__ for NULL filtering)
        if symbol:
            if symbol == '__EMPTY__':
                query = query.filter(QuoteAuditModel.symbol == None)
            else:
                query = query.filter(QuoteAuditModel.symbol == symbol.upper())
        if time_window:
            if time_window == '__EMPTY__':
                query = query.filter(QuoteAuditModel.time_window == None)
            else:
                query = query.filter(QuoteAuditModel.time_window == time_window)
        if selected_source:
            if selected_source == '__EMPTY__':
                query = query.filter(QuoteAuditModel.selected_source == None)
            else:
                query = query.filter(QuoteAuditModel.selected_source == selected_source)
        if high_divergence is not None:
            query = query.filter(QuoteAuditModel.high_divergence == high_divergence)
```

**Approach:** Replace lines 1078-1095 with:
```python
        # Apply multi-select filters via generic handler
        query = apply_generic_filters(
            query, QuoteAuditModel,
            symbol=symbol.upper() if symbol else None,
            time_window=time_window,
            selected_source=selected_source,
        )
        # Boolean column - keep manual handling
        if high_divergence is not None:
            query = query.filter(QuoteAuditModel.high_divergence == high_divergence)
```

---

### Change Point #6: Validation Log — `get_validation_log` (SQLAlchemy)

**File:** [data_routes.py:1168-1252](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/data_routes.py#L1168-L1252)

**Current code (lines 1197-1208):**
```python
        # Apply filters
        if symbol:
            query = query.filter(EntryValidationLogModel.symbol == symbol.upper())
        if entry_trigger:
            query = query.filter(EntryValidationLogModel.entry_trigger == entry_trigger)
        if target_hit is not None:
            if target_hit == '__EMPTY__':
                query = query.filter(EntryValidationLogModel.target_hit == None)
            elif target_hit.lower() == 'true':
                query = query.filter(EntryValidationLogModel.target_hit == True)
            elif target_hit.lower() == 'false':
                query = query.filter(EntryValidationLogModel.target_hit == False)
```

**Approach:** Replace lines 1197-1208 with:
```python
        # Apply multi-select filters via generic handler
        query = apply_generic_filters(
            query, EntryValidationLogModel,
            symbol=symbol.upper() if symbol else None,
            entry_trigger=entry_trigger,
        )
        # Boolean column - keep manual handling
        if target_hit is not None:
            if target_hit.lower() in ('(empty)', 'null'):
                query = query.filter(EntryValidationLogModel.target_hit == None)
            elif target_hit.lower() == 'true':
                query = query.filter(EntryValidationLogModel.target_hit == True)
            elif target_hit.lower() == 'false':
                query = query.filter(EntryValidationLogModel.target_hit == False)
```

---

### Change Point #7: Scan History — `get_scan_history` (in-memory)

**File:** [data_routes.py:232-296](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/data_routes.py#L232-L296)

**Current code (lines 268-279):**
```python
    # Apply filters
    if date_from:
        all_entries = [e for e in all_entries if e["date"] >= date_from]
    if date_to:
        all_entries = [e for e in all_entries if e["date"] <= date_to]
    if symbol:
        all_entries = [e for e in all_entries if e["symbol"].upper() == symbol.upper()]
    if source:
        all_entries = [e for e in all_entries if e.get("source", "scan") == source]
    if catalyst:
        all_entries = [e for e in all_entries if e.get("catalyst", "") == catalyst]
    all_entries = _apply_exact_time_filter(all_entries, "logged_at", logged_at)
```

**Approach:** Replace `symbol`, `source`, `catalyst` lines (273-278) with `_apply_multi_select`:
```python
    if date_from:
        all_entries = [e for e in all_entries if e["date"] >= date_from]
    if date_to:
        all_entries = [e for e in all_entries if e["date"] <= date_to]
    all_entries = _apply_multi_select(all_entries, "symbol", symbol.upper() if symbol else None)
    all_entries = _apply_multi_select(all_entries, "source", source)
    all_entries = _apply_multi_select(all_entries, "catalyst", catalyst)
    all_entries = _apply_exact_time_filter(all_entries, "logged_at", logged_at)
```

> [!NOTE]
> The original symbol filter uses `.upper()` on both sides. Since stored symbol values are already uppercase, `.upper()` on the filter value is sufficient.

---

## E. Wiring Checklist

- [ ] Add `_apply_multi_select()` helper function after `_apply_exact_time_filter` (line 36)
- [ ] **Trade Events:** Add `reason` query param; replace `symbol`/`event_type` filters with `_apply_multi_select`; add `reason` filter
- [ ] **Warrior Trades:** Replace 7 manual string filters (lines 907-938) with `apply_generic_filters()` call; update boolean `__EMPTY__` to `(empty)` 
- [ ] **NAC Trades:** Replace 3 manual string filters (lines 161-179) with `apply_generic_filters()` call
- [ ] **Quote Audits:** Replace 3 manual string filters (lines 1079-1093) with `apply_generic_filters()` call
- [ ] **Validation Log:** Replace 2 manual string filters (lines 1198-1201) with `apply_generic_filters()` call; update boolean `__EMPTY__` to `(empty)`
- [ ] **Scan History:** Replace 3 manual Python filters (lines 273-278) with `_apply_multi_select()` calls
- [ ] Run existing tests: `cd nexus2; python -m pytest tests/api/test_data_routes.py -v`

---

## F. Risk Assessment

### What could go wrong
1. **Symbol case sensitivity:** `apply_generic_filters()` does exact string match. Symbol values in DB are uppercase. As long as we pass `symbol.upper()` before calling the function, this is safe.
2. **Boolean column breakage:** If boolean columns (`is_sim`, `partial_taken`, `high_divergence`, `target_hit`) are routed through `apply_generic_filters()`, they'd be treated as strings (`"True"` vs `True`), causing match failures. **Mitigation:** Keep boolean columns as manual handlers.
3. **`(empty)` handling for `_apply_multi_select`:** The helper checks `not e.get(column)` which is truthy for `None`, `""`, and `0`. For string columns this is correct; for numeric columns it could match `0`. But none of these in-memory endpoints filter numeric columns, so this is safe.

### What existing behavior might break
- **None.** All changes are backward-compatible: single-value filters still work (a single value has no comma, so `split(',')` returns `[value]`, and `IN (value)` is equivalent to `== value`).
- The only change in semantics is that `(empty)` now correctly triggers NULL filtering (fixing the `__EMPTY__` mismatch).

### Existing tests to verify
```powershell
cd nexus2; python -m pytest tests/api/test_data_routes.py -v
```

### Suggested new tests (for implementer)
The implementer should add tests for multi-select filtering. Example test cases:
- `GET /data/warrior-trades?status=FILLED,EXITED` → returns only trades with those statuses
- `GET /data/trade-events?event_type=ENTRY_TRIGGERED,EXIT_STOP` → returns only those event types
- `GET /data/warrior-trades?exit_reason=(empty)` → returns trades with NULL exit_reason

---

## G. Summary

This is a straightforward, mechanical migration. The pattern (`apply_generic_filters`) already exists and works correctly for 3 endpoints. The fix is to adopt it for the remaining 4 SQLAlchemy endpoints, create a parallel in-memory helper for the 2 Python-dict endpoints, and add the missing `reason` parameter to trade-events. Total changes: **1 new helper function + 6 endpoint modifications**, all in a single file (`data_routes.py`).
