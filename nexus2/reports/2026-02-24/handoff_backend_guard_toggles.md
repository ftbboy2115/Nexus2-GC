# Handoff: Make Guard Fixes API-Toggleable

**Date:** 2026-02-24
**From:** Coordinator
**To:** Backend Specialist
**Priority:** P1 — guard fixes caused -$5K regression, need to isolate via param sweep

---

## Context

Three guard tuning fixes were applied simultaneously but caused a -$4,971 regression ($161K → $156K). We need to isolate which fix(es) caused it by making all three API-toggleable so GC can sweep combinations at runtime without code changes.

**Current state of each fix:**

| Fix | Current Default | What It Does | API-Toggleable? |
|-----|----------------|--------------|----------------|
| `max_reentry_count` = 5 | 5 (was 3) | More re-entries allowed | ✅ Already via `/warrior/monitor/settings` |
| Profit-check removed | Code deleted | Was blocking adds when >25% gain | ❌ Code gone |
| `macd_histogram_tolerance` = -0.02 | -0.02 | Allows slightly negative MACD | ❌ In `WarriorEngineConfig`, no API |

---

## Tasks

### Task 1: Re-add profit-check guard behind a toggle

The 25% profit-check guard was deleted from `warrior_entry_guards.py` (lines 257-268). Re-add the code, but gated behind a new setting:

**Add to `WarriorMonitorSettings` in `warrior_types.py`:**
```python
enable_profit_check_guard: bool = False  # Block new entries when position >25% gain (not Ross methodology)
```

**In `warrior_entry_guards.py` `_check_position_guards()`, re-add the check gated on this setting:**
```python
if engine.monitor.settings.enable_profit_check_guard:
    unrealized_pnl_pct = ((entry_price - pos.entry_price) / pos.entry_price) * 100
    pnl_above_threshold = unrealized_pnl_pct > 25
    if price_past_target or pnl_above_threshold:
        return False, "BLOCKING - position already past target. Take profit first."
```

Default `False` = current behavior (guard disabled). `True` = old behavior (guard enabled).

### Task 2: Expose `macd_histogram_tolerance` via API

`macd_histogram_tolerance` is currently in `WarriorEngineConfig` (`warrior_engine_types.py:117`). It needs to be reachable via an API endpoint so GC can change it at runtime.

**Option A (preferred):** Add `macd_histogram_tolerance` to the existing engine settings GET/PUT endpoints. Check if there's already a `/warrior/engine/settings` or similar route in `warrior_routes.py`.

**Option B:** Move `macd_histogram_tolerance` to `WarriorMonitorSettings` (since it's checked during entry guards, which are called from the engine). Then it's automatically available via the existing `/warrior/monitor/settings` endpoint.

**Option C:** Simply add it as an additional field to `WarriorMonitorSettings` that gets copied to the engine config on update. This is the least invasive approach.

Pick whichever is cleanest. The key requirement: GC must be able to change `macd_histogram_tolerance` via a PUT endpoint.

### Task 3: Wire both new toggles to API

Add `enable_profit_check_guard` and `macd_histogram_tolerance` (if moved) to:
- Request model (for PUT)
- GET response
- PUT handler

Follow the same pattern used for `enable_momentum_adds` fields.

---

## Important Notes

- Default values must preserve CURRENT behavior (profit-check OFF, MACD tolerance -0.02)
- Setting `macd_histogram_tolerance = 0` should effectively restore original binary MACD blocking
- Setting `enable_profit_check_guard = True` should restore old 25% gain guard
- Do NOT change `max_reentry_count` — it's already API-toggleable

---

## Verification

1. `pytest nexus2/tests/ -x -q` passes
2. Default batch run produces same P&L as current ($156,145)
3. Confirm both fields appear in GET `/warrior/monitor/settings` (or engine equivalent)

Write status to: `nexus2/reports/2026-02-24/backend_status_guard_toggles.md`
