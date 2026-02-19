---
description: Global guardrails to prevent presumptuous agent behavior
---

# Presumption Guardrails

> **Rule version:** 2026-02-19T07:01:00

These rules prevent the agent from acting without appropriate approval.

---

## Proposal Keyword Triggers

When the user uses these words, **respond with text/plan only** - do NOT edit files:
- "propose", "suggest", "recommend"
- "what do you think", "thoughts on"
- "how would you", "how should we"
- "consider", "evaluate", "review"

Only proceed to implementation after explicit approval (e.g., "approved", "proceed", "do it", "looks good", "yes").

---

## Ask-First Operations

The following operations **always require explicit approval** before execution:
1. **Renaming or moving files**
2. **Editing workflow documentation** (`.agent/workflows/`)
3. **Editing agent rules** (`.agent/rules/`)
4. **Deviating from documented processes**
5. **Changing established naming patterns**

---

## Trust Existing Automation

When a script/tool already handles an operation (e.g., saving to correct location):
- **Assume it's correct** unless there's evidence of failure
- **Do not "improve" by adding manual steps** that duplicate what the script does
- If unsure, **ask** rather than act
