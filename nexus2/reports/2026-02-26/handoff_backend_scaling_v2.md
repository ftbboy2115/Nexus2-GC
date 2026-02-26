# Handoff: Backend Specialist — Scaling v2 Implementation

**Date:** 2026-02-26  
**From:** Coordinator  
**To:** Backend Specialist (`agent-backend-specialist.md`)  
**Reference Spec:** `nexus2/reports/2026-02-26/spec_scaling_v2_code_research.md`  
**Research Doc:** `nexus2/reports/2026-02-16/research_ross_add_methodology.md`

---

## Task Summary

Replace the "accidental" scaling behavior with Ross Cameron's level-break methodology. The current scaling has a broken pullback zone check that always returns True, producing one add per trade. Replace with proper structural-level scaling ($X.00, $X.50 breaks).

**All changes must be A/B testable** via settings flags so we can compare old vs new with batch tests.

---

## Decisions (from Clay)

| Question | Decision |
|----------|----------|
| MACD gate fail mode | **Fail-closed** — no MACD data = no scaling. Log WARNING. |
| Take-profit→add-back cycle | **NOT this phase** — implement level-break adds only. Follow-up later. |
| `min_rvol_for_scale` | **Leave as-is** — don't wire, don't remove. Revisit later. |
| Structural level exits | **Enable `enable_structural_levels=True`** as default. A/B testable. |

---

## Implementation Checklist

Refer to the spec (Section C, Change Points 1-7) for exact file paths, line numbers, and code snippets.

### warrior_types.py — Settings & Position Fields

- [ ] Add to `WarriorMonitorSettings` (alongside existing scaling fields, ~line 118):
  ```python
  enable_level_break_scaling: bool = True   # New level-break logic (vs accidental)
  level_break_increment: float = 0.50       # $0.50 = whole + half dollar levels
  level_break_min_distance_cents: int = 10  # Skip levels closer than 10¢
  level_break_macd_gate: bool = True        # MACD negative blocks scaling
  level_break_macd_tolerance: float = -0.02 # MACD histogram tolerance
  ```
- [ ] Change `enable_structural_levels` default to `True` (if it exists, else add it)
- [ ] Add to `WarriorPosition` (~line 216):
  ```python
  last_level_break_price: Optional[Decimal] = None
  ```

### warrior_monitor_scale.py — Core Logic Replacement

- [ ] **Modify `check_scale_opportunity()`** (lines 31-156):
  - When `enable_level_break_scaling=True`: use level-break logic
  - When `False`: keep existing accidental behavior (for A/B testing)
  - Level-break logic:
    1. Get reference price = `position.last_level_break_price or position.entry_price`
    2. Compute next level via `_compute_structural_target(reference_price, increment, min_distance)`
    3. If `current_price >= next_level` → level broken → proceed to MACD check
    4. MACD gate (fail-closed): fetch candles, get snapshot, check histogram >= tolerance
    5. If MACD passes → return scale signal with `next_level` as the trigger price
    6. If MACD check fails or no data → return `None` + log WARNING
  - Use `check_momentum_add()` (same file, lines 164-254) as template

- [ ] **Import `_compute_structural_target`** from `warrior_monitor_exit.py` (Option A from spec — no circular dep risk)

- [ ] **After successful scale execution**: set `position.last_level_break_price = next_level` in `execute_scale_in()` so the next level is computed from the new reference

### warrior_monitor_exit.py — Structural Level Exits

- [ ] Ensure `enable_structural_levels` works when toggled True
- [ ] No code change needed if it's already implemented at lines 915-928 — just verify the setting default change activates it

### warrior_monitor.py — Wiring

- [ ] Verify existing wiring at lines 577-607 routes correctly
- [ ] The function name `check_scale_opportunity()` is unchanged, so no call-site changes needed
- [ ] The internal routing (level-break vs accidental) happens inside the function via the settings flag

### Settings Persistence

- [ ] Add new fields to `warrior_monitor_settings.py` serialization/deserialization (follow existing pattern for how `enable_scaling`, `max_scale_count` etc. are saved/loaded)

---

## What NOT to Do

- ❌ Do NOT implement take-profit→add-back cycle (Phase 3)
- ❌ Do NOT wire `min_rvol_for_scale` (leave dead)
- ❌ Do NOT remove any existing scaling fields (keep for A/B)
- ❌ Do NOT add on weakness / average down (Ross never does this)
- ❌ Do NOT change momentum adds system (independent, leave untouched)

---

## A/B Testing Plan

After implementation, we need these batch test comparisons:

| Test | Config Override | Expected |
|------|----------------|----------|
| Baseline (accidental) | `enable_level_break_scaling=False` | ~$359K (current) |
| Level-break only | `enable_level_break_scaling=True, enable_structural_levels=False` | ? |
| Level-break + structural exits | `enable_level_break_scaling=True, enable_structural_levels=True` | ? |
| MACD gate off | `level_break_macd_gate=False` | ? (compare vs gate on) |

Use `gc_param_sweep.py` or batch API with `config_overrides` for these tests.

---

## Key Test Cases to Watch

| Case | Why | What to Check |
|------|-----|---------------|
| **GRI** | THE level-break case. Ross added every $0.50/$1.00 | Multiple scales at $6, $6.50, $7, $7.50+ |
| **ROLR** | Major P&L contributor ($46K) | Level breaks should fire, MACD gate should block late adds |
| **BATL** | MACD went negative | MACD gate should prevent scaling |
| **NPT** | Already close to Ross ($68K vs $81K) | Should not regress |

---

## Testable Claims (for validator)

After implementation, provide these claims with code evidence:

1. `enable_level_break_scaling` field exists in `WarriorMonitorSettings`
2. `last_level_break_price` field exists in `WarriorPosition`
3. `check_scale_opportunity()` checks `enable_level_break_scaling` to route logic
4. MACD gate is called inside level-break scaling path
5. `_compute_structural_target` is imported from `warrior_monitor_exit`
6. `position.last_level_break_price` is set after successful scale-in
7. `enable_structural_levels` defaults to `True`
8. All existing tests pass (`pytest nexus2/tests/ -x -q`)

---

## Output

Write your status report to: `nexus2/reports/2026-02-26/backend_status_scaling_v2.md`
