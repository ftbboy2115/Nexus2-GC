# Implementation Plan: Scaling v2 — Ross Cameron Level-Break Methodology

**Date:** 2026-02-26  
**Goal:** Replace the accidental scaling behavior with proper Ross Cameron level-break scaling to improve Warrior bot P&L.

---

## Background

Current scaling is "accidentally" beneficial — a broken pullback zone check triggers one scale-in per trade, producing +$3,681 (+38%) over un-scaled baseline. With the new parameter optimizations ($359K total), scaling is already a major P&L contributor. **Scaling v2** replaces this with the documented Ross Cameron add methodology.

### Research Source
`nexus2/reports/2026-02-16/research_ross_add_methodology.md` — HIGH confidence, grounded in transcript evidence.

---

## Phase 1: Backend Planner — Deep Code Research

> **Agent:** Backend Planner (`agent-backend-planner.md`)  
> **Scope:** READ ONLY — map existing code, identify change points, write spec

### Tasks

1. **Map the current scaling flow end-to-end:**
   - `warrior_monitor_scale.py`: `check_scale_opportunity()` → triggers, zone checks, MACD gate
   - `warrior_monitor_scale.py`: `check_momentum_add()` → momentum-based adds
   - `warrior_monitor_scale.py`: `execute_scale_in()` → order submission, PSM transitions
   - `warrior_monitor.py`: Where scaling checks are called (monitor tick loop)
   - `warrior_types.py`: `WarriorMonitorSettings` scaling-related fields
   
2. **Identify the "accidental" behavior:**
   - What's the broken pullback zone check that accidentally scales every case once?
   - What condition is always-true that shouldn't be?
   
3. **Map structural level detection needs:**
   - How does the bot currently know about price levels ($X.00, $X.50)?
   - Where would level-holds-check fit in the existing flow?
   - Where would take-profit-at-level fit?

4. **Document change points** in a spec with file paths, line numbers, and proposed modifications

### Output
`nexus2/reports/2026-02-26/spec_scaling_v2_code_research.md`

---

## Phase 2: Backend Specialist — Implementation

> **Agent:** Backend Specialist (`agent-backend-specialist.md`)  
> **Scope:** Implement changes per Phase 1 spec

### Core Changes (from research doc)

#### Must Implement
1. **Structural level detection** — detect $X.00 and $X.50 levels relative to current price
2. **Level-break scaling** — add on break of structural level (replace broken pullback zone)
3. **Level-holds check** — verify level holds before add-back after profit take
4. **Take-profit at structural levels** — partial profit at $X.00/$X.50
5. **MACD gate for adds** — no adds when MACD crosses negative
6. **Configurable max_scale_count** — keep current setting (4)

#### Should Implement
7. **Give-back tolerance** — configurable (default 25% from peak daily P&L)

#### Must NOT Implement (Ross explicitly doesn't do these)
- ❌ Traditional trailing stops
- ❌ Fixed R-multiple targets  
- ❌ Adding on weakness / averaging down
- ❌ Adding after MACD goes negative

### Files to Modify
- `nexus2/domain/automation/warrior_monitor_scale.py` — Primary scaling logic
- `nexus2/domain/automation/warrior_types.py` — New settings fields
- `nexus2/domain/automation/warrior_monitor_exit.py` — Structural level profit-taking

### Output
Backend status report + testable claims

---

## Phase 3: Testing Specialist — Validation

> **Agent:** Testing Specialist (`agent-testing-specialist.md`)

### Verification Plan

#### Automated Tests
1. **Batch test comparison:**
   ```
   python scripts/gc_quick_test.py
   ```
   Compare Scaling v2 P&L against current $359K baseline.

2. **Unit tests for structural level detection:**
   - Verify $X.00 and $X.50 levels detected correctly
   - Verify level-holds-check logic
   - Verify MACD gate blocks adds when negative

3. **Pytest regression:**
   ```
   python -m pytest nexus2/tests/ -x -q
   ```
   Ensure no existing tests break.

#### Key Cases to Watch
- **GRI** ($17K → Ross $31K) — GRI is THE level-break case. Ross added at every $0.50/$1.00 level.
- **ROLR** ($46K → Ross $85K) — Ross used take-profit→add-back extensively.
- **NPT** ($68K → Ross $81K) — Already close, shouldn't regress.

---

## Sequencing

```
Phase 1 (Backend Planner) → Phase 2 (Backend Specialist) → Phase 3 (Testing)
         ↑                           ↑                           ↑
    Code research only          Implementation            Validation
    ~30 min                     ~60 min                   ~30 min
```

> [!IMPORTANT]
> **Coordinator role boundary:** I (coordinator) will create the handoffs and review results, but NOT dive into implementation code. Each specialist operates independently and produces a status report.
