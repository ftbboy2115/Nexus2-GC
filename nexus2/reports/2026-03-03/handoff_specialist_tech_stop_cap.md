# Handoff: Technical Stop Cap Param Sweep

**Agent:** Backend Specialist  
**Date:** 2026-03-03  
**Baseline:** 39 cases, $355,039, 79.5% capture

---

## Bug (Validated, Confirmed)

The `max_stop_pct` cap in `calculate_stop_price()` is bypassed by the `technical_stop` path in `_create_new_position()`. Raw `calculated_candle_low` flows uncapped through `support_level → technical_stop → current_stop`.

**MNTS example:** Entry $8.73, consolidation low $6.02, stop set at $5.97 (32% from entry). The 10% cap only applied to `mental_stop`, not `technical_stop`. This caused a -$15,503 bag-hold to EOD.

**Validation:** All 4 claims verified — see `nexus2/reports/2026-03-02/validation_mnts_stop_failure.md`

## Task

Apply the cap in `_create_new_position` (warrior_monitor.py ~line 420) and sweep cap values to find the optimal threshold.

### Implementation

Add cap logic after `technical_stop` is calculated:

```python
# warrior_monitor.py, after line 420
if support_level and s.use_technical_stop:
    technical_stop = support_level - s.technical_stop_buffer_cents / 100
    
    # Cap technical stop to max distance
    max_pct = Decimal(str(CAP_VALUE))  # <- SWEEP THIS
    stop_distance_pct = (entry_price - technical_stop) / entry_price if entry_price > 0 else Decimal("0")
    if stop_distance_pct > max_pct:
        original = technical_stop
        technical_stop = (entry_price * (1 - max_pct)).quantize(Decimal("0.01"))
        logger.warning(f"[Warrior] {symbol}: TECH STOP CAPPED ${original:.2f} → ${technical_stop:.2f}")
```

### Param Sweep

Test each value, restart server between, run `python scripts/gc_quick_test.py --all --diff`:

| Cap Value | Expected Impact |
|-----------|----------------|
| 10% | Already tested: MNTS +$12K but -$54.7K net (too tight) |
| 15% | Should catch MNTS (32%) without hitting 10-15% range cases |
| 20% | Conservative — only catches extreme outliers |
| 25% | Very conservative — catches only MNTS-level extremes |

Record results in a table: cap value, improved count, regressed count, net change, and per-case breakdown.

### Important

- Make `max_stop_pct` a setting on `WarriorMonitorSettings` (not hardcoded) so it's tunable via API
- Reference `warrior_engine_types.py:92` for the existing 10% default
- If NO cap value is net positive, report findings and leave the cap disabled

### Reference

- Planner report: `nexus2/reports/2026-03-02/research_mnts_stop_failure.md`
- Validation: `nexus2/reports/2026-03-02/validation_mnts_stop_failure.md`

Write results to: `nexus2/reports/2026-03-03/backend_status_tech_stop_cap_sweep.md`
