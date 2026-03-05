# Audit Validator Handoff: Tiebreaker Review

**Date:** 2026-03-03 13:55 ET  
**From:** Coordinator  
**To:** Audit Validator (independent second opinion)  
**Context:** A Backend Specialist claimed $0 P&L change. A first Validator found -$9,944. The P&L regression is confirmed (Clay ran the batch test: PAVM -$7,525, MLEC -$1,422, MNTS -$997). We need independent verification of the first validator's STRUCTURAL claims.

**First validator's report:** `nexus2/reports/2026-03-03/validation_missing_factors_fix.md`  
**Output:** `nexus2/reports/2026-03-03/validation_tiebreaker_structural.md`

---

## Claims to Independently Verify

### Claim A: HOD proximity is structurally always 1.0 on first entry

The first validator claims `recent_high` is set to `current_price` before scoring runs, making HOD proximity always 1.0 (at HOD) on first entry.

**Verify:** Trace where `recent_high` (or whatever field HOD proximity reads) is first set. Is it set before or after `score_pattern()` runs? Does it always equal `current_price` at scoring time?

```powershell
Select-String -Path "C:\Dev\Nexus\nexus2\domain\automation\warrior_engine_entry.py" -Pattern "hod|recent_high|high_of_day" -CaseSensitive:$false
Select-String -Path "C:\Dev\Nexus\nexus2\domain\automation\warrior_entry_scoring.py" -Pattern "hod|high_of_day" -CaseSensitive:$false
```

### Claim B: Volume expansion computation causes performance regression

Runtime went from 102s → 236s (2.3x slower). Is the vol expansion computation doing extra API calls or fetching data that wasn't fetched before?

```powershell
Select-String -Path "C:\Dev\Nexus\nexus2\domain\automation\warrior_entry_helpers.py" -Pattern "vol_expansion|cached_vol" -Context 5,5
```

### Claim C: Which specific change caused the -$9,944 regression?

Was it HOD proximity (weight rebalance from 35%→33% pattern confidence), vol expansion wiring, or both? The first validator doesn't specify which.

**Note:** A revert specialist is already working on removing both. This tiebreaker is for the record — understanding root cause.

---

## Report Format

For each claim: CONFIRMED / DISPUTED / UNABLE TO VERIFY, with evidence.
