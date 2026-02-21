# Validation Report: Sim Engine Display Fixes

**Date:** 2026-02-20
**Validator:** Audit Validator
**Reference:** `backend_status_sim_display_fixes.md`

---

## Claim Verification Table

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | `partial_exit_prices` column exists in model | **PASS** | `warrior_db.py:79` — `partial_exit_prices = Column(Text, nullable=True)` |
| 2 | Partial prices tracked in JSON during exit | **PASS** | `warrior_db.py:413-416` — `existing_partials.append({"price": exit_price, "qty": quantity_exited})` |
| 3 | `entry_time_override` param on `log_warrior_entry` | **PASS** ⚠️ | `warrior_db.py:292` — `entry_time_override: datetime = None` (report said line 284) |
| 4 | `exit_time_override` param on `log_warrior_exit` | **PASS** ⚠️ | `warrior_db.py:385` — `exit_time_override: datetime = None` (report said line 376) |
| 5 | Sim clock passed in entry | **PASS** | `warrior_engine_entry.py:1243-1247` — `entry_time_override=(engine._sim_clock.current_time if getattr(engine, '_sim_clock', None) else None)` |
| 6 | Sim clock passed in exit callback | **PASS** | `sim_context.py:346` — `exit_time_override=ctx.clock.current_time` (report said 347, off by 1) |
| 7 | `avg_exit_price` in trade result dict | **PASS** ⚠️ | `sim_context.py:683` — `"avg_exit_price": _compute_avg_exit_price(wt)` (report said line 632) |
| 8 | Dual P&L docstring exists | **PASS** ⚠️ | `sim_context.py:582-599` — Docstring on `_run_single_case_async` (report said line 548) |

---

## Additional Checks

### Backward Compatibility

**Claim:** `entry_time_override` and `exit_time_override` default to `None`, so live trading is unaffected.

**Verification:**
- `warrior_db.py:292` — `entry_time_override: datetime = None` ✅
- `warrior_db.py:385` — `exit_time_override: datetime = None` ✅
- `warrior_db.py:305` — `entry_time=entry_time_override or now_utc()` — falls back to `now_utc()` when None ✅
- `warrior_db.py:398` — `exit_time=exit_time_override or now_utc()` — falls back to `now_utc()` when None ✅

**Result:** **PASS** — Live trading callers don't pass these params, so `now_utc()` is always used in production.

---

### `_compute_avg_exit_price` Edge Cases

**Verification:** (`sim_context.py:498-547`)

| Edge Case | Handled? | Code |
|-----------|----------|------|
| No exit at all (`exit_price` is None) | ✅ | Line 513: `if not exit_price_str: return None` |
| No partials (just final exit) | ✅ | Line 520: `if not partial_json: return round(final_exit_price, 2)` |
| Empty JSON string `"[]"` | ✅ | Line 528: `if not partials: return round(final_exit_price, 2)` |
| Malformed JSON | ✅ | Line 525: `except (json.JSONDecodeError, TypeError): return round(final_exit_price, 2)` |
| Missing `price`/`qty` fields in partials | ❌ | Line 535: `p["price"] * p["qty"]` would raise `KeyError` — not handled |
| `total_qty <= 0` after computation | ✅ | Line 544: guard returns `final_exit_price` |

**Result:** **PASS** with minor note — missing field `KeyError` is unlikely in practice since `existing_partials.append({"price": ..., "qty": ...})` always writes both fields, but a defensive `p.get("price", 0)` would be more robust.

---

### EOD Exit Callback

**Verification:** `sim_context.py:650-656` — EOD close also passes `exit_time_override=ctx.clock.current_time` ✅

---

## Test Suite

```
757 passed, 4 skipped, 3 deselected, 0 failed (136.27s)
```

**Result:** **PASS** — No regressions.

---

## Line Number Discrepancies

The report's claimed line numbers were off for 4 of 8 claims:

| Claim | Reported Line | Actual Line | Delta |
|-------|--------------|-------------|-------|
| 3 | 284 | 292 | +8 |
| 4 | 376 | 385 | +9 |
| 7 | 632 | 683 | +51 |
| 8 | 548 | 582 | +34 |

This is cosmetic — likely the report was written against an earlier revision of the files. All code patterns match exactly.

---

## Quality Rating

**HIGH** — All 8 claims verified. Code exists at the claimed locations (with minor line drift). Backward compatibility confirmed. Edge cases handled. Test suite passes with zero failures.
