# Handoff: Audit Validator — Verify Exit Fill Fixes (Track A)

@agent-audit-validator.md

## Context

Two rounds of Backend Specialist changes were made to fix exit fill recording bugs. These changes are already committed (`025f4d4`) and deployed to VPS. Your job is to independently verify every claim.

## Claims to Verify

### Round 1 (Backend Specialist, earlier session)

| # | Claim | File | Line | Verification Command |
|---|-------|------|------|---------------------|
| 1 | `get_order()` replaced with `get_order_status()` | `warrior_callbacks.py` | ~L482 | `Select-String -Path "nexus2\api\routes\warrior_callbacks.py" -Pattern "get_order_status"` |
| 2 | `filled_avg_price` replaced with `avg_fill_price` | `warrior_callbacks.py` | ~L483 | `Select-String -Path "nexus2\api\routes\warrior_callbacks.py" -Pattern "avg_fill_price"` |
| 3 | Poll retries increased from 4 to 8 | `warrior_callbacks.py` | ~L479 | `Select-String -Path "nexus2\api\routes\warrior_callbacks.py" -Pattern "range(8)"` |
| 4 | Error handling changed from `break` to `continue` | `warrior_callbacks.py` | ~L489 | `Select-String -Path "nexus2\api\routes\warrior_callbacks.py" -Pattern "continue"` (in poll loop) |
| 5 | Fallback warning added | `warrior_callbacks.py` | ~L492-493 | `Select-String -Path "nexus2\api\routes\warrior_callbacks.py" -Pattern "Fill poll failed"` |
| 6 | Slippage labels fixed for sells (positive = better) | `trade_event_service.py` | ~L672-675 | `Select-String -Path "nexus2\domain\automation\trade_event_service.py" -Pattern "better"` |
| 7 | Entry `filled_avg_price` → `avg_fill_price` | `warrior_entry_execution.py` | ~L212 | `Select-String -Path "nexus2\domain\automation\warrior_entry_execution.py" -Pattern "avg_fill_price"` |
| 8 | Entry `filled_qty` → `filled_quantity` | `warrior_entry_execution.py` | ~L215 | `Select-String -Path "nexus2\domain\automation\warrior_entry_execution.py" -Pattern "filled_quantity"` |

### Round 2 (Backend Specialist, this session)

| # | Claim | File | Line | Verification Command |
|---|-------|------|------|---------------------|
| 9 | `order.id` replaced with `order.broker_order_id` | `warrior_callbacks.py` | ~L477 | `Select-String -Path "nexus2\api\routes\warrior_callbacks.py" -Pattern "broker_order_id"` |
| 10 | Upward stale guard: logs warning, uses fresh quote | `warrior_callbacks.py` | ~L438-443 | `Select-String -Path "nexus2\api\routes\warrior_callbacks.py" -Pattern "using fresh quote"` |
| 11 | Downward stale guard: clips to signal when >10% below | `warrior_callbacks.py` | ~L445-451 | `Select-String -Path "nexus2\api\routes\warrior_callbacks.py" -Pattern "signal_price \* 0.90"` |

### Negative Checks (verify old patterns are GONE)

| # | Claim | File | Verification Command |
|---|-------|------|---------------------|
| 12 | No `get_order(` calls remain (only `get_order_status`) | `warrior_callbacks.py` | `Select-String -Path "nexus2\api\routes\warrior_callbacks.py" -Pattern "\.get_order\(" -NotMatch "get_order_status"` |
| 13 | No `order.id` remains (only `broker_order_id`) | `warrior_callbacks.py` | `Select-String -Path "nexus2\api\routes\warrior_callbacks.py" -Pattern "order\.id "` |
| 14 | No `filled_avg_price` remains | `warrior_callbacks.py` | `Select-String -Path "nexus2\api\routes\warrior_callbacks.py" -Pattern "filled_avg_price"` (should return 0 matches) |

### Functional Check

| # | Claim | Verification Command |
|---|-------|---------------------|
| 15 | Import succeeds | `cd nexus2; python -c "from api.routes.warrior_callbacks import create_execute_exit; print('OK')"` |
| 16 | No new test failures | `cd nexus2; python -m pytest tests/ -v --no-header --tb=line 2>&1 | Select-String "FAILED"` |

## Output

Write your validation report to: `nexus2/reports/2026-02-18/validation_exit_fill_fixes.md`

Use the standard format:

```markdown
## Validation Report: Exit Fill Fixes (Track A)

### Claims Verified
| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | [claim] | PASS/FAIL | [command + output] |

### Overall Rating
- HIGH / MEDIUM / LOW

### Failures (if any)
```
