---
description: Multi-agent development workflow using Antigravity Agent Manager
---

# Multi-Agent Development Workflow

This workflow leverages Google Antigravity's Agent Manager to orchestrate multiple AI agents working in parallel on the Nexus 2 project.

## Prerequisites

- Antigravity with Agent Manager (public preview)
- Agent Manager toggle: `CTRL+E` (Windows) / `CMD+E` (Mac)

---

## Core Concepts

### Agent Manager
The "Mission Control" dashboard for managing multiple agents across workspaces.
- **Toggle**: `CTRL+E` to switch between Agent Manager and Editor view
- **Purpose**: Birds-eye view of all agent activities, start conversations, manage workspaces

### Key Components

| Component | Trigger | Purpose |
|-----------|---------|---------|
| **Skills** | Agent-triggered (automatic) | Modular extensions in `.agent/skills/` with `SKILL.md` |
| **Workflows** | User-triggered (`/command`) | Saved prompts in `.agent/workflows/` |
| **Rules** | Always-on | Guardrails in `.agent/rules/` that constrain behavior |
| **Task Groups** | Automatic (Planning mode) | Agent subdivides large tasks into parallel units |

### Strategy Registry
Trading methodology definitions live in `.agent/strategies/`:

| File | Strategy | Bot |
|------|----------|-----|
| `warrior.md` | Ross Cameron | Warrior |
| `qullamaggie.md` | KK (Qullamaggie) | NACbot |
| `algo_generated.md` | R&D Lab strategies | Algo Lab |

**All agents reference this registry** for trading logic rules. Adding new strategies = add new file (no agent rule changes needed).

---

## Parallel Agent Patterns for Nexus 2

### Pattern 1: Domain-Specialist Agents
Run separate agents in the Agent Manager, each focused on a domain:

---

## Nexus 2 Specialist Agent Registry

| Agent | Rule File | Scope | Key Constraint |
|-------|-----------|-------|----------------|
| **Testing Specialist** | `agent-testing-specialist.md` | `nexus2/tests/` | READ ONLY for impl code |
| **Frontend Specialist** | `agent-frontend-specialist.md` | `frontend/src/` | Defer API changes to Backend |
| **Backend Specialist** | `agent-backend-specialist.md` | `nexus2/api/`, `nexus2/domain/` | Owns core logic |
| **Mock Market Specialist** | `agent-mock-market-specialist.md` | `adapters/simulation/` | Stay in SIM sandbox |
| **Backend Planner** | `agent-backend-planner.md` | Code research, tech specs | READ ONLY, plan not implement |
| **Coordinator** | `agent-coordinator.md` | Knowledge, workflows | Root Cause Fidelity |
| **Code Auditor** | `agent-code-auditor.md` | All code (P0 priority) | READ ONLY, no fixes |
| **Audit Validator** | `handoff_audit_validator_template.md` | Audit reports | Verify claims only |
| **Strategy Expert** | `agent-strategy-expert.md` | Trading methodology | Source-grounded research |
| **Algo Specialist** | `agent-algo-specialist.md` | R&D Lab, backtest | Experimental only |

### Refactoring Sub-Specialists (Feb 2026)

These specialists emerged during Phase 2 refactoring:

| Agent | Focus | Example Tasks |
|-------|-------|---------------|
| **Entry Specialist** | Entry trigger logic | Pattern extraction, wiring, guards |
| **Exit/Monitor Specialist** | Exit logic, position monitoring | Stop logic, scaling, base hit |
| **Core Services Specialist** | Shared infrastructure | Broker adapters, risk engine |

**Handoff Pattern**: Create `handoff_[specialist].md` with specific task details before spawning.

---

### Deployment Command

To spawn a specialist (CTRL+E → New Conversation):

```
@.agent/rules/agent-backend-specialist.md Execute the task defined in C:\Users\ftbbo\.gemini\antigravity\brain\[conversation-id]\handoff_telemetry_schema.md
```

> [!TIP]
> Copy the line, paste into new conversation. When you type `@`, Antigravity autocomplete kicks in - select the file, then the rest pastes normally.
> **Always use ABSOLUTE PATH for handoff files.**

### Pattern 2: Task-Parallel Agents
For large features, spawn multiple agents working on independent subtasks:

```
Example: Implementing new scanner type
├── Agent 1: Scanner logic implementation
├── Agent 2: API route + frontend UI
└── Agent 3: Test fixtures + unit tests
```

### Pattern 3: Research + Implementation
Run agents in complementary roles:

```
Agent 1: "Researcher" (PLANNING mode)
- Research KK methodology, transcripts
- Produce specs and documentation

Agent 2: "Implementer" (EXECUTION mode)  
- Consume specs, write code
- Implement based on researcher's output
```

---

## Best Practices

### Post-Refactor Verification (CRITICAL)
After any extraction + wiring refactoring:
1. **Grep verify**: Check each function is CALLED (not just imported)
2. **Import/Call matrix**: Document "Imported at Line X, Called at Line Y"
3. **Runtime smoke test**: `python -c "from module import func; print('OK')"`

See: `.agent/rules/refactoring-verification-standard.md` for full protocol.

> **Feb 2026 Lesson**: ABCD pattern was imported but never wired, causing production error.

