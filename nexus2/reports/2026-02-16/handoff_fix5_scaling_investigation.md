# Fix 5 Scaling Regression: Multi-Agent Investigation Handoff

**Date:** 2026-02-16  
**Regression:** $13,298 → $9,796 (-26%, -$3,502) when `enable_improved_scaling=True`  
**Previous Hypothesis (DISPROVEN):** Scaling interferes with Fix 1 partial-then-ride

---

## Verified Facts (Code-Evidenced)

### Fact 1: `partial_taken=False` on ALL 23 scale events
**File:** `data/scaling_trace_*.log` (8 trace files captured via file handler)  
**Evidence:** Every `[Warrior Scale TRACE] SCALE EXECUTED` event shows `partial_taken=False`  
**Conclusion:** Scaling fires BEFORE any partial exit. Fix 1 interaction is NOT the regression cause.

### Fact 2: `move_stop_to_breakeven_after_scale` defaults to `False`
**File:** [warrior_types.py:105](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_types.py#L105)  
**Code:** `move_stop_to_breakeven_after_scale: bool = False  # Keep technical stop after scale (Ross Cameron)`  
**Note:** [warrior_types.py:71](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_types.py#L71) — `# NOTE: move_stop_to_breakeven REMOVED - this is KK methodology, not Ross Cameron`  
**Conclusion:** Stop NOT moving is BY DESIGN. This is intentional, not a bug.

### Fact 3: Re-entries increment `scale_count`
**File:** [warrior_monitor.py:329](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor.py#L329)  
**Code:** `existing_position.scale_count += 1` in `consolidate_position()`  
**Evidence from trace:** VERO shows `scale_count=1` after re-entry WITHOUT any `SCALE EXECUTED` event  
**Conclusion:** Re-entries consume scale slots, potentially blocking legitimate scaling later.

### Fact 4: Ross has a pullback exception  
**File:** [warrior.md:72](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/.agent/strategies/warrior.md#L72)  
**Quote:** "Ross adds on strength, never on weakness **(with one exception: dip-buying the first pullback after an initial move)**."  
**Conclusion:** Pullback scaling is NOT categorically anti-methodology. But the current implementation may be too aggressive (scaling 20% below entry on any pullback, not just the "first pullback after initial move").

### Fact 5: Scale prices are consistently below entry
**Evidence (trace logs):**

| Symbol | Entry | Scale #1 | Scale #2 | % Below |
|--------|-------|----------|----------|---------|
| TNMG | $3.43 | $2.75 | $2.73 | -19.8% |
| FLYE | $7.11 | $5.66 | $5.54 | -20.4% |
| ROLR | $16.07 | $14.14 | — | -12.0% |
| GWAV | $5.68 | $5.20 | $5.18 | -8.5% |
| BATL | $3.22 | $3.11 | $3.10 | -3.4% |

### Fact 6: 5 symbols scale while in `home_run` mode
**Evidence:** TNMG, GWAV, VELO, PRFX, BATL all show `exit_mode_override=home_run` at time of SCALE EXECUTED.

---

## Open Questions (Need Investigation)

### Q1: What is the per-case P&L impact of scaling?
We know total regression is -$3,502. But we DON'T know which specific cases got worse vs. better.
- **Needed:** Per-case comparison of P&L with `enable_improved_scaling=True` vs `False`
- **Starting point:** Run batch with each config, diff the results per case_id

### Q2: Is the pullback zone threshold (50%) too deep?
The current threshold is `entry - 0.5 * (entry - support)`. For stocks with wide support (entry=$3.43, support=$2.15 = $1.28 range), the zone extends to entry - $0.64 = $2.79, allowing scales nearly 20% below entry.
- **Needed:** Analysis of which pullback depths produce positive vs negative outcomes
- **Starting point:** Cross-reference scale price vs. eventual exit price for each scaled trade

### Q3: Should scaling be blocked during `home_run` mode?
5 symbols scaled while in home_run. Were those scales positive or negative?
- **Needed:** Isolate P&L contribution of home_run scales vs. base_hit scales
- **Starting point:** Filter trace data by exit_mode at time of scale

### Q4: Is the doubling (2x position) too aggressive?
11 of 12 scaled symbols doubled their position (2 scales of 50%).
- **Needed:** Would 1 scale produce a better outcome? Or smaller add sizes?
- **Starting point:** Check `scale_shares_ratio` setting, test different values

### Q5: Does scale_count leak from re-entries affect scaling?
VERO has `scale_count=1` from a re-entry consolidation, leaving only 1 scale slot for the scaling module.
- **Needed:** Count how many positions have `scale_count > 0` from re-entries before scaling module runs
- **Starting point:** Add trace logging to `consolidate_position` path

### Q6: Exact regression source — is it ALL from scaling, or partially from other interactions?
VERO regressed despite NOT scaling through the scaling module. Other changes in the `enable_improved_scaling` code path (cooldown bypass, pullback zone guard) may have secondary effects.
- **Needed:** Deep comparison of VERO's trade sequence with scaling on vs off
- **Starting point:** Run VERO in isolation with max logging

---

## Available Trace Data

8 log files in `data/scaling_trace_*.log`:

| File | Lines | Contains |
|------|-------|----------|
| scaling_trace_18720.log | 28 | Small case (few bars) |
| scaling_trace_54632.log | 734 | ~3 cases |
| scaling_trace_55712.log | 186 | ~1 case |
| scaling_trace_57952.log | 256 | ~1-2 cases |
| scaling_trace_62604.log | 1034 | ~4 cases |
| scaling_trace_63972.log | 1108 | ~4 cases |
| scaling_trace_66024.log | 1192 | ~5 cases |
| scaling_trace_66208.log | 271 | ~1-2 cases |

25 symbols reached CHECKPOINT (all trades with active positions).  
12 symbols had SCALE EXECUTED events.  

---

## Agent Assignments

### Agent 1: Backend Planner — Per-Case P&L Differential
**Goal:** Answer Q1 (which cases regressed) and Q2 (pullback depth analysis)
- Run batch with `enable_improved_scaling=False`, capture per-case results
- Diff against the Fix 5 results ($9,796 run) 
- Produce a table showing per-case delta
- For scaled cases, calculate the scale P&L contribution if possible

### Agent 2: Code Auditor — Scaling Module Deep Audit
**Goal:** Answer Q3 (home_run scaling), Q4 (position sizing), Q5 (scale_count leak), Q6 (VERO mystery)
- Audit `check_scale_opportunity` guards end-to-end
- Trace the `consolidate_position` path for scale_count leak
- Investigate VERO's specific regression mechanism
- Verify whether cooldown bypass has any secondary effects beyond allowing scaling
