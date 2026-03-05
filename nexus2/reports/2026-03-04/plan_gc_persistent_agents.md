# Gravity Claw: Autonomous Development Team

**Date:** 2026-03-04
**Purpose:** Transform Gravity Claw from a chat assistant into an autonomous AI development team that independently audits, plans, implements, tests, and validates improvements to the Nexus trading platform — competing alongside Clay's manual orchestration in Antigravity.

---

## Vision

GC spawns and manages 9 specialist agents as a fully autonomous coordinator:

```
Clay (Telegram) ←→ GC (Main + Observer)
                        │
                Coordinator Agent (persistent, autonomous)
                        │
        ┌───────────────┼───────────────┐
        │               │               │
   Planning         Execution       Validation
 ┌─────┴─────┐   ┌─────┴─────┐   ┌─────┴─────┐
 │ Backend   │   │ Backend   │   │ Testing   │
 │ Planner   │   │ Specialist│   │ Specialist│
 ├───────────┤   ├───────────┤   ├───────────┤
 │ Strategy  │   │ Frontend  │   │ Audit     │
 │ Expert    │   │ Specialist│   │ Validator │
 ├───────────┤   ├───────────┤   └───────────┘
 │ Code      │   │ Mock      │
 │ Auditor   │   │ Market    │
 └───────────┘   └───────────┘
        │               │
        └───────┬───────┘
                │
         Nexus GC Repo
         (forked workspace)
```

---

## Gemini 2.5 Flash Cost Analysis

| Metric | Estimate |
|--------|----------|
| **Model** | `google/gemini-2.5-flash` via OpenRouter |
| **Input** | ~$0.15/1M tokens |
| **Output** | ~$0.60/1M tokens |
| **Per agent task** (5K in + 2K out × 8 iters) | ~$0.01–0.02 |
| **Per full dev cycle** (8 agents) | ~$0.20–0.50 |
| **5 cycles/day** | ~$1–2.50/day |
| **Monthly estimate** | ~$30–75 |

> [!TIP]
> Gemini 2.5 Flash is extremely cost-effective for this use case. The full autonomous team running 5 cycles/day would cost roughly what a single Anthropic Claude session costs.

---

## Architecture

### Core Principles

1. **Coordinator is the brain** — persistent agent on a timer, manages all workflow state
2. **Specialists are ephemeral** — spawned for a task, produce output files, terminate
3. **Communication via handoff files** — same pattern as current Antigravity workflow
4. **Adversarial validation** — coordinator never trusts claims without evidence
5. **Observable everything** — full thought-process logs per agent, visible to Clay

### New Modules

```
src/swarm/
├── background-agent.ts       # Persistent agent lifecycle (spawn/message/list/stop)
├── background-agent-tools.ts # Tool definitions for the 4 agent management tools
├── agent-profiles.ts         # Predefined profiles for 9 specialist types + coordinator
├── workflow-engine.ts         # Development cycle state machine
└── agent-logger.ts           # Per-agent log files with thought trails
```

---

## Proposed Changes

### Phase 1: Persistent Agent Infrastructure

#### [NEW] [background-agent.ts](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/gravity-claw/src/swarm/background-agent.ts)

Core agent lifecycle management:

- **`BackgroundAgent` interface** — name, systemPrompt, recurringTask, intervalMs, toolFilter, status, stats
- **`spawnAgent(config)`** — creates and starts a named background agent on `setInterval`
- **`messageAgent(name, message)`** — sends ad-hoc message, returns response
- **`listAgents()`** — returns all running agents with uptime, tick count, last output
- **`stopAgent(name)`** — stops and removes a named agent
- **`registerAgentCallback(cb)`** — registers Telegram push callback (same pattern as `scheduler.ts`)

Each tick: runs a lightweight agent loop (reuses `runSubAgent` from `swarm-engine.ts`), captures output, pushes to Telegram if noteworthy.

#### [NEW] [background-agent-tools.ts](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/gravity-claw/src/swarm/background-agent-tools.ts)

Four tool definitions + executors exposed to the GC main agent:

| Tool | Params | Description |
|------|--------|-------------|
| `spawn_agent` | name, profile, task, interval_minutes, tool_filter | Create a named background agent |
| `message_agent` | name, message | Send a message to a running agent |
| `list_agents` | (none) | Show all running background agents |
| `stop_agent` | name | Stop a named background agent |

#### [NEW] [agent-logger.ts](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/gravity-claw/src/swarm/agent-logger.ts)

Per-agent observability:

- Writes to `data/agent-logs/{agent-name}/YYYY-MM-DD.log`
- Captures: timestamp, iteration #, tool calls, tool results, LLM reasoning, final output
- Provides `getAgentLog(name, lines?)` for reading recent logs
- Log format is human-readable markdown for easy review

#### [MODIFY] [registry.ts](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/gravity-claw/src/tools/registry.ts)

- Import 4 new tool defs + executors from `background-agent-tools.ts`
- Add to `tools` array and `toolExecutors` map

#### [MODIFY] [telegram.ts](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/gravity-claw/src/bot/telegram.ts)

- Import `registerAgentCallback` from `background-agent.ts`
- Call alongside `registerSchedulerCallback` in `ensureScheduler()`

---

### Phase 2: Agent Profiles + Coordinator

