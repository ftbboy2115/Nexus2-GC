# Context Degradation Audit: Agent Rules & Multi-Agent Workflow

**Date:** 2026-02-17  
**Scope:** All 25 files in `.agent/rules/`, 1 file in `.agent/knowledge/`, and 10 `MEMORY[]` user rules  
**Framework:** The 5 degradation patterns from `.agent/skills/skills/context-degradation/SKILL.md`

---

## Executive Summary

The Nexus 2 agent rules are **well-defended** against *context poisoning* (the most dangerous pattern) thanks to discovery-based handoffs, evidence-format mandates, and the hypothesis-vs-confirmation guardrail. However, the system has **significant vulnerabilities** in three areas:

| Pattern | Severity | Finding |
|---------|----------|---------|
| **Context Distraction** | 🔴 HIGH | Massive boilerplate duplication inflates every agent's context |
| **Context Clash** | 🟡 MEDIUM | User-rules duplicate agent-rules, creating version-drift risk |
| **Context Confusion** | 🟡 MEDIUM | All 10 `MEMORY[]` modes load simultaneously, diluting focus |
| Context Poisoning | 🟢 LOW | Strong existing defenses |
| Lost-in-Middle | 🟢 LOW | Rule files are reasonably sized; critical info at edges via `[!CAUTION]` blocks |

---

## Finding 1: Boilerplate Duplication Causes Context Distraction (🔴 HIGH)

### The Problem
Three blocks of text are **copy-pasted identically** across nearly every agent rule file:

| Boilerplate Block | Char Count | Files Containing It |
|-------------------|------------|---------------------|
| Windows Environment table | ~430 chars | **All 10** specialist files + coordinator (11 total) |
| Document Output Location | ~380 chars | **All 10** specialist files + coordinator (11 total) |
| Strategy Registry Reference | ~250 chars | 8 of 10 specialist files |

**Total wasted tokens:** Roughly **~1,060 chars × 11 files ≈ 11,660 characters** of pure duplication loaded into context. That's approximately **3,000-4,000 tokens** of zero-information-value content competing for attention in every agent session.

### Why It Matters (from the skill)
> *"Even a single irrelevant document reduces performance significantly. The effect follows a step function where the presence of any distractor triggers degradation."*

These blocks aren't *irrelevant* per se — a Windows command table is important — but loading 11 copies of the identical table is. Each copy competes for attention budget with the agent's *actual* domain-specific instructions.

### Recommendation
Extract shared boilerplate into an `_shared.md` partial file. Reference it once in each specialist file rather than duplicating. Alternatively, since these are `MEMORY[]` user rules, use the coordinator's copy as the authoritative source and remove duplicates from specialist files.

**Files affected:** All 10 `agent-*.md` files.

---

## Finding 2: MEMORY[] Rules Duplicate Agent Rules — Context Clash Risk (🟡 MEDIUM)

