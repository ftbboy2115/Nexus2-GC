# Batch Settings Comparison UI

Add batch baseline comparison badges to the Settings card so the user can see at a glance which settings diverge from the committed batch test baseline.

## Proposed Changes

### Frontend — SettingsCard

#### [MODIFY] [SettingsCard.tsx](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/frontend/src/components/warrior/SettingsCard.tsx)

1. **Fetch batch settings on mount** — `useEffect` calls `GET /warrior/batch-settings` once. Store result in `batchSettings` state (same `WarriorConfig` shape). Gracefully handle 404/failure (endpoint may not exist yet).

2. **Comparison logic** — A helper function `getBatchDiff(key)` compares `config[key]` vs `batchSettings[key]`. Returns the batch value only when they differ, `null` otherwise.

3. **Inline batch badge** — For each setting item that differs, render a small `<span>` next to the control: `📊 Batch: {formattedValue}`. Uses muted amber/blue color, `0.75rem` font.

4. **Settings to compare** (6 total):
   - `risk_per_trade` — format as `$X,XXX`
   - `max_shares_per_trade` — format as `X,XXX`
   - `max_positions` — format as number
   - `max_capital` — format as `$X,XXX`
   - `entry_bar_timeframe` — format as string (`1min` / `10s`)
   - `max_candidates` — format as number

5. **No changes to `warrior.tsx`** — All logic is self-contained within `SettingsCard.tsx`.

### CSS

#### [MODIFY] [Warrior.module.css](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/frontend/src/styles/Warrior.module.css)

Add a `.batchBadge` class for the batch comparison label:
- Muted color (`#e5a54b` amber or `#4dabf7` blue)
- Small font (`0.72rem`)
- Slight left margin
- Optional subtle background pill

## Verification Plan

### Manual Verification

Since there are no existing frontend tests, verification will be manual:

1. **Start the dev server** (`cd nexus2/frontend; npm run dev`)
2. **Open browser** to `http://localhost:3000/warrior`
3. **Check Settings card**:
   - If backend endpoint is available: Settings that differ from batch baseline show `📊 Batch: X` badges
   - If backend endpoint is NOT available (404): Card renders normally with no badges and no errors in console
4. **Modify a setting** (e.g., change Max Positions) — the badge should appear/disappear dynamically as the value matches or diverges from batch

> [!NOTE]
> The backend endpoint `GET /warrior/batch-settings` is being added by a separate backend agent. If not available yet, the UI should degrade gracefully (no badges shown, no console errors).
