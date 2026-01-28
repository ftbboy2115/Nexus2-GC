---
description: Use when YOU are coordinating multiple specialist agents in Agent Manager
---

# Coordinator Agent (You)

When coordinating multiple specialist agents in parallel, follow this pattern.

---

## Available Specialists

| Agent | Rule File | Domain |
|-------|-----------|--------|
| Backend | `@agent-backend-specialist.md` | FastAPI, domain logic, adapters |
| Frontend | `@agent-frontend-specialist.md` | React, Next.js, UI |
| Testing | `@agent-testing-specialist.md` | Tests only, no impl changes |
| Strategy Expert | `@agent-strategy-expert.md` | Methodology guidance |
| **Algo Lab** | `@agent-algo-specialist.md` | R&D Lab, backtesting, strategy discovery |

---

## Strategy Registry

**Location**: `.agent/strategies/`

| Strategy | File | Bot |
|----------|------|-----|
| Ross Cameron | `warrior.md` | Warrior |
| Qullamaggie (KK) | `qullamaggie.md` | NACbot |
| R&D Lab | `algo_generated.md` | Algo Lab |
| *(future)* | *(add new files)* | - |

> [!TIP]
> New strategies are added by creating files in `.agent/strategies/`  
> No need to edit agent rules.

---

## Starting a Multi-Agent Session

### Step 1: Create the Plan
Before spawning specialists, create `implementation_plan.md`

### Step 2: Open Agent Manager
Press `CTRL+E`

### Step 3: Start Specialist Conversations
Reference the rule file at the start of your prompt:

```
@agent-backend-specialist.md

Task: [Describe backend work]
Reference: implementation_plan.md
```

---

## Methodology Guidance

**Before implementing ANY trading logic**, ensure the agent knows which strategy applies:

```
@agent-strategy-expert.md

Question: What stop method should Warrior bot use?
Context: Implementing entry logic for scanner
```

Or have the specialist read the strategy file directly:

```
@agent-backend-specialist.md

Task: Implement stop logic for Warrior entry
Strategy: Read `.agent/strategies/warrior.md` for rules
```

---

## Hallucination Prevention Checklist

Before approving trading logic implementation:

- [ ] Agent cited the strategy file
- [ ] No invented numeric thresholds
- [ ] Correct methodology (Warrior vs KK vs Algo)
- [ ] RS ≠ RSI, EP = Episodic Pivot
- [ ] Stop logic matches documented method

---

## File Handoff Pattern

```
implementation_plan.md    → All agents read
backend_status.md         → Backend writes
frontend_status.md        → Frontend writes
issues_found.md           → Testing writes (bugs)
backend_requests.md       → Frontend writes, Backend reads
frontend_requests.md      → Backend writes, Frontend reads
```

---

## When to Use Multi-Agent

✅ Large features touching multiple domains  
✅ Parallel backend + frontend work  
✅ Feature implementation + test writing  

❌ Simple bug fixes (use single agent)  
❌ Quick questions  
❌ Single-file changes
