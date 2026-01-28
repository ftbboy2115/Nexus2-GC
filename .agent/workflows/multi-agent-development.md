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

```
Agent 1: "Backend Specialist"
- Focus: FastAPI routes, domain logic, database
- Workspace: Nexus (focused on /api, /domain)

Agent 2: "Frontend Specialist"  
- Focus: React/Next.js UI, TypeScript
- Workspace: Nexus (focused on /frontend)

Agent 3: "Testing & Verification"
- Focus: Writing tests, running backtests
- Workspace: Nexus (focused on /tests, /domain/lab)
```

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
