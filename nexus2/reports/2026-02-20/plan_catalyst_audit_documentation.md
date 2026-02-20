# Catalyst Audit Gap Documentation

Document the expected behavior where earnings-calendar-resolved symbols do not appear in Catalyst Audits or AI Comparison tabs.

## Background

SPAI passed the Warrior scanner with `catalyst='earnings'` via the `has_recent_earnings()` fallback, but did not appear in the Catalyst Audits or AI Comparison tabs. Investigation confirmed this is **expected behavior**: the earnings calendar shortcut sets `ctx.has_catalyst = True` early, causing the multi-model AI pipeline (which writes to `telemetry.db catalyst_audits` and `ai_comparisons` tables) to be skipped.

Three documentation features will make this self-evident to the user.

## Proposed Changes

### Feature 1: Tab Tooltips (Frontend)

Update the existing tab tooltip text for Catalyst Audits and AI Comparisons to explain which stocks appear and which don't.

#### [MODIFY] [data-explorer.tsx](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/frontend/src/pages/data-explorer.tsx)

**Lines 814-815** — Update tab tooltip strings:

```diff
-{ id: 'catalyst-audits', label: 'Catalyst Audits', tooltip: 'Regex-based headline classification (Tier 0.9/0.5/0.0). Shows which headlines matched catalyst patterns like earnings, FDA approvals, etc.' },
-{ id: 'ai-comparisons', label: 'AI Comparisons', tooltip: 'Side-by-side comparison of Regex vs Flash-Lite vs Pro catalyst classification.' },
+{ id: 'catalyst-audits', label: 'Catalyst Audits', tooltip: 'Regex-based headline classification (Tier 0.9/0.5/0.0). Shows headlines evaluated by the multi-model AI pipeline. Note: Symbols resolved via earnings calendar bypass this pipeline and won\'t appear here.' },
+{ id: 'ai-comparisons', label: 'AI Comparisons', tooltip: 'Side-by-side comparison of Regex vs Flash-Lite vs Pro catalyst classification. Only symbols with ambiguous headlines trigger AI validation. Earnings-calendar symbols are resolved without AI and won\'t appear here.' },
```

---

### Feature 2: Persistent Info Banner (Frontend)

