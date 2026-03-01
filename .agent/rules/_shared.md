---
trigger: always_on
description: Shared rules inherited by all specialist agents — Windows environment and document output standards
---

# Shared Agent Standards

> **Rule version:** 2026-02-19T07:01:00

These rules apply to ALL specialist agents. Do not duplicate in individual rule files.

---

## 🚨 Windows Environment (CRITICAL)

> [!CAUTION]
> This project runs on **Windows with PowerShell**. Linux commands will FAIL.

| ❌ Do NOT Use | ✅ Use Instead |
|--------------|---------------|
| `cat` | `Get-Content` |
| `curl` | `Invoke-RestMethod` or `Invoke-WebRequest` |
| `&&` (chaining) | `;` or separate commands |
| `rm` | `Remove-Item` |

---

## 🔍 Search Tools — Use Symlink Paths

> [!IMPORTANT]
> The actual project path contains spaces and parentheses (`Documents (sync'd)`) which breaks `grep_search` / `codebase_search`.
> **Always use the symlink paths for search tools:**

| Project | Symlink Path | Actual Path |
|---------|-------------|-------------|
| Nexus | `C:\Dev\Nexus` | `C:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus` |
| Gravity Claw | `C:\Dev\gravity-claw` | `C:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\gravity-claw` |

**Rules:**
1. Use `C:\Dev\Nexus\...` for `grep_search`, `find_by_name`, and `codebase_search`
2. Both the symlink and actual paths work for `view_file`, `run_command`, etc.
3. If a search returns 0 results, verify with `view_file` before concluding code is missing

> [!CAUTION]
> **Do NOT conclude that code is missing based solely on grep_search returning 0 results.**
> Always verify with `view_file` before reporting a claim as FAILED.

---

## ⚠️ Command Execution (CRITICAL)

> [!WARNING]
> **Wait for each command to complete before doing other work.**
> If you try to run additional tools while a command is pending, they will fail.

- Run your commands and **wait for output** before proceeding
- You CAN run multiple commands in parallel — but don't mix commands with non-command tool calls
- If a command hangs, **ask Clay for help** rather than trying to work around it
- **Long-running commands (>2 min):** Chain `python scripts/notify.py "description"` after the command so Clay gets a Telegram alert when it finishes. Example:
  ```powershell
  Invoke-RestMethod -Method POST -Uri "..." | Out-File "output.json"; python scripts/notify.py "Batch test complete"
  ```

---

## 📁 Document Output Location

> [!IMPORTANT]
> All reports, plans, specs, and audit documents **MUST** be written to the project reports directory:
> `nexus2/reports/YYYY-MM-DD/` (use today's date)

**Do NOT write documents to your brain/artifacts directory.** Documents must be version-controlled and findable by other agents.

**Naming convention:** `<type>_<feature>.md`
- Plans: `plan_hod_break_fixes.md`
- Audit reports: `audit_hod_break_impl.md`
- Test results: `batch_test_hod_break.md`
- Validation: `validation_entry_logic.md`
- Specs: `spec_pattern_competition.md`

---

## 🚨 Verify Before Asserting (CRITICAL)

> [!CAUTION]
> **If you haven't verified it with a tool call, do NOT state it as fact.**

This applies to ALL communication — handoffs, reports, AND direct conversation with Clay.

| Claim Type | Must Verify With | Example Failure |
|------------|-----------------|-----------------|
| File/table names | Search tools or `Select-String` | Said "table is in quote_audit.db" — it was in `nexus.db` |
| Root causes | Code trace, not speculation | Said "Polygon API calls cause slowness" — data was pre-cached |
| Tool capabilities | Say "I'm not sure" if untested | Confidently "corrected" a true DBeaver SSH claim to false |
| DB schemas | Search for `__tablename__` in code | Guessed table name instead of checking model |

**The rule:** Before stating a fact, ask: *"Did I verify this with a tool, or am I generating from memory?"*
- Verified with tool → state as fact
- From memory → say "I believe" / "likely" / "let me check"
- Don't know → say "I don't know"

> [!WARNING]
> **Confident self-corrections are equally dangerous.**
> When correcting a previous statement, verify the correction too — don't just flip your answer.
> On Feb 18 2026, the coordinator correctly stated DBeaver supports SSH for SQLite, then when
> challenged, confidently "corrected" itself to say it doesn't — which was wrong. Both the
> original assertion AND the correction were made without verification.

---

## 📄 Artifact Protection

> [!IMPORTANT]
> Before creating any `plan_*.md`, `handoff_*.md`, `walkthrough_*.md`, or `investigation_*.md` artifact,
> read `.agent/rules/artifact-protection.md`. Key rules:
> - Use **feature-specific naming** (e.g., `plan_data_storage.md`, NOT `implementation_plan.md`)
> - **Never overwrite** without checking existing content first
> - **Never rename** artifacts via PowerShell — delete and recreate instead