### Handoff Quality Requirements (CRITICAL)

Vague handoffs lead to incomplete implementations. Follow these rules:

**1. Explicit Enumeration**
- DON'T: "Find the PASS/FAIL decision point and add DB write"
- DO: "Add DB write at these 13 specific locations: [enumerated list with line numbers]"

**2. Mandatory Pre-Audit**
Before creating implementation handoffs, the coordinator MUST:
- Audit the target file to enumerate ALL change points
- List each point explicitly in the handoff
- Include approximate line numbers

**3. Mandatory Post-Implementation Audit**
After EACH implementation phase:
- Spawn auditor to verify ALL points were addressed
- Do NOT proceed to next phase until audit passes
- Re-run implementation if coverage is incomplete

**4. Multi-File Handoffs**
If handoff mentions multiple files:
- Create SEPARATE handoffs per file, OR
- Use explicit checkboxes per file in single handoff

> [!CAUTION]
> **Feb 2026 Lesson (Telemetry Migration):**
> - Phase 2 handoff said "add DB writes to scanner PASS/FAIL points"
> - Agent only covered 3 of 13 rejection points
> - Handoff mentioned 2 files but agent only did 1
> - Required audit + fix handoff to complete the work
> - **Fix**: Enumerate all 13 rejection reasons explicitly in handoff

### Handoff Drift Prevention (CRITICAL)
Multi-phase refactoring creates **handoff drift** when later handoffs lose critical context from earlier phases.

**The Problem:**
- Phase 1 handoff documented dependency: "Use `pattern_service.py`, don't reimplement"
- Phase 3 handoff forgot to carry forward this context
- Agent happened to do it correctly (luck), but could have duplicated logic

**Prevention Protocol:**
1. **Re-read previous handoffs** before writing new ones
2. **Copy forward** any "Critical Context" or "Dependencies" sections
3. **Or reference them**: "See Phase 1 handoff (`handoff_pattern_extraction.md`) for dependency context"
4. **Handoff template** should include:
   ```markdown
   ## Dependencies (from prior phases)
   - `file.py` - Contains X logic, CALL don't duplicate
   - [Reference: handoff_phase1.md#L6-L21]
   ```

**Feb 2026 Lesson**: Phase 3 pattern extraction handoff forgot to mention `pattern_service.py` dependency that was documented in Phase 1. Agent did it correctly by luck.

### Conflict Prevention
- **One agent per file at a time** – Avoid agents editing the same file concurrently
- **Clear boundaries** – Assign distinct modules/directories to each agent
- **Explicit handoffs** – When one agent completes, start another on dependent work

### Workspace Organization
```
Recommended structure for multi-agent work:
├── Agent Manager (CTRL+E)
│   ├── Inbox (view all conversations)
│   ├── Workspace: Nexus
│   │   ├── Conversation: Backend work
│   │   ├── Conversation: Frontend work
│   │   └── Conversation: Testing
│   └── Playground (experiments)
```

### Context Isolation
Each agent has its own context window. Share information via:
1. **Files** – Write specs/docs that other agents read
2. **Knowledge Items** – Use Antigravity's knowledge system
3. **Explicit instructions** – Copy key info between agent prompts

---

## Nexus-Specific Multi-Agent Workflows

### Workflow A: Feature Development
```
1. Start Agent 1 (PLANNING mode):
   "Plan the [feature] implementation. Write spec to implementation_plan.md"
   
2. Review plan, approve

3. Start Agent 2 (EXECUTION - Backend):
   "Implement backend for [feature] per implementation_plan.md"
   
4. Start Agent 3 (EXECUTION - Frontend):  
   "Implement frontend for [feature] per implementation_plan.md"
   
5. Start Agent 4 (VERIFICATION):
   "Test [feature] - run unit tests, integration tests, browser tests"
```

### Workflow B: Parallel Bug Investigation
```
1. Start Agent 1: "Investigate [bug] in scanner logic"
2. Start Agent 2: "Investigate [bug] in API layer"
3. Start Agent 3: "Investigate [bug] in frontend"
→ First agent to find root cause informs fix strategy
```

### Workflow C: Bot Development (Warrior + NACbot)
```
Agent 1: Focused on Warrior Trading methodology
Agent 2: Focused on NACbot/Qullamaggie methodology  
Agent 3: Shared infrastructure (adapters, risk engine)
```

---

## Security Features

### Sandboxing
- **Enabled in Secure Mode**: Prevents file modifications outside project
- **Network control**: Can deny network access for sensitive work
- **Settings**: Antigravity User Settings → Sandboxing toggle

### Secure Mode
- All agent actions require manual approval
- Restricted file access
- Use for: production deployments, sensitive config changes

---

## Quick Reference

| Action | Command/Shortcut |
|--------|-----------------|
| Open Agent Manager | `CTRL+E` (Windows) |
| Start new conversation | Agent Manager → Start conversation |
| Run workflow | `/workflow-name` in chat |
| View all agents | Agent Manager → Inbox |
| Focus/hide editor | Agent Manager → workspace menu |

---

## Limitations (Preview)

- Rate limits apply during public preview
- Agents don't share context automatically
- Browser subagent may have environment issues
- Coordination between agents is manual
