# Backend Planner Handoff: Volume Gate Investigation for Re-Entries

## Task
Investigate whether a volume gate already exists in the Warrior entry pipeline, and if so, determine how it can be leveraged or modified to serve as a re-entry quality gate.

## Context
We just A/B tested re-entry quality gates. The MACD gate was a no-op (already covered by `check_entry_guards`). The Backend Planner's analysis found **volume ratio** is the strongest discriminator between good re-entries (0.65× late/early volume) vs bad re-entries (0.06×). Clay believes a volume gate may already exist.

## Investigation Steps

### 1. Find ALL existing volume checks in the entry pipeline
Search these files for volume-related logic:
- `nexus2/domain/automation/warrior_entry_guards.py` — main guard pipeline
- `nexus2/domain/automation/warrior_engine_entry.py` — entry triggers and `enter_position`
- `nexus2/domain/automation/warrior_entry_patterns.py` — pattern detection functions
- `nexus2/domain/automation/warrior_scanner_service.py` — scanner filters
- `nexus2/domain/indicators/` — technical service

Search terms: `volume`, `vol_`, `relative_volume`, `rvol`, `vol_gate`, `volume_ratio`

### 2. For each volume check found, document:
- **File and line number**
- **What it checks** (absolute volume, relative volume, volume ratio, etc.)
- **When it fires** (all entries? only scanner? only re-entries?)
- **Threshold values**
- **Whether it could serve as a re-entry quality gate**

### 3. Analyze the gap
- Does the existing volume gate apply to re-entries?
- If so, why aren't bad re-entries being blocked?
- If not, what would it take to extend it?

### 4. Propose implementation (if needed)
- Can we reuse existing volume logic with a stricter threshold for re-entries?
- Or do we need a new volume gate specifically for re-entry timing?

## Deliverable
Write findings to: `nexus2/reports/2026-02-15/analysis_volume_gate_investigation.md`

Structure:
1. Inventory of ALL existing volume checks (file, line, purpose)
2. Gap analysis (why bad re-entries aren't caught)
3. Recommendation (reuse vs new gate)
4. Implementation spec if applicable
