# Status: Fix 2 — Price-Proportional Trail Activation

**Date:** 2026-02-16  
**Agent:** Backend Specialist  
**Spec:** [spec_proportional_trail.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-02-16/spec_proportional_trail.md)

---

## Result: ✅ All 6 Changes Implemented

### Changes Made

| # | File | Change | Status |
|---|------|--------|--------|
| 1 | `warrior_types.py:129` | Added `trail_activation_pct: float = 3.0` | ✅ |
| 2 | `warrior_types.py:123` | Added `base_hit_profit_pct: float = 3.5` | ✅ |
| 3 | `warrior_monitor_exit.py:708-714` | Proportional trail activation: `max(15¢, entry * 3%)` | ✅ |
| 4 | `warrior_monitor_exit.py:824-836` | Proportional flat fallback: `max(18¢, entry * 3.5%)` + log update | ✅ |
| 5 | `warrior_monitor_settings.py:121-122` | `get_monitor_settings_dict` — both fields added | ✅ |
| 6 | `warrior_monitor_settings.py:96-99` | `apply_monitor_settings` — both fields added | ✅ |

### Key Design Decisions

- **`getattr` defensive access** in exit logic — protects against older settings objects loaded from pre-existing JSON
- **`max(floor, proportional)`** — guarantees no stock gets a *lower* threshold than the fixed floor
- **A/B toggle:** Setting `trail_activation_pct = 0.0` or `base_hit_profit_pct = 0.0` reverts to fixed behavior

### Impact by Price

| Entry Price | Old Trail | New Trail | Old Fallback | New Fallback |
|-------------|-----------|-----------|--------------|--------------|
| $3.00 | 15¢ | 15¢ (unchanged) | 18¢ | 18¢ (unchanged) |
| $5.00 | 15¢ | 15¢ (unchanged) | 18¢ | 18¢ (unchanged) |
| $10.00 | 15¢ | **30¢** | 18¢ | **35¢** |
| $15.00 | 15¢ | **45¢** | 18¢ | **52¢** |
| $33.81 | 15¢ | **101¢** | 18¢ | **118¢** |

---

## Verification

```
Import check:  ✅ OK
Config check:  ✅ trail_activation_pct=3.0, base_hit_profit_pct=3.5
Persistence:   ✅ True True
```

---

## Next Step

Run batch test across all 38 cases to measure P&L delta vs baseline.
