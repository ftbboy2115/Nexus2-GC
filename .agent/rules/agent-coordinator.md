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
| **Code Auditor** | `@agent-code-auditor.md` | Code quality, dead code, refactoring |
| **Audit Validator** | `@agent-audit-validator.md` | Verify audit claims, quality assurance |
| **Mock Market** | `@agent-mock-market-specialist.md` | Historical replay testing, test cases |

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

## 🚨 MANDATORY VALIDATION PROTOCOL 🚨

> [!CAUTION]
> **NO implementation task is complete until validated by the assigned validator.**
> Agents have been found making unverified claims. Trust but verify.

### Implementation → Validator Pairings

Every implementation agent has a corresponding validator:

| Implementer | Validator | Validation Method |
|-------------|-----------|-------------------|
| Backend | Testing Specialist | Run `pytest` on affected modules |
| Frontend | (Human review) | Manual UI verification |
| Code Auditor | Audit Validator | Verify grep claims, run commands |
| Mock Market | Testing Specialist | Validate test cases work |
| Algo Lab | Testing Specialist | Run backtest verification |

### Validation Rules

1. **Sequential Execution** - Validator runs AFTER implementer completes
2. **Independent Verification** - Validator runs commands themselves, doesn't trust claims
3. **Evidence Required** - Validator must provide:
   - Exact commands run
   - Actual output (not paraphrased)
   - PASS/FAIL per claim
4. **Failure Escalation** - If validation fails:
   - Document specific failure
   - Return to coordinator
   - Re-assign to implementer with failure evidence

### Coordinator Workflow

```
1. Spawn Implementer → Wait for completion
2. Spawn Validator with implementer's claims
3. Review validation report
4. If FAIL: Loop back to step 1 with failure notes
5. If PASS: Mark task complete
```

### Validation Report Format

Validators MUST produce:

```markdown
## Validation Report: [Task Name]

### Claims Verified
| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | [claim] | PASS/FAIL | [command + output] |

### Overall Rating
- **HIGH**: All claims verified
- **MEDIUM**: Minor issues (cosmetic)  
- **LOW**: Major issues (requires rework)

### Failures (if any)
- Claim #X: Expected [X], got [Y]
```

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