#### [NEW] [agent-profiles.ts](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/gravity-claw/src/swarm/agent-profiles.ts)

Predefined profiles for each agent type, extracted from the existing `.agent/rules/agent-*.md` files:

```typescript
interface AgentProfile {
    name: string;                    // e.g., "backend-planner"
    displayName: string;             // e.g., "Backend Planner"
    systemPrompt: string;            // Role, rules, output format
    toolFilter: string[];            // Allowed tools
    maxIterations: number;           // Per-task iteration limit
    outputPath: string;              // Where to write results
}
```

**9 specialist profiles** + 1 coordinator profile:

| Profile | Tools | Max Iterations |
|---------|-------|----------------|
| `coordinator` | shell_exec, read_file, write_file, list_dir, search_files, memory_save, memory_search, get_current_time | 15 |
| `backend-planner` | shell_exec, read_file, list_dir, search_files, write_file, get_current_time | 12 |
| `backend-specialist` | shell_exec, read_file, write_file, list_dir, search_files, get_current_time | 15 |
| `frontend-specialist` | shell_exec, read_file, write_file, list_dir, search_files, get_current_time | 12 |
| `code-auditor` | shell_exec, read_file, list_dir, search_files, write_file, get_current_time | 10 |
| `audit-validator` | shell_exec, read_file, list_dir, search_files, write_file, get_current_time | 10 |
| `testing-specialist` | shell_exec, read_file, write_file, list_dir, search_files, get_current_time | 12 |
| `mock-market` | shell_exec, read_file, write_file, list_dir, search_files, web_search, get_current_time | 10 |
| `strategy-expert` | read_file, list_dir, search_files, write_file, get_current_time | 8 |
| `algo-lab` | shell_exec, read_file, write_file, list_dir, search_files, get_current_time | 12 |

#### [NEW] [workflow-engine.ts](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/gravity-claw/src/swarm/workflow-engine.ts)

Development cycle state machine:

```
States:
  IDLE → AUDITING → PLANNING → VALIDATING_PLAN → IMPLEMENTING →
  TESTING → VALIDATING_IMPL → DEPLOYING → MONITORING → IDLE

Each transition:
  1. Coordinator reads current state
  2. Spawns the appropriate specialist agent
  3. Agent does work, writes output to reports/
  4. Coordinator evaluates output quality
  5. Decides: advance, retry, or escalate to Clay
```

**Coordinator decision protocol** (encoded in system prompt):

1. **Never trust claims** — require file paths, line numbers, command output
2. **Adversarial validation** — after every implementer, spawn a validator that tries to disprove the claims
3. **Regression gates** — run batch tests before AND after changes; reject if P&L regresses beyond threshold
4. **Escalation** — if uncertain or if regression detected, alert Clay via Telegram and pause
5. **Evidence format** — every finding must include: file path, line number, code snippet, command used, actual output

**Workspace management:**

- `NEXUS_GC_PATH` env var points to the forked repo
- All agent commands run with `Set-Location $env:NEXUS_GC_PATH`
- Coordinator tracks git state (branch, commit, dirty files)

---

## What Changes in Existing Files

| File | Change | Risk |
|------|--------|------|
| `src/tools/registry.ts` | Add 4 imports + registrations | Low — additive only |
| `src/bot/telegram.ts` | Add 1 import + 1 callback registration | Low — additive only |
| `.env` | Add `NEXUS_GC_PATH` for forked repo | Low |

All other changes are **new files** — zero risk to existing GC functionality.

---

## Verification Plan

### TypeScript Compilation

```powershell
cd "C:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\gravity-claw"
npx tsc --noEmit
```

This verifies all new code compiles without errors against the existing codebase.

### Manual Testing via Telegram

Since GC is a Telegram bot, all testing is done by chatting with the bot. These tests should be run in order:

**Phase 1 Tests (Infrastructure):**

1. **Spawn basic agent**: Tell GC *"Spawn an agent called TestBot that says the current time every 60 seconds"*
   - ✅ GC confirms spawn
   - ✅ TestBot sends time messages every 60 seconds

2. **List agents**: Tell GC *"List agents"*
   - ✅ Shows TestBot with uptime and tick count

3. **Message agent**: Tell GC *"Tell TestBot to tell me a joke instead of the time"*
   - ✅ GC relays instruction, TestBot responds

4. **Stop agent**: Tell GC *"Stop TestBot"*
   - ✅ GC confirms stop, no more messages

5. **Check logs**: Tell GC *"Show me TestBot's log"*
   - ✅ Shows thought-process log with timestamps, tool calls, outputs

**Phase 2 Tests (Coordinator):**

6. **Spawn coordinator**: Tell GC *"Spawn the development coordinator for Nexus GC"*
   - ✅ Coordinator starts, performs initial codebase audit
   - ✅ Reports findings via Telegram

7. **Observe workflow**: Wait for coordinator to complete a full audit → plan → implement → test cycle
   - ✅ Each phase reported via Telegram
   - ✅ Log files show per-agent reasoning

8. **Manual intervention**: Tell GC *"Tell Coordinator to pause and show me what it's working on"*
   - ✅ Coordinator pauses and reports current state

### Smoke Test (GC Still Works)

After all changes, verify GC's normal chat functionality still works:
- Memory save/search
- Skill running
- Single test mode
- Swarm execute
