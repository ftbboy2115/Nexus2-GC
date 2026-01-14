---
trigger: always_on
---

# Windows Environment Rules

You are operating in a **Windows environment with PowerShell**. Always remember:

## Command Syntax
- Do NOT use Linux-style command chaining (`&&`, `||`)
- Do NOT use `curl` — use `Invoke-RestMethod` or `Invoke-WebRequest`
- Do NOT use `cat` — use `Get-Content`
- Do NOT use [rm](cci:1://file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/frontend/src/pages/automation.tsx:364:4-368:5) — use `Remove-Item`
- Do NOT use `grep` — use `Select-String`
- Do NOT use [ls](cci:1://file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/api/routes/scheduler_routes.py:423:0-436:5) — use `Get-ChildItem` or `dir`
- Use PowerShell syntax for loops, conditionals, and piping

## Python One-Liners
- Avoid complex Python one-liners with mixed quotes in PowerShell
- PowerShell escapes quotes differently than bash — prefer creating [.py](cci:7://file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/check_inbs.py:0:0-0:0) script files for anything beyond trivial commands

## Path Handling
- Use backslashes (`\`) in Windows paths, or forward slashes in Python/Node contexts
- Be aware of spaces in paths — quote or escape appropriately

## Environment Variables
- Use `$env:VAR_NAME` syntax in PowerShell, not `$VAR_NAME`