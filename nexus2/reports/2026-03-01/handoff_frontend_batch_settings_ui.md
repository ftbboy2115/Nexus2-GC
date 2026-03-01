# Handoff: Batch Settings Comparison UI

**Agent:** Frontend Specialist  
**Priority:** P2  
**Date:** 2026-03-01

---

## Context

We've separated batch test settings from live settings. The committed file `data/warrior_settings_batch.json` contains the canonical batch baseline. The live engine/GUI uses `data/warrior_settings.json` which may differ.

The user wants the Settings card to show which settings differ from the batch baseline, so they can see at a glance when their GUI settings diverge and know what to set them back to.

---

## Backend Dependency

A new endpoint `GET /warrior/batch-settings` is being added by the backend specialist. It returns the batch settings JSON (same shape as `GET /warrior/scanner/settings` and `/monitor/settings`).

---

## UI Changes

### Settings Card Enhancement

When any setting differs from the batch baseline value, show the batch value as a subtle reference. Only show differences — matching values should have no extra indicator.

**Visual example:**
```
Risk/Trade ($):        [2500]
Max Shares/Trade:      [10000]  📊 Batch: 40,000
Max Positions:         [3]      📊 Batch: 20
Entry Timeframe:       [10s]    📊 Batch: 1min
Max Capital/Trade ($): [100000]
```

### Implementation approach:
1. Fetch `GET /warrior/batch-settings` once on mount (batch settings are static)
2. Compare each setting against the batch value
3. When a setting value changes (user edits), re-compare against the batch baseline
4. Show a small badge/label next to settings that differ: `📊 Batch: {value}`
5. Use a muted/secondary color so it doesn't overpower the main controls

### Settings to compare:
- `risk_per_trade` (from engine settings)
- `max_shares_per_trade` (from engine settings)  
- `max_positions` (from engine settings)
- `max_capital` / `max_value_per_trade` (from engine settings)
- `entry_bar_timeframe` (from engine settings)
- `max_candidates` (from engine settings)

---

## Files to modify

- `nexus2/frontend/src/components/warrior/SettingsCard.tsx` (or equivalent)
- Add a new API call for batch settings

---

## Deliverable

Frontend status report at `nexus2/reports/2026-03-01/frontend_status_batch_settings_ui.md`
