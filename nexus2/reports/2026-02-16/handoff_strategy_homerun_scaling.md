# Handoff: Strategy Expert — Home Run Riding & Scaling Research

**Date:** 2026-02-16  
**From:** Coordinator  
**To:** Strategy Expert (`@agent-strategy-expert.md`)

---

## Context

Warrior bot captures only **13% of Ross Cameron's P&L** in batch testing ($54K vs $412K at $2K risk).  
The **#1 gap** is **home run riding** — exiting too early on big winners.

**Case Study:** NPT made +$14K vs Ross's +$81K (a **$67K gap from one trade**).

The bot currently defaults to `base_hit` mode (candle-low trail, activated at +15¢).  
A `home_run` mode exists but is rarely used.

**Full batch results:** `nexus2/reports/2026-02-16/batch_ross_sizing_test.md`

---

## Verified Facts (with evidence)

1. **Default exit mode is `base_hit`**  
   - File: `nexus2/domain/automation/warrior_types.py:119`  
   - Code: `session_exit_mode: str = "base_hit"`

2. **Home run mode exists with these parameters:**  
   - File: `nexus2/domain/automation/warrior_types.py:131-134`  
   - `home_run_partial_at_r: float = 2.0` (50% partial at 2:1 R)  
   - `home_run_trail_after_r: float = 1.5` (start trailing after 1.5R)  
   - `home_run_trail_percent: float = 0.20` (trail 20% below high)  
   - `home_run_move_to_be: bool = True` (move stop to breakeven after partial)

3. **Base hit mode uses candle-low trailing:**  
   - Activation: +15¢ above entry  
   - Trail: 2-bar low  
   - Fallback: flat +18¢ target

---

## Open Questions (INVESTIGATE FROM SCRATCH)

> [!IMPORTANT]
> These are questions, not assertions. Research Ross Cameron's actual methodology.

1. **How does Ross decide between base hit and home run on a given trade?**
   - Is it per-trade or per-session?
   - Does market conditions (hot vs. cold) affect this?
   - Does the quality of the setup affect this?

2. **How does Ross ride home runs?**
   - Does he use candle-low trails? What timeframe?
   - Does he use percentage-based trails?
   - Does he take partials, and at what levels?
   - When does he move to breakeven?

3. **How does Ross scale into winners (add on strength)?**
   - At what price levels does he add?
   - What's his max position size (shares or dollars)?
   - Does he add above key technical levels (VWAP, HOD, whole/half)?
   - How many adds does he typically do?

4. **What disqualifies a trade from home run treatment?**
   - Low volume? Poor market? Extended moves?
   - Does Ross ever switch from home run to base hit mid-trade?

### Primary Sources to Check
- `.agent/strategies/warrior.md` — documented strategy
- `.agent/knowledge/warrior_trading/` transcripts
- KI "Nexus 2 Trading Methodologies" → `warrior/` artifacts

---

## Deliverable

Write a structured research document to:  
`nexus2/reports/2026-02-16/research_homerun_scaling_methodology.md`

Include:
- Verified rules (with source citations)
- Observed patterns (from transcripts)
- Open questions requiring Clay's clarification
- **Do NOT invent numeric thresholds**
