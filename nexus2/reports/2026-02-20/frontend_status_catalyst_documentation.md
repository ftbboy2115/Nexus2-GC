# Frontend Status: Catalyst Audit Documentation UI

**Date:** 2026-02-20
**Agent:** Frontend Specialist
**File Modified:** `nexus2/frontend/src/pages/data-explorer.tsx`

## Changes Implemented

### Feature 1: Tab Tooltips
- **catalyst-audits tooltip** — Appended: "Note: Symbols resolved via earnings calendar bypass this pipeline and won't appear here."
- **ai-comparisons tooltip** — Appended: "Only symbols with ambiguous headlines trigger AI validation. Earnings-calendar symbols are resolved without AI and won't appear here."

### Feature 2: Info Banner
- Added a styled info banner (`ℹ️ Only symbols evaluated by the multi-model AI pipeline appear here...`) that renders conditionally when `activeTab === 'catalyst-audits'` or `activeTab === 'ai-comparisons'`.
- Positioned between tabs bar and filters/pagination controls.

### Feature 3: `catalyst_source` Column
- **COLUMN_TOOLTIPS**: Added `'catalyst_source': 'How catalyst was resolved: calendar (earnings date), regex (headline match), ai (AI validation), former_runner'`
- **PREFERRED_COLUMN_ORDER**: Inserted `'catalyst_source'` after `'catalyst'` in `warrior-scans` array
- **Cell rendering**: Added emoji rendering before the country handler:
  - 📅 = calendar, 🤖 = ai, 📰 = regex, 🔄 = former_runner
  - Hover tooltip: `Resolved via: {value}`

## Verification
- All changes are in a single file (`data-explorer.tsx`)
- No new dependencies introduced
- No backend changes required (column data comes from existing `catalyst_source` field in scan results)
