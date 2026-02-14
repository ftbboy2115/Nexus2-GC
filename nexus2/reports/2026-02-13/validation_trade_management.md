# Validation Report: Trade Management Audit

**Date**: 2026-02-13  
**Validator**: Audit Validator (AI)  
**Audit Report**: `nexus2/reports/2026-02-13/audit_trade_management.md`  
**Handoff**: `handoff_validator_trade_mgmt.md`

---

## Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| V1 | `base_hit_candle_trail_enabled` defaults to `True`, activation at +10¢ | **PASS** | `warrior_types.py` L121: `base_hit_candle_trail_enabled: bool = True`. Also L170: `candle_trail_stop: Optional[Decimal] = None`. Auditor cited L114 — line shifted to L121, content matches. |
| V2 | `enable_time_stop` defaults to `False`, `_check_time_stop` wired into `evaluate_position` | **PASS** | `warrior_types.py` L83: `enable_time_stop: bool = False`. `warrior_monitor_exit.py` L319: `async def _check_time_stop(`, L341: `if not s.enable_time_stop:`, L958: `signal = await _check_time_stop(...)`. Auditor cited L957-960 — actual wiring at L958, content matches. |
| V3 | `base_hit_stop_cents` wired in `_create_new_position` | **PASS** | `warrior_monitor.py` L401: comment, L405: `mental_stop = entry_price - s.base_hit_stop_cents / 100`, L408: log string. Matches auditor's L401-409 exactly. |
| V4 | 8 exit checks in documented order | **PASS** | Confirmed 8 `_check_*` calls in order: `_check_after_hours_exit` → `_check_spread_exit` → `_check_time_stop` → `_check_stop_hit` → `_check_candle_under_candle` → `_check_topping_tail` → `_check_base_hit_target` → `_check_home_run_exit`. Matches auditor's C4 table exactly. |
| V5 | `_check_profit_target` is dead code | **PASS** | Only 1 reference found: `L618: async def _check_profit_target(`. No callers in `evaluate_position` or anywhere else. Confirmed orphaned. |
| V6 | `BREAKOUT_FAILURE` enum never generated as exit signal | **PASS** | 3 references found: `warrior_types.py:27` (enum def), `warrior_monitor_exit.py:1058` (exit_reason_map), `warrior_monitor_exit.py:1162` (stop_reasons set). Zero instances of `WarriorExitSignal(...BREAKOUT_FAILURE...)`. No `_check_breakout_failure` function exists. Confirmed unreachable. |
| V7 | `breakout_hold_threshold` defined but never read | **PASS** | Only 1 hit across all `nexus2/domain/automation/*.py`: `warrior_types.py:L85: breakout_hold_threshold: float = 0.5`. No code reads this setting. Confirmed dead. |
| V8 | `topping_tail_grace_seconds` used via `getattr` but missing from settings | **PASS** | `warrior_monitor_exit.py` L572: `grace_seconds = getattr(s, 'topping_tail_grace_seconds', 120)`. `warrior_types.py`: `NOT FOUND`. Always falls back to hardcoded 120. Confirmed implicit. |

---

## Line Number Discrepancies

| Claim | Auditor Line | Actual Line | Impact |
|-------|-------------|-------------|--------|
| V1 | L114 | L121 | None — content matches, lines shifted (likely from prior edits) |
| V2 | L319-372 (def), L957-960 (wiring) | L319 (def), L958 (wiring) | None — negligible offset |
| V3 | L401-409 | L401-408 | None — matches |

All line discrepancies are minor shifts with no impact on claim accuracy.

---

## Overall Rating

**HIGH** — All 8 claims verified. Code matches auditor's descriptions exactly. Line number offsets are trivial and expected from incremental edits. No rework required.

---

## Summary

The trade management audit report is **accurate and trustworthy**. All findings regarding active features (candle trail, base_hit_stop_cents), disabled features (time stop), exit path ordering, dead code (`_check_profit_target`, `BREAKOUT_FAILURE`, `breakout_hold_threshold`), and implicit settings (`topping_tail_grace_seconds`) are independently confirmed.
