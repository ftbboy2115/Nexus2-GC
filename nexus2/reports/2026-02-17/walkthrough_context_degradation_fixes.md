# Context Degradation Fixes — Walkthrough

**Date:** 2026-02-17

## What Changed

### Fix #1: Boilerplate Extraction (HIGH) ✅

Created [_shared.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/rules/_shared.md) containing the Windows environment table and document output location rules.

Stripped both blocks from **10 files**:

| File | Lines Removed |
|------|---------------|
| [agent-coordinator.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/rules/agent-coordinator.md) | ~32 |
| [agent-backend-specialist.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/rules/agent-backend-specialist.md) | ~32 |
| [agent-frontend-specialist.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/rules/agent-frontend-specialist.md) | ~32 |
| [agent-testing-specialist.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/rules/agent-testing-specialist.md) | ~32 |
| [agent-strategy-expert.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/rules/agent-strategy-expert.md) | ~32 |
| [agent-code-auditor.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/rules/agent-code-auditor.md) | ~32 |
| [agent-audit-validator.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/rules/agent-audit-validator.md) | ~32 |
| [agent-backend-planner.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/rules/agent-backend-planner.md) | ~32 |
| [agent-mock-market-specialist.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/rules/agent-mock-market-specialist.md) | ~32 |
| [agent-algo-specialist.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/rules/agent-algo-specialist.md) | ~32 |

**Total:** ~320 lines (~3,000 tokens) of duplicated distraction eliminated.

---

### Fix #2: Mode File Slimming (MEDIUM) ✅

Slimmed all 6 mode files by removing KK methodology duplication and fixing identity conflicts:

| File | Before | After | Reduction |
|------|--------|-------|-----------|
| [architecture-and-planning-mode.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/rules/architecture-and-planning-mode.md) | 47 | 23 | 51% |
| [implementation-and-refactoring-mode.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/rules/implementation-and-refactoring-mode.md) | 48 | 21 | 56% |
| [documentation-and-api-contract-mode.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/rules/documentation-and-api-contract-mode.md) | 53 | 21 | 60% |
| [testing-and-verifcation-mode.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/rules/testing-and-verifcation-mode.md) | 60 | 21 | 65% |
| [research-and-documentation-mode.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/rules/research-and-documentation-mode.md) | 150 | 31 | 79% |
| [trading-logic-and-safety-review-mode.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/rules/trading-logic-and-safety-review-mode.md) | 174 | 31 | 82% |
| **Total** | **532** | **148** | **72%** |

Key changes:
- `"You are operating in X MODE"` → `"When in X mode"` (eliminates 6 conflicting identity statements)
- KK methodology bullet lists → single reference to `.agent/strategies/`
- Redundant NON-GOALS section removed from research mode (was repeating the DO NOT list)

---

## Fix #3: MEMORY[] Cleanup (Manual — For Clay)

> [!IMPORTANT]
> The following MEMORY[] entries are **frozen snapshots** of rule files that you maintain in `.agent/rules/`. Since the rule files are the living source of truth, these MEMORY[] copies create **context clash risk** if they drift out of sync.

### MEMORY[] Entries to REMOVE (8 entries)

These all duplicate files in `.agent/rules/` which are already loaded by the system:

| MEMORY[] Entry | Duplicates Rule File | Action |
|----------------|---------------------|--------|
| `MEMORY[agent-coordinator.md]` | `agent-coordinator.md` | ❌ REMOVE |
| `MEMORY[architecture-and-planning-mode.md]` | `architecture-and-planning-mode.md` | ❌ REMOVE |
| `MEMORY[implementation-and-refactoring-mode.md]` | `implementation-and-refactoring-mode.md` | ❌ REMOVE |
| `MEMORY[documentation-and-api-contract-mode.md]` | `documentation-and-api-contract-mode.md` | ❌ REMOVE |
| `MEMORY[research-and-documentation-mode.md]` | `research-and-documentation-mode.md` | ❌ REMOVE |
| `MEMORY[testing-and-verifcation-mode.md]` | `testing-and-verifcation-mode.md` | ❌ REMOVE |
| `MEMORY[trading-logic-and-safety-review-mode.md]` | `trading-logic-and-safety-review-mode.md` | ❌ REMOVE |
| `MEMORY[operating-system-considerations.md]` | `_shared.md` (now) | ❌ REMOVE |

### MEMORY[] Entries to KEEP (2 entries)

| MEMORY[] Entry | Reason to Keep |
|----------------|---------------|
| `MEMORY[user_global]` | Global model routing rules — not in rule files |
| `MEMORY[command-line-instructions.md]` | Small, always-relevant, no duplication risk |
| `MEMORY[project-goal-nexus2.md]` | Core project identity — critical to always have |

> [!NOTE]
> If MEMORY[] entries auto-sync with rule files, this cleanup is unnecessary. Test by editing a rule file and checking if the MEMORY[] version updates in the next conversation.