### The Problem
The `agent-coordinator.md` file exists **twice** in every conversation:
1. As the `.agent/rules/agent-coordinator.md` file (loaded on demand)
2. As `MEMORY[agent-coordinator.md]` (loaded into **every** conversation's system prompt, always)

These two copies are **not identical** — the `MEMORY[]` version was captured at some past point and may drift from the file version if either is updated without the other.

Similarly, several mode files exist as both rule files AND `MEMORY[]` entries:
- `architecture-and-planning-mode.md` — rule file AND `MEMORY[]`
- `implementation-and-refactoring-mode.md` — rule file AND `MEMORY[]`
- `documentation-and-api-contract-mode.md` — rule file AND `MEMORY[]`
- `research-and-documentation-mode.md` — rule file AND `MEMORY[]`
- `testing-and-verifcation-mode.md` — rule file AND `MEMORY[]`
- `trading-logic-and-safety-review-mode.md` — rule file AND `MEMORY[]`
- `operating-system-considerations.md` — rule file AND `MEMORY[]`
- `command-line-instructions.md` — rule file AND `MEMORY[]`

### Why It Matters (from the skill)
> *"Context clash develops when accumulated information directly conflicts, creating contradictory guidance that derails reasoning."*

If `agent-coordinator.md` is updated (e.g., adding a new specialist) but `MEMORY[agent-coordinator.md]` is not, the agent sees **two versions of the truth**. The model must decide which to follow — and per the skill's research on context clash, this creates reasoning errors.

### Current Risk Assessment
- **If both are manually maintained**: HIGH risk — human will forget to update both
- **If MEMORY[] auto-syncs**: LOW risk — but this should be verified

### Recommendation
1. **Audit whether `MEMORY[]` entries auto-sync** with rule files. If not, decide on a single source of truth.
2. If they don't auto-sync: remove the `MEMORY[]` copies of files that exist in `.agent/rules/`. The rule files are the living documents; the `MEMORY[]` copies are frozen snapshots.

---

## Finding 3: Mode Confusion from Simultaneous Mode Loading (🟡 MEDIUM)

### The Problem
There are **6 distinct "modes"** loaded via `MEMORY[]` user rules into every conversation:

1. `architecture-and-planning-mode.md` — "You are operating in ARCHITECTURE & PLANNING MODE"
2. `implementation-and-refactoring-mode.md` — "You are operating in IMPLEMENTATION & REFACTORING MODE"
3. `documentation-and-api-contract-mode.md` — "You are operating in DOCUMENTATION & API CONTRACT MODE"
4. `research-and-documentation-mode.md` — "You are operating in RESEARCH & DOCUMENTATION MODE"
5. `testing-and-verifcation-mode.md` — "You are operating in TESTING & VERIFICATION MODE"
6. `trading-logic-and-safety-review-mode.md` — "You are operating in TRADING LOGIC & SAFETY REVIEW MODE"

**Each mode opens with "You are operating in [X] MODE"** — a direct identity instruction. When all 6 load simultaneously, the model sees 6 conflicting identity statements.

### Why It Matters (from the skill)
> *"Context confusion arises when irrelevant information influences responses... Confusion is especially problematic when context contains multiple task types or when switching between tasks within a single session."*

The model doesn't have a mechanism to know which mode is "active." All 6 are in context at equal priority. This creates:
- **Identity dilution** — the model hedges across all 6 modes
- **Instruction bleed** — rules from inactive modes leak into active behavior
- **Wasted context** — 5/6 of the mode instructions are irrelevant at any given time

### Estimated Context Waste
Each mode file is ~40-60 lines of dense instructions. Total across all 6: ~300 lines ≈ **~4,000-5,000 tokens** of competing, often contradictory instructions.

### Recommendation
Two options:

**Option A (Preferred): Conditional loading.** Convert modes from `MEMORY[]` (always-on) to conditional rules with trigger descriptions. Load only the relevant mode per conversation.

**Option B: Mode consolidation.** Merge all 6 modes into a brief "mode selector" document that lists modes as reference but does NOT use identity language ("You are operating in..."). Instead, use "When in X mode, follow these rules."

---

## Finding 4: KK-Style Rules Repetition Across Modes (🟢 LOW, but Compounding)

### The Problem
The same KK-style trading logic rules (EP, ATR ≤ 1.0, tactical stop hierarchy, etc.) are repeated in:
- `trading-logic-and-safety-review-mode.md` (full, detailed)
- `testing-and-verifcation-mode.md` (abbreviated version)
- `architecture-and-planning-mode.md` (abbreviated version)
- `implementation-and-refactoring-mode.md` (abbreviated version)
- `documentation-and-api-contract-mode.md` (abbreviated version)
- `project-goal-nexus2.md` (brief mention)

Each copy is slightly different in detail level and phrasing.

### Why It Matters
This is a combination of **distraction** (redundant information) and **clash** (slightly different phrasings). For example:
- `trading-logic-and-safety-review-mode.md` says "ATR constraint: Tactical stop distance must be ≤ 1.0 ATR"
- `testing-and-verifcation-mode.md` says "ATR ≤ 1.0 enforcement"
- The strategy files in `.agent/strategies/` are the **actual** source of truth

### Recommendation
Keep KK-style rules exclusively in `.agent/strategies/qullamaggie.md` (the canonical source). Replace the lengthy KK rule lists in each mode file with a single line: `> For KK methodology rules, consult .agent/strategies/qullamaggie.md`.

---

## Finding 5: What's Working Well (🟢 Strengths)

### Anti-Poisoning Defenses (Excellent)
The system has strong protections against the most dangerous degradation pattern:

| Defense | File | How It Prevents Poisoning |
|---------|------|--------------------------|
| Discovery-based handoffs | `agent-coordinator.md` | Forces facts vs questions separation — prevents coordinator assumptions from propagating |
| Evidence format mandate | `agent-coordinator.md`, `agent-code-auditor.md`, `agent-audit-validator.md` | Requires file:line + grep proof — kills unverified claims |
| Hypothesis vs Confirmation | `hypothesis-vs-confirmation.md` | Forces "I suspect" language until code-verified |
| Presumption guardrails | `presumption-guardrails.md` | Blocks action without approval on critical operations |
| Hallucination Prevention Checklist | `agent-coordinator.md`, `agent-strategy-expert.md` | Requires citation of strategy files |
| Validator pairings | `agent-coordinator.md` | Independent verification for every implementer claim |

### Anti-Lost-in-Middle (Good)
- `[!CAUTION]` blocks create visual "attention anchors" that models notice even in long context
- Rule files are kept under 350 lines each
- Critical information is consistently placed at the top (Windows env) and bottom (output location) of files

### Context Isolation (Good)
- Multi-agent architecture inherently isolates context per specialist
- Clear boundary definitions (✅ Your Scope / ❌ NOT Your Scope) in every specialist file
- Handoff files create a minimal, structured communication channel vs full context sharing

---

## Quantitative Summary

| Metric | Value | Assessment |
|--------|-------|------------|
| Total rule files | 25 | Manageable |
| Total `MEMORY[]` entries | 10 | HIGH — all load simultaneously |
| Duplicated boilerplate instances | ~33 blocks | Wastes ~3,000+ tokens |
| Mode identity conflicts | 6 simultaneous | Creates confusion |
| Largest rule file | `agent-backend-planner.md` (340 lines) | Within safe bounds |
| Files with clash risk (rule + MEMORY[]) | 8 files | Version drift danger |

---

## Prioritized Recommendations

| # | Action | Impact | Effort |
|---|--------|--------|--------|
| 1 | **Convert 6 mode files from MEMORY[] to conditional rules** | Eliminates ~4,000 tokens of confusion per conversation | Medium |
| 2 | **Extract boilerplate (Windows env, output location) to shared partial** | Eliminates ~3,000 tokens of distraction per agent session | Small |
| 3 | **Remove MEMORY[] duplicates of rule files** (or verify auto-sync) | Eliminates clash risk across 8 files | Small |
| 4 | **Consolidate KK-style rules to strategy files only** | Eliminates intra-mode clash and ~1,000 tokens of repetition | Small |
| 5 | **Add a "context budget" note to coordinator rules** | Awareness prevents future inflation | Trivial |

---

## Appendix: Files Audited

### Agent Specialist Rules (10 files)
- `agent-coordinator.md` (324 lines)
- `agent-backend-specialist.md` (162 lines)
- `agent-frontend-specialist.md` (134 lines)
- `agent-testing-specialist.md` (186 lines)
- `agent-strategy-expert.md` (156 lines)
- `agent-code-auditor.md` (205 lines)
- `agent-audit-validator.md` (129 lines)
- `agent-backend-planner.md` (340 lines)
- `agent-mock-market-specialist.md` (217 lines)
- `agent-algo-specialist.md` (190 lines)

### Behavioral Guardrails (7 files)
- `hypothesis-vs-confirmation.md` (25 lines)
- `presumption-guardrails.md` (40 lines)
- `artifact-protection.md` (42 lines)
- `refactoring-verification-standard.md` (98 lines)
- `calendar-check.md` (36 lines)
- `operating-system-considerations.md` (via MEMORY[])
- `command-line-instructions.md` (via MEMORY[])

### Mode Files (6 files)
- `architecture-and-planning-mode.md`
- `implementation-and-refactoring-mode.md`
- `documentation-and-api-contract-mode.md`
- `research-and-documentation-mode.md`
- `testing-and-verifcation-mode.md`
- `trading-logic-and-safety-review-mode.md`

### Other
- `project-goal-nexus2.md`
- `user-defined-momentum-screener.md` (conditional rule — good practice!)
- `.agent/knowledge/debugging_methodology.md`
