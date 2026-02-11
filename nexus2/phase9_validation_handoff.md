# Phase 9 Validation Handoff

## Context

The Phase 9 auditor will investigate 5 anomalies (C1-C5) from the sequential batch results. Your job is to validate their findings.

## Input

Read the auditor's report at `nexus2/phase9_audit_report.md`.

## Validation Tasks

For each claim (C1-C5) in the audit report:

1. **Re-run the verification commands** independently
2. **Check the auditor's evidence** — does their output match what they claim?
3. **Assess their root cause analysis** — is it logically sound?
4. **Grade each finding**: CONFIRMED / PARTIALLY CONFIRMED / DISPROVED

## Special Focus Areas

### Cross-Case Contamination (C1)
- Trace the EXACT query path used to collect trades in the batch loop
- Verify whether `purge_sim_trades()` clears ALL sim trades or just some
- Check if the first case (LCFY) could have leftover trades from a previous batch

### P&L Source Mismatch (C5)
- Verify whether `realized_pnl` and `trades` come from the same source
- If not, identify both sources and which one is authoritative

## Report

Write to `nexus2/phase9_validation_report.md`:

```markdown
## Phase 9 Validation Report

### Claims Validated
| # | Auditor Claim | Verdict | Evidence |
|---|--------------|---------|----------|
| C1 | [claim] | CONFIRMED/DISPROVED | [command + output] |
| C2 | [claim] | CONFIRMED/DISPROVED | [command + output] |
| C3 | [claim] | CONFIRMED/DISPROVED | [command + output] |
| C4 | [claim] | CONFIRMED/DISPROVED | [command + output] |
| C5 | [claim] | CONFIRMED/DISPROVED | [command + output] |

### Overall Rating
HIGH / MEDIUM / LOW

### Additional Findings
[Anything the auditor missed]
```
