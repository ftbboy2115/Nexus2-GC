# Backend Planner: Non-Entry Investigation

**Date:** 2026-02-16  
**Priority:** HIGH — HIND alone is +$55k Ross P&L that the bot missed entirely  
**Output:** `nexus2/reports/2026-02-16/findings_nonentry_investigation.md`

---

## Objective

Investigate why the Warrior bot produces `$0.00` P&L (no entry) for HIND and PRFX test cases.

## Cases to Investigate

### HIND (Jan 27) — Ross made +$55,252

```yaml
symbol: HIND
setup_type: pmh
gap_percent: 8.7        # LOW — may be below scanner threshold
premarket_high: 7.57
previous_close: 5.00
float_shares: 5000000
catalyst: "news"
ross_entry_time: "08:00"  # Breaking news entry
ross_pnl: 55252.51
entry_near: 5.00
```

**Hypothesis:** 8.7% gap is below scanner minimum gap threshold. Check `warrior_scanner.py` and `warrior_engine_entry.py` for gap filters.

### PRFX (Feb 11) — Ross made +$5,971

```yaml
symbol: PRFX
setup_type: pmh
gap_percent: 23.9       # SHOULD pass gap threshold
premarket_high: 7.93
previous_close: 2.60
float_shares: 800000    # Sub-1M float — may trigger low-float filter?
catalyst: "news"
ross_entry_time: "~09:00"
ross_pnl: 5970.90
entry_near: 4.15
```

**Hypothesis:** Either (a) sub-1M float filtering PRFX out, or (b) bar data doesn't generate a pattern match. 23.9% gap with news SHOULD pass scanner.

## Investigation Steps

### Step 1: Scanner Thresholds
Find and document ALL minimum thresholds in the scanner pipeline:
- **File:** `nexus2/domain/automation/warrior_engine.py` — `_evaluate_symbol` 
- **File:** `nexus2/domain/automation/warrior_scanner.py` — scan criteria
- **File:** `nexus2/domain/automation/warrior_engine_entry.py` — entry guards

Search for:
- `gap_percent` minimum thresholds
- `float` or `float_shares` filters (min/max)
- `rvol` minimum thresholds
- Any hardcoded number comparisons in scanner evaluation

### Step 2: Trace HIND Through Pipeline
Run the HIND test case YAML through the scanner logic mentally:
1. Does gap_percent=8.7% pass the gap filter?
2. Does the catalyst="news" pass?
3. Does float=5M pass float filters?
4. Do the intraday bars generate any pattern match?

### Step 3: Trace PRFX Through Pipeline
Same for PRFX:
1. Does gap_percent=23.9% pass? (should)
2. Does float=800K pass? (sub-1M may be filtered)
3. Do the intraday bars generate patterns?
4. Does the entry time (~09:00) fall within the active trading window?

### Step 4: Compare With Entering Cases
Pick 2-3 cases that DID enter with similar profiles:
- Similar gap% to HIND (8-15% range)
- Similar float to PRFX (sub-2M range)
Show what parameter was different.

## Evidence Requirements

For EVERY finding, provide:
```
**Finding:** [description]
**File:** [absolute path]:[line number]
**Code:** [exact copy-pasted snippet]
**Conclusion:** [reasoning]
```

## Output Format

Write to: `nexus2/reports/2026-02-16/findings_nonentry_investigation.md`

Structure:
1. Scanner threshold inventory (all gates with values)
2. HIND trace (where exactly does it fail?)
3. PRFX trace (where exactly does it fail?)
4. Recommendations (what thresholds to adjust, if any)
