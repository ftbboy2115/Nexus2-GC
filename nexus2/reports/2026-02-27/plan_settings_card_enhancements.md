# Settings Card Enhancements

Add Ross-size preset toggle, notes section, and editable Risk/Trade input to the Warrior Settings card.

## Proposed Changes

### Frontend

#### [MODIFY] [SettingsCard.tsx](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/frontend/src/components/warrior/SettingsCard.tsx)

**1. Ross-Size Toggle Button**

Add a toggle button (like the existing ORB/PMH toggles) that switches between two presets:

| Setting | Conservative (current) | Ross Size |
|---------|----------------------|-----------|
| `risk_per_trade` | Current value | $2,500 |
| `max_capital` | Current value | $100,000 |
| `max_shares_per_trade` | Current value | 10,000 |

- Button in the `entryModeToggles` row: `🐻 Conservative` / `🚀 Ross Size`
- Clicking it calls `updateConfig` for all three fields at once
- Visual indicator: green when Ross mode, orange when conservative
- The toggle detects which mode is active by checking if all three values match Ross-size values

**2. Make Risk/Trade an editable text input**

Replace the `<span>` display (lines 65) with an `<input type="number">` matching the pattern already used by Max Shares/Trade (lines 93-105) and Max Capital/Trade (lines 119-131).

- Min: $10, Max: $10,000
- +/- buttons increment by $25 (unchanged)

**3. Notes Section**

Add a collapsible notepad textarea following the MockMarketCard global notepad pattern:
- 📋 icon toggle in the card header (via CollapsibleCard `badge` prop)
- Textarea with Save button
- Reuse the existing `/warrior/mock-market/notes` API with `case_id=_settings`
- No backend changes needed — the notes API is generic and takes any `case_id`

---

## No Backend Changes Required

- Settings PATCH API already handles `risk_per_trade`, `max_capital`, `max_shares_per_trade`
- Notes API (`/warrior/mock-market/notes`) already supports arbitrary `case_id` values
- The Ross-size values come from `gc_quick_test.py` (verified: `$2,500 / $100,000 / 10,000`)

## Verification Plan

### Manual Verification
1. Start the dev server (`npm run dev` in `nexus2/frontend`)
2. Navigate to Warrior page → Settings card
3. Verify Risk/Trade now shows an editable number input (type `500`, confirm it updates)
4. Click the Ross Size toggle → confirm all three values snap to $2,500 / $100,000 / 10,000
5. Click toggle again → confirm values snap back to conservative defaults
6. Toggle notes icon → textarea appears, type text, click Save, reload page → notes persist
7. Verify existing functionality (ORB/PMH toggles, +/- buttons) still works
