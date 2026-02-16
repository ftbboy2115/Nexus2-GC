# Exit Logic Optimization Sprint — Final Report

**Date:** 2026-02-16  
**Risk per trade:** $250

---

## Summary

After testing 4 fixes across 29 test cases, **only Fix 1 (Partial-Then-Ride) improved P&L**. All other exit-side tweaks were neutral or harmful. The remaining P&L gap is entry-side (missing entries + no scaling), not exit-side.

---

## Results Table

| Config | P&L | Delta vs Baseline | Profitable | Capture % |
|--------|-----|-------------------|------------|-----------|
| **Baseline** | **$6,740** | — | 16/29 | 13.1% |
| **Fix 1: Partial-then-ride** | **$13,298** | **+$6,558 (+97%)** ✅ | **18/29** | **25.8%** |
| Fix 2: Proportional trail | $6,044 | -$696 (-10%) ❌ | 17/29 | 11.7% |
| Fix 1 + Fix 2 | $13,038 | +$6,298 (+93%) | 18/29 | 25.3% |
| Fix 1 + Fix 3 | $13,385 | +$6,645 (+99%) | 16/29 | 26.0% |
| Fix 1 + Fix 4a | $13,298 | +$6,558 (+97%) | 18/29 | 25.8% |
| Fix 1 + Fix 4a + 4b | $13,298 | +$6,558 (+97%) | 18/29 | 25.8% |
| Fix 1 + Fix 4 (all) | $11,103 | +$4,363 (+65%) ❌ | 18/29 | 21.5% |

---

## Fix Details

### ✅ Fix 1: Partial-Then-Ride (+97% P&L)
**KEEPER — enabled in production**

- Sells 50% at candle trail stop, switches remainder to home_run trailing
- Doubles P&L by capturing profit on first half + letting remainder ride
- Config: `enable_partial_then_ride = True`

### ❌ Fix 2: Price-Proportional Trail (-10%)
**REJECTED**

- Replaced fixed +15¢ trail activation with `max(15, entry_price × 3%)`
- Higher activation threshold delayed exits, stocks reversed before locking gains
- Config: `trail_activation_pct = 0.0`, `base_hit_profit_pct = 0.0` (disabled)

### ❌ Fix 3: Structural Profit Levels (+1% but -2 winners)
**REJECTED**

- Replaced flat +18¢ fallback with next $0.50 structural level
- Marginal P&L gain but targets too far on low-priced stocks → missed exits
- Config: `enable_structural_levels = False`

### ❌ Fix 4: Improved Home Run Trail (neutral to -16%)
**REJECTED — all three sub-fixes neutral or harmful**

| Sub-fix | What | Result |
|---------|------|--------|
| 4a: Trail-level stop | Replace breakeven with candle trail level after partial | **Neutral** — trail_level ≈ breakeven (partial fires at +15¢, trailing stop is ~entry) |
| 4b: Skip topping tail | Don't check topping tail for home_run positions | **Neutral** — topping tail never fires on these test cases |
| 4c: Candle-low trail | Replace 20%-from-high with 5-bar candle low trail | **-16% regression** — trail too tight on volatile small caps, causing premature exits |

Config: `enable_improved_home_run_trail = False`

---

## Key Insight: The Remaining Gap Is Entry-Side

At $2K-equivalent risk, Fix 1 captures **~26% of Ross's P&L**. The other 74% comes from:

### 1. Missing Entries (~$200K gap at Ross sizing)
Cases where the bot enters $0 or near-$0:
- HIND: $0 vs $55K (no pattern trigger)
- PAVM: $10 vs $44K (no pattern trigger)
- LRHC: $87 vs $31K (minimal entry)
- BNKK: $18 vs $15K (no pattern trigger)

### 2. Scaling Logic Exists But Never Fires (~$130K gap at Ross sizing)
Full scaling logic exists in `warrior_monitor_scale.py` (`check_scale_opportunity`, `execute_scale_in`) with config (`max_scale_count=2`, `scale_size_pct=50`), but NO scaling occurs in batch tests. Under investigation — likely not wired in sim or guards too strict.
- ROLR: $49K vs $85K (Ross added 2-3x)
- NPT: $14K vs $81K (Ross added multiple times)
- MLEC: -$299 vs $43K (Ross had different entry points)

### 3. Exit optimization is near ceiling
The 20%-from-high trail for home_run mode is actually adequate. The candle trail alternatives tested worse. The current exit logic extracts reasonable profit from the entries we DO take.

---

## DO NOT REVISIT

The following approaches have been empirically tested and **do not improve P&L**:

1. ~~Price-proportional trail activation~~ → delays exits
2. ~~Structural profit levels~~ → targets too far on cheap stocks
3. ~~Replacing breakeven stop after partial~~ → trail_level ≈ breakeven anyway
4. ~~Skipping topping tail for home_run~~ → never triggers on test cases
5. ~~Candle-low trail for home_run~~ → **actively harmful**, too tight

---

## Next Steps

Focus on **entry-side improvements**:
1. **Entry coverage** — Why doesn't the bot enter HIND, PAVM, BNKK, LRHC?
2. **Scaling/adds** — Implement add-on-strength logic for winners
3. **Re-entry quality** — Better re-entry gates after profitable exits
