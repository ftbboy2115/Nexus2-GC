# Backend Status: Filter Delimiter & Reason Category Grouping

> **Date:** 2026-03-04
> **Spec:** `spec_filter_delimiter_and_grouping.md`

## Changes Made

### `data_routes.py` — 7 change points

| # | Change | Lines |
|---|--------|-------|
| 2 | `_apply_exact_time_filter`: `.split(',')` → `.split('|')` + docstring updated | 21–36 |
| 3 | `_apply_multi_select`: `.split(',')` → `.split('|')`, removed `import logging`, `_log`, and 3 `_log.info` calls, updated docstring | 38–49 |
| 4 | `apply_generic_filters`: `.split(',')` → `.split('|')`, docstring examples updated (`US,CN` → `US|CN`, `>=5,<=10` → `>=5|<=10`) | 59–92 |
| 5 | NAC `entry_time` inline: `.split(',')` → `.split('|')` + comment updated | 206–211 |
| 6 | New `_categorize_reason()` function added after `_apply_multi_select` | 51–73 |
| 7 | Trade events: `_apply_multi_select(... "reason" ...)` replaced with category matching block | 813–822 |
| 8 | Trade events distinct: `if column == 'reason'` branch for category grouping | 893–907 |

### `data-explorer.tsx` — 1 change point

| # | Change | Line |
|---|--------|------|
| 1 | `.join(',')` → `.join('|')` | 291 |

## Test Results

```
31 passed in 21.42s
```

Zero regressions.

## Testable Claims

| # | Claim | How to verify |
|---|-------|---------------|
| 1 | No debug logging remains in `_apply_multi_select` | `Select-String "data_routes.multi_select" data_routes.py` → 0 results |
| 2 | All 4 backend split points use pipe | `Select-String "\.split\(','\)" data_routes.py` → 0 results (within helper functions) |
| 3 | `_categorize_reason` function exists | `Select-String "_categorize_reason" data_routes.py` → 3+ hits (def + 2 call sites) |
| 4 | Trade events reason filter uses category matching | `data_routes.py` line ~813: `reason_categories` variable, not `_apply_multi_select` |
| 5 | Trade events distinct has `if column == 'reason'` branch | `data_routes.py` line ~893: early return with category grouping |
| 6 | Frontend uses pipe delimiter | `data-explorer.tsx` line 291: `.join('|')` |

## Deployment Note

> [!CAUTION]
> Frontend and backend changes **must deploy atomically**. If only one side deploys, ALL multi-select filters will break across ALL tabs.
