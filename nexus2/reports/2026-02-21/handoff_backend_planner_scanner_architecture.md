# Handoff: Backend Planner — Dual Scanner Architecture Spec

**Date:** 2026-02-21
**From:** Coordinator
**To:** Backend Planner (`@agent-backend-planner.md`)
**Priority:** HIGH

---

## Objective

Design the architecture for a two-tier scanner system that matches Ross Cameron's actual scanner methodology.

---

## Context

The Strategy Expert has completed research on Ross's scanners. Read the full report:
**`nexus2/reports/2026-02-21/research_ross_dual_scanner.md`**

Key findings:
- Ross uses 4 scanner types: Top Gainers, HOD Momentum, Five Pillar Alert, Running Up
- Our current scanner = Five Pillar Alert (checks gap%, RVOL, float, price, catalyst)
- We're missing Top Gainers (passive watchlist) and HOD Momentum (event-driven trigger)
- RVOL is used as a sort preference on Top Gainers, not a hard kill gate

---

## What To Spec

### 1. Current Scanner Code Research

Research the existing scanner implementation:
- Where does the current scanner live? (files, classes, functions)
- What is the current RVOL hard gate and where is it enforced?
- How does the scanner connect to the entry engine?
- What settings are already configurable via `WarriorScanSettings`?

### 2. RVOL Threshold — Make Configurable

**Requirement from Clay:** RVOL threshold should be:
- Configurable in `WarriorScanSettings`
- Exposed in the GUI Settings card with a tooltip showing the default value
- Default value: TBD (currently 2.0x — Strategy Expert found Ross publishes 5x but trades below it)

> [!IMPORTANT]
> This is NOT a dual scanner feature request yet — it's a standalone improvement to make the existing scanner's RVOL gate configurable rather than hard-coded.

### 3. Two-Tier Scanner Architecture

Design how we'd add:
- **Tier 1 (Discovery):** Top Gainers — simple sorted list by % change from close, with soft filters
- **Tier 2 (Action):** HOD Momentum — event-driven alert when stock breaks intraday high

Questions to address:
- Where does this fit in the existing codebase? New module? Extension of existing scanner?
- How does Tier 1 feed Tier 2? (Stock on Top Gainers watchlist → eligible for HOD trigger)
- What data sources do we need for real-time HOD tracking?
- How does this interact with the existing entry engine (`check_entry_triggers()`)?
- Should the HOD Momentum scanner replace the current "pattern trigger" logic, or supplement it?

### 4. HIND Test Fix

With the existing scanner:
- Making RVOL configurable (e.g., lowering to 1.5x or removing the hard gate) should fix the HIND test failure
- Confirm this in the spec

---

## Open Questions from Strategy Expert

These don't need to be answered in this spec but should be acknowledged:
1. Exact filter criteria for HOD Momentum Scanner (UNKNOWN from research)
2. Whether Running Up Scanner is distinct from HOD Momentum (UNKNOWN)
3. Whether Five Pillar Alert is a variant of Top Gainers (UNKNOWN)

---

## Deliverable

Write architecture spec to: `nexus2/reports/2026-02-21/spec_dual_scanner_architecture.md`

Include:
1. **Current state** — how the scanner works today (files, flow, settings)
2. **RVOL config change** — specific files to modify, settings schema, GUI integration points
3. **Two-tier architecture proposal** — module structure, data flow, integration points
4. **Migration path** — how to get from current state to two-tier (phased approach)
5. **HIND fix confirmation** — verify configurable RVOL resolves the test failure