Show an always-visible info banner below the tab bar when the Catalyst Audits or AI Comparisons tab is active. This is more discoverable than a contextual empty state (which would never trigger since unrecorded symbols can't be selected from the filter dropdown).

#### [MODIFY] [data-explorer.tsx](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/frontend/src/pages/data-explorer.tsx)

**After the tab bar (after line ~831)** — Add a conditional info banner:

```tsx
{/* Info banner for AI pipeline tabs */}
{(activeTab === 'catalyst-audits' || activeTab === 'ai-comparisons') && (
    <div style={{
        padding: '6px 16px',
        background: '#1a2332',
        borderLeft: '3px solid #4dabf7',
        fontSize: '12px',
        color: '#8899aa',
        margin: '0 0 8px 0',
    }}>
        ℹ️ Only symbols evaluated by the multi-model AI pipeline appear here. Earnings-calendar matches are visible in Warrior Scans.
    </div>
)}
```

---

### Feature 3: Catalyst Resolution Indicator (Backend + Frontend)

Add a `catalyst_source` column to the `WarriorScanResult` table so the Warrior Scans tab shows HOW the catalyst was resolved. Frontend renders a 📅 icon for calendar-resolved entries.

#### [MODIFY] [telemetry_db.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/db/telemetry_db.py)

Add `catalyst_source` column to `WarriorScanResult`:

```diff
     catalyst_type = Column(String(50), nullable=True)
+    catalyst_source = Column(String(20), nullable=True)  # calendar, regex, ai, former_runner, or None
```

Update `to_dict()` to include it:

```diff
             "catalyst_type": self.catalyst_type,
+            "catalyst_source": self.catalyst_source,
```

Add migration entry in `_migrate_telemetry_columns()`:

```diff
         expected_columns = {
             "warrior_scan_results": {
                 "price": "REAL",
                 "country": "VARCHAR(10)",
                 "ema_200": "REAL",
                 "room_to_ema_pct": "REAL",
                 "is_etb": "VARCHAR(5)",
                 "name": "VARCHAR(100)",
+                "catalyst_source": "VARCHAR(20)",
             }
         }
```

---

#### [MODIFY] [warrior_scanner_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py)

Add `catalyst_source` field to `EvaluationContext` (around line 430):

```diff
     catalyst_type: Optional[str] = None
+    catalyst_source: Optional[str] = None  # "calendar", "regex", "ai", "former_runner"
```

Set it in `_evaluate_catalyst_pillar`:
- When `has_positive_catalyst` matches: `ctx.catalyst_source = "regex"`
- When `has_recent_earnings` matches: `ctx.catalyst_source = "calendar"`
- When former runner matches: `ctx.catalyst_source = "former_runner"`

Set it in `_run_multi_model_catalyst_validation`:
- When AI validation succeeds: `ctx.catalyst_source = "ai"`

Pass it in `_write_scan_result_to_db`:

```diff
                     catalyst_type=ctx.catalyst_type if ctx else None,
+                    catalyst_source=ctx.catalyst_source if ctx else None,
```

---

#### [MODIFY] [data_routes.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/data_routes.py)

In the Warrior Scan History response transformation (around line 418), rename `catalyst_source` on the response for display:

```python
# Existing line
if "catalyst_type" in entry:
    entry["catalyst"] = entry.pop("catalyst_type")
# Add:
# catalyst_source passes through as-is (no rename needed)
```

No code change needed for `catalyst_source` — it will pass through from `to_dict()` automatically.

---

#### [MODIFY] [data-explorer.tsx](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/frontend/src/pages/data-explorer.tsx)

Add tooltip for new column (line ~253):

```diff
     'catalyst': 'Catalyst type: earnings, fda, contract, etc. Includes dilution filter',
+    'catalyst_source': 'How catalyst was resolved: calendar (earnings date), regex (headline match), ai (AI validation), former_runner',
```

Add to preferred column order (line 259):

```diff
-    'warrior-scans': ['timestamp', 'symbol', 'result', 'reason', 'country', 'float', 'rvol', 'price', 'gap_pct', 'catalyst', 'ema_200', 'room_to_ema_pct', 'is_etb', 'score', 'name'],
+    'warrior-scans': ['timestamp', 'symbol', 'result', 'reason', 'country', 'float', 'rvol', 'price', 'gap_pct', 'catalyst', 'catalyst_source', 'ema_200', 'room_to_ema_pct', 'is_etb', 'score', 'name'],
```

Add special cell rendering: show a 📅 icon for `calendar`, 🤖 for `ai`, 📰 for `regex`, 🔄 for `former_runner` (around line 1315 in the cell rendering block):

```tsx
) : col === 'catalyst_source' && rawVal ? (
    <span title={`Resolved via: ${rawVal}`}>
        {rawVal === 'calendar' ? '📅' : rawVal === 'ai' ? '🤖' : rawVal === 'regex' ? '📰' : rawVal === 'former_runner' ? '🔄' : ''} {displayVal}
    </span>
```

---

## Multi-Agent Assignment

| Feature | Agent | Scope |
|---------|-------|-------|
| #1 Tab Tooltips | **Frontend** | 2 string changes in `data-explorer.tsx` |
| #2 Empty State | **Frontend** | Add conditional hint below "No data found" in `data-explorer.tsx` |
| #3 Backend | **Backend** | Add `catalyst_source` to `EvaluationContext`, `WarriorScanResult`, `_write_scan_result_to_db`, and set it in catalyst evaluation methods |
| #3 Frontend | **Frontend** | Add column tooltip, preferred order, and emoji cell rendering for `catalyst_source` |

> [!TIP]
> Features #1 and #2 are frontend-only (no backend needed). Feature #3 is a parallel backend + frontend change. All 3 frontend changes can be done by a single frontend agent.

---

## Verification Plan

### Automated Tests

1. **Backend unit test** — run existing telemetry DB test to ensure no regression:
```powershell
cd "c:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus"
python -m pytest nexus2/tests/unit/db/test_telemetry_db.py -x -q
```

2. **Scanner test** — run existing scanner validation tests:
```powershell
python -m pytest nexus2/tests/test_scanner_validation.py -x -q
```

3. **Full test suite** — ensure no regressions:
```powershell
python -m pytest nexus2/tests/ -x -q
```

### Manual Verification

1. **Tab Tooltips**: Hover over the "Catalyst Audits" and "AI Comparisons" tab buttons in the Data Explorer. Confirm the tooltips now mention the earnings calendar bypass.

2. **Empty State**: On the Catalyst Audits tab, click on a symbol that was resolved via earnings calendar (e.g., filter by symbol `SPAI`). Confirm the empty state shows the 💡 hint message about calendar bypass.

3. **`catalyst_source` Column**: After the next scan cycle, check the Warrior Scans tab. Confirm the new `catalyst_source` column appears with icons (📅 for calendar, 📰 for regex, etc.). Filter by `catalyst_source` to verify it works as a filter.
