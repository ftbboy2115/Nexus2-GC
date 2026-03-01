# Walkthrough: Batch Test PnL Divergence Resolution

**Date:** 2026-03-01  
**Commit:** 6506aaf

---

## Problem

$139K PnL divergence between Windows ($409K) and Linux/VPS ($271K) batch tests.

## Root Cause

`data/warrior_settings.json` was gitignored and machine-local. Each environment had different settings:

| Setting | Windows | VPS |
|---------|---------|-----|
| `max_shares_per_trade` | 10,000 | 40,000 |
| `entry_bar_timeframe` | 1min | 10s |
| `max_positions` | 20 | 3 |

## Resolution

Separated batch test settings from live settings:

1. **Created** `data/warrior_settings_batch.json` — committed, version-controlled (40K shares, 1min bars, 20 positions)
2. **Modified** `sim_context.py` — batch runner loads from batch file, not live settings
3. **Added** `GET /warrior/batch-settings` endpoint
4. **Added** batch comparison badges in SettingsCard.tsx
5. **Fixed** `.gitignore` — uses `/data/*` + negation to track batch file

## Verification

| Environment | P&L | Convergence |
|---|---|---|
| Local (Windows) | $437,558 | ✅ Baseline |
| VPS (Linux) | $435,454 | ✅ 0.5% variance |
| **Old divergence** | **$139,000 (34%)** | ❌ **Resolved** |

## Additional Findings

- **10s vs 1min bars for entry patterns:** 10s bars degrade PnL from $155K to $91K due to noise in pattern detection. Keep `entry_bar_timeframe: 1min`.
- **NAC scanners running on weekends:** Observed FMP rate limit calls on Sunday, consuming VPS resources during batch test (19 min vs 96s local). Separate investigation.

## Files Changed

- `data/warrior_settings_batch.json` [NEW]
- `nexus2/adapters/simulation/sim_context.py` [MODIFIED]
- `nexus2/api/routes/warrior_routes.py` [MODIFIED]
- `nexus2/frontend/src/components/warrior/SettingsCard.tsx` [MODIFIED]
- `nexus2/frontend/src/styles/Warrior.module.css` [MODIFIED]
- `.gitignore` [MODIFIED]
