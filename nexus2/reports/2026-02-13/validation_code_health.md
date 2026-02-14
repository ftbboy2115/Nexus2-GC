# Code Health Audit — Validation Report

**Date**: 2026-02-13  
**Validator**: Audit Validator Agent  
**Audit Report**: `nexus2/reports/2026-02-13/audit_code_health.md`  
**Handoff**: `handoff_validator_code_health.md`

---

## Claim Verification Table

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| V1 | 12 functions have zero callers | ✅ **PASS** | All 12 returned exactly 1 hit (definition only). See details below. |
| V2 | 6 shadowed duplicates in `warrior_engine_entry.py` | ✅ **PASS** | AST analysis returned exactly 6: `check_active_market`, `check_falling_knife`, `check_high_volume_red_candle`, `check_micro_pullback_entry`, `check_volume_confirmed`, `check_volume_expansion` |
| V3 | 3 test-only functions | ✅ **PASS** | All 3 have exactly 1 non-test hit (their def). `_enter_position`: 15 test calls. `process_signal`: 1 test call. `log_nac_stop_moved`: 1 test call. |
| V4 | VWAP indicator duplication (L202-210 ≡ L301-309) | ⚠️ **PARTIAL** | Logic is identical but comment line differs (`"# VWAP indicator (above = green...)"` vs `"# VWAP"`). Functionally duplicate, not byte-identical. |
| V5 | Route model import in `services.py` L27 | ⚠️ **PASS + FINDING** | L27 confirmed. **Auditor missed a second violation at L236**: `from nexus2.api.routes.automation_state import get_recent_exit_symbols` |
| V6 | Direct `db.commit()` in domain files | ✅ **PASS** | Confirmed at exact lines: `ai_catalyst_validator.py:844`, `ai_catalyst_validator.py:937`, `trade_event_service.py:330` |
| V7 | Line count inventory accuracy | ✅ **PASS** | All 5 spot-checked files are **exact** matches: `warrior_engine.py` 759, `warrior_types.py` 174, `warrior_monitor_exit.py` 1176, `warrior_engine_entry.py` 1438, `services.py` 399 |

---

## Detailed Evidence

### V1: Dead Functions — All 12 Confirmed

Each function returned exactly **1 hit** (its own definition), confirming zero callers:

| # | Function | File:Line | Hits |
|---|----------|-----------|:----:|
| 1 | `_check_orb_setup` | `warrior_engine.py:615` | 1 |
| 2 | `_check_profit_target` | `warrior_monitor_exit.py:618` | 1 |
| 3 | `_scale_into_existing_position` | `warrior_engine_entry.py:833` | 1 |
| 4 | `ai_validate_catalyst` | `ai_catalyst_validator.py:485` | 1 |
| 5 | `classify_headlines` | `catalyst_classifier.py:263` | 1 |
| 6 | `get_cached_headlines` | `ai_catalyst_validator.py:226` | 1 |
| 7 | `get_days_since_split` | `reverse_split_service.py:216` | 1 |
| 8 | `get_score_boost` | `reverse_split_service.py:250` | 1 |
| 9 | `get_symbols_with_catalyst_type` | `catalyst_search_service.py:116` | 1 |
| 10 | `initialize_engine` | `services.py:381` | 1 |
| 11 | `queue_comparison` | `ai_catalyst_validator.py:731` | 1 |
| 12 | `reset_daily_fails` | `warrior_engine.py:670` | 1 |

### V4: VWAP Duplication — Functional Duplicate

The two blocks differ only in the comment line:
- Block 1 (L202): `# VWAP indicator (above = green, at = yellow, below = red)`
- Block 2 (L301): `# VWAP`

All 8 lines of logic (the `if/elif/else` chain) are byte-identical.

**Verdict**: Auditor's claim of duplication is correct in substance. The `Identical: True` assertion is technically false due to the comment, but this does not change the recommendation to extract a helper.

### V5: Layer Violation — Second Violation Found

The auditor documented:
- **L27**: `from nexus2.api.routes.scanner import run_scanner, ScannerRunRequest` ✅ Confirmed

The validator discovered an **additional** layer violation the auditor missed:
- **L236**: `from nexus2.api.routes.automation_state import get_recent_exit_symbols`

> [!WARNING]
> This second import is inside `create_unified_scanner_callback` and represents another domain-to-API layer violation that should be added to the refactoring backlog.

---

## Overall Rating

**HIGH** — All claims verified. The audit is thorough and accurate. Two minor notes:

1. V4 (VWAP duplication) is a functional duplicate, not byte-identical (comment differs) — this doesn't change the recommendation
2. V5 has a **missed second layer violation** at `services.py:236` — this should be added to the cleanup backlog

---

## Recommendations

1. **All V1 dead functions are safe to delete** — zero callers confirmed
2. **V2 shadowed duplicates should be priority 1 cleanup** — 380+ lines of dead code
3. **Add `services.py:236` import** to the layer violation list alongside the L27 violation
4. **V3 test-only functions**: Consider updating tests to use new entry paths before removing `_enter_position`
