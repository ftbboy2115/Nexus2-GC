---
trigger: always_on
description: Shared rules inherited by all specialist agents — Windows environment and document output standards
---

# Shared Agent Standards

These rules apply to ALL specialist agents. Do not duplicate in individual rule files.

---

## 🚨 Windows Environment (CRITICAL)

> [!CAUTION]
> This project runs on **Windows with PowerShell**. Linux commands will FAIL.

| ❌ Do NOT Use | ✅ Use Instead |
|--------------|---------------|
| `grep` | `Select-String -Path "file" -Pattern "pattern"` |
| `grep -rn` | `Select-String -Path "dir\*" -Pattern "pattern" -Recurse` |
| `cat` | `Get-Content` |
| `curl` | `Invoke-RestMethod` or `Invoke-WebRequest` |
| `&&` (chaining) | `;` or separate commands |
| `rm` | `Remove-Item` |

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
