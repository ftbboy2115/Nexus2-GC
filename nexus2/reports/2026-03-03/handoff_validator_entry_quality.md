# Audit Validator Handoff: Entry Quality Research Verification

**Date:** 2026-03-03 10:43 ET  
**From:** Coordinator  
**To:** Audit Validator  
**Source Report:** `nexus2/reports/2026-03-03/research_entry_quality_gap.md`  
**Output:** `nexus2/reports/2026-03-03/validation_entry_quality_gap.md`

---

## Claims to Verify

### Claim 1: Each batch test case runs in COMPLETE ISOLATION (single stock, single day)

**Report says:** `sim_context.py` creates per-process in-memory SQLite DB and puts exactly 1 symbol in the watchlist.  
**Verify with:**
```powershell
Select-String -Path "C:\Dev\Nexus\nexus2\adapters\simulation\sim_context.py" -Pattern "sqlite://|_watchlist\[symbol\]|watchlist.clear"
```
**Check:** Does the code at the cited lines match the claim? Is there any path where multiple symbols could be added?

---

### Claim 2: Top 4 cases produce 52% of total P&L ($183,714 of $355,039)

**Report says:** NPT ($68,021), BATL×2 ($49,636 + $26,757 = $76,393), ROLR ($45,723) = $190,137... wait, that's $190,137, not $183,714. **Check the math.**  
**Verify with:**
```powershell
Get-Content "C:\Dev\Nexus\nexus2\reports\gc_diagnostics\baseline.json" | python3 -c "import sys,json; data=json.load(sys.stdin); cases=sorted(data.get('cases',data.get('results',[])), key=lambda x: x.get('pnl',x.get('bot_pnl',0)), reverse=True); [print(f'{c.get(\"case_name\",\"?\"):40s} ${c.get(\"pnl\",c.get(\"bot_pnl\",0)):>10,.2f}') for c in cases[:5]]"
```
**Check:** Do the actual P&L numbers in baseline.json match the report's table? Does 52% math check out?

---

### Claim 3: `score_pattern()` receives ZERO real-time data — all inputs are static

**Report says:** `add_candidate()` at `warrior_engine_entry.py:500-525` passes only scanner metadata + hard-coded confidence to `score_pattern()`.  
**Verify with:**
```powershell
Select-String -Path "C:\Dev\Nexus\nexus2\domain\automation\warrior_engine_entry.py" -Pattern "score_pattern\(" -Context 0,10
```
**Check:** Are all 6 args truly static? Confirm: `volume_ratio` comes from scanner, `pattern_confidence` is hard-coded, `catalyst_strength` from scanner, `spread_pct` from scanner. Is there any path where dynamic data is injected?

---

### Claim 4: `watched.entry_snapshot` (MACD, VWAP, EMA) is computed BEFORE scoring but NOT passed to `score_pattern()`

**Report says:** `entry_snapshot` is set in `_check_macd_gate()` at `warrior_entry_guards.py:264-265`, and logged at entry in `warrior_entry_execution.py:520-529`, but never fed to the scoring function.  
**Verify with:**
```powershell
Select-String -Path "C:\Dev\Nexus\nexus2\domain\automation\warrior_entry_guards.py" -Pattern "entry_snapshot"
Select-String -Path "C:\Dev\Nexus\nexus2\domain\automation\warrior_entry_scoring.py" -Pattern "snapshot|macd|vwap|ema"
```
**Check:** Is `entry_snapshot` populated? Is it ever referenced in `warrior_entry_scoring.py`?

---

### Claim 5: Re-entry cooldown in sim mode is 10 minutes

**Report says:** Code at `warrior_entry_guards.py:166-176` implements sim-mode cooldown using `_reentry_cooldown_minutes`.  
**Verify with:**
```powershell
Select-String -Path "C:\Dev\Nexus\nexus2\domain\automation\warrior_entry_guards.py" -Pattern "cooldown_minutes|reentry_cooldown"
Select-String -Path "C:\Dev\Nexus\nexus2\domain\automation\warrior_types.py" -Pattern "reentry_cooldown"
```
**Check:** What's the default value of `_reentry_cooldown_minutes`? Is it actually 10?

---

### Claim 6: `check_volume_expansion()` exists but is NOT wired to scoring

**Report says:** The function exists in `warrior_engine_entry.py` but is never called from the entry flow.  
**Verify with:**
```powershell
Select-String -Path "C:\Dev\Nexus\nexus2\domain\automation" -Pattern "check_volume_expansion" -Include "*.py"
```
**Check:** Is the function called anywhere? If so, is the result used for scoring or just logging?

---

## Validation Report Format

```markdown
## Validation Report: Entry Quality Research

### Claims Verified
| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | [claim] | PASS/FAIL | [command + output] |

### Overall Rating
- **HIGH**: All claims verified
- **MEDIUM**: Minor issues
- **LOW**: Major issues requiring rework

### Failures (if any)
- Claim #X: Expected [X], got [Y]
```
