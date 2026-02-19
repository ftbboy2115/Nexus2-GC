# Artifact Protection Rules

> **Rule version:** 2026-02-19T07:01:00

> [!CAUTION]
> **READ THIS FILE** before creating any artifact in the brain directory.
> This rule applies EVERY TIME you create `plan_*.md`, `handoff_*.md`, `walkthrough_*.md`, or `investigation_*.md`.

## Pre-Creation Checklist

Before creating ANY artifact:

1. ✅ Read this file (`artifact-protection.md`)
2. ✅ Use feature-specific naming (e.g., `plan_data_storage.md`, NOT `implementation_plan.md`)
3. ✅ Check if a similar file already exists

> [!WARNING]
> **NEVER rename artifacts via PowerShell** (e.g., `Move-Item`).  
> This breaks Antigravity's internal tracking and makes files unviewable in the UI.  
> If you need a different name, **delete and recreate** using `write_to_file`.

## NEVER Overwrite Plans Without Checking

Before using `Overwrite=true` on ANY artifact file in the brain directory:

1. **ALWAYS view the existing file first** to understand what's there
2. **If it contains valuable content**, create a NEW file instead with a descriptive name:
   - ❌ `implementation_plan.md` (generic, gets overwritten)
   - ✅ `plan_pattern_priority_framework.md` (specific, preserved)
   - ✅ `plan_server_restart_endpoint.md` (specific, preserved)
3. **Ask the user** if you're unsure whether content should be preserved

## Naming Convention for Plans

Use feature-specific names, not generic `implementation_plan.md`:
- `plan_[feature_name].md` for implementation plans
- `investigation_[topic].md` for research/debugging
- `walkthrough_[feature].md` for completed work summaries

## The Single Generic Files

These files are OK to update (not overwrite entirely):
- `task.md` - The living task checklist (append new phases, don't replace)
