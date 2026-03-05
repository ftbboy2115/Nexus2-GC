# Fix: Filter Delimiter + Reason Category Grouping

## Problem

1. **Comma delimiter breaks** — Multi-select filters join values with `,` and split on `,` on the backend. Values containing commas (e.g., `"Exit (candle_under_candle) @ $1.34, P&L: $-0.20"`) get fragmented.
2. **250+ unique reason values** — The trade-events `reason` column has 250+ unique values (every fill price, exit price, cooldown time is unique). A dropdown with 250 checkboxes is unusable.

## Root Cause (Verified)

- **Frontend** (`data-explorer.tsx:291`): `params.set(key, Array.from(valueSet).join(','))`
- **Backend** (`data_routes.py:42`): `value_set = {v.strip() for v in filter_value.split(',')}`
- **Backend** (`data_routes.py:80`): `apply_generic_filters` also splits on comma (line 80)

## Changes Required

### Part 1: Switch delimiter from `,` to `|` (pipe)

**Affects ALL tabs. Pipe character doesn't appear in any column values.**

#### Frontend (`data-explorer.tsx`)
- **Line 291**: Change `Array.from(valueSet).join(',')` → `Array.from(valueSet).join('|')`

#### Backend (`data_routes.py`)
- **`_apply_multi_select` (line 42)**: Change `filter_value.split(',')` → `filter_value.split('|')`
- **`apply_generic_filters` (line ~80)**: Change `value.split(',')` → `value.split('|')` (the main split that creates `value_list`)

> [!IMPORTANT]
> Both frontend AND backend must change simultaneously. If only one side changes, ALL filters break.

### Part 2: Category grouping for trade-events `reason`

The trade-events distinct endpoint (`get_trade_events_distinct`, line ~860) currently returns every unique reason string. Instead, group them into categories by extracting prefixes.

**Proposed categories** (based on actual data):
| Category | Pattern | Example values |
|----------|---------|---------------|
| `Already holding position` | Exact match | "Already holding position" |
| `Re-entry cooldown` | Starts with "Re-entry cooldown" | "Re-entry cooldown - exited 0.2m ago (waiting 10m)" |
| `BLOCKED` | Starts with "BLOCKED" | "BLOCKED - already at max scale #4 (limit=4)" |
| `Exit (candle_under_candle)` | Starts with "Exit (candle_under_candle)" | "Exit (candle_under_candle) @ $1.34, P&L: $-0.20" |
| `Exit (topping_tail)` | Starts with "Exit (topping_tail)" | "Exit (topping_tail) @ $1.35, P&L: $-0.20" |
| `Exit (mental_stop)` | Starts with "Exit (mental_stop)" | "Exit (mental_stop) @ $1.82, P&L: $0.00" |
| `Exit (technical_stop)` | Starts with "Exit (technical_stop)" | "Exit (technical_stop) @ $2.28, P&L: $-6.55" |
| `Exit fill confirmed` | Starts with "Exit fill confirmed" | "Exit fill confirmed: $1.36 → $1.35 (1.0¢ worse)" |
| `Fill confirmed` | Starts with "Fill confirmed" | "Fill confirmed: $1.37 → $1.37 (no slippage)" |
| `Added shares` | Starts with "Added" | "Added 5 shares @ $1.84" |
| `Entry` | Ends with pattern `Entry: N shares @ $X` | "bull_flag Entry: 10 shares @ $1.539" |
| `MACD GATE` | Starts with "MACD GATE" | "MACD GATE - blocking entry..." |
| `REJECTED - spread` | Starts with "REJECTED - spread" | "REJECTED - spread 3.1% > 3.0%..." |
| `TOP_3_ONLY` | Starts with "TOP_3_ONLY" | "TOP_3_ONLY - blocked..." |
| `EoD entry cutoff` | Starts with "EoD entry cutoff" | "EoD entry cutoff: 19:06 past 19:00 ET" |
| Other | Everything else | "stop_hit", "Broker stop-out detected..." |

**Implementation approach:**

1. In the trade-events distinct endpoint, when `column == "reason"`, apply a category extraction function instead of returning raw values
2. Create `_categorize_reason(value: str) -> str` that maps raw values to category names using prefix matching
3. In the `_apply_multi_select` call for reason, convert both filter values AND event values through the same categorization function before comparing
4. This way the dropdown shows ~15 categories, and filtering matches by category prefix

**Category extraction function:**
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

**Changes to trade-events distinct endpoint:**
```python
if column == 'reason':
    # Group verbose reasons into categories
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
```

**Changes to trade-events filter logic:**
```python
# For reason, use category matching instead of exact match
if reason:
    reason_categories = {v.strip() for v in reason.split('|')}
    has_empty = '(empty)' in reason_categories
    reason_categories.discard('(empty)')
    all_events = [
        e for e in all_events
        if _categorize_reason(str(e.get('reason') or '')) in reason_categories
        or (has_empty and not e.get('reason'))
    ]
else:
    # No reason filter — skip
    pass
```

> [!NOTE]
> The reason filter should NOT use `_apply_multi_select` anymore since it needs category matching. Handle it as a special case before the generic multi-select calls.

### Part 3: Remove debug logging

Remove the temporary debug logging added to `_apply_multi_select` in commit `94bee56`.

## Other Tabs Assessment

| Tab | Column | Has commas? | High cardinality? | Needs grouping? |
|-----|--------|-------------|-------------------|-----------------|
| Warrior Scans | catalyst | Possibly | No (~10 values) | No |
| Warrior Scans | reason | No | Low | No |
| Catalyst Audits | headline | Yes | High | Consider text search instead |
| AI Comparisons | reason | Possibly | Medium | Monitor |
| Trade Events | reason | **Yes** | **250+** | **Yes — this handoff** |

The **pipe delimiter fix** (Part 1) prevents comma issues universally. Category grouping (Part 2) is only needed for trade-events reason right now.

## Verification

1. Deploy to VPS
2. Trade Events → reason dropdown should show ~15 categories instead of 250+
3. Uncheck "Already holding position" → those events should disappear
4. Check event_type filter still works (regression test for delimiter change)
5. Check filters on other tabs (Warrior Trades, Quote Audits) still work

## Files to Modify

| File | Change |
|------|--------|
| `nexus2/api/routes/data_routes.py` | Delimiter change, category function, remove debug |
| `nexus2/frontend/src/pages/data-explorer.tsx` | Delimiter change (1 line) |
