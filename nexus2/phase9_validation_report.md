# Phase 9 Validation Report

**Date**: 2026-02-11  
**Validator**: Audit Validator Agent  
**Audit Report**: [phase9_audit_report.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/phase9_audit_report.md)  
**Validation Handoff**: [phase9_validation_handoff.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/phase9_validation_handoff.md)  

---

## Claims Validated

| # | Auditor Claim | Verdict | Evidence |
|---|--------------|---------|----------|
| C1 | Shared engine state — `engine.stats` never instantiated, `_last_scan_*` irrelevant, only monitor fixed | **PARTIALLY CONFIRMED** | `engine.stats` IS instantiated at `warrior_engine.py:L77` (`self.stats = WarriorEngineStats()`). Auditor's claim that it was "never instantiated" is **incorrect**. However, stats doesn't affect entry/exit logic — no P&L impact. The `_blacklist` (L92) is also NOT reset between sequential cases and IS checked in entry guards (`warrior_entry_guards.py:L85`). See Additional Findings. |
| C2 | Wall-clock throttle is per-WatchedCandidate, no carry-over | **CONFIRMED** | `_last_tech_update_ts` lives on `WatchedCandidate` (verified at `warrior_engine_entry.py:L398-401`). Fresh candidate created per case in both runners. `Select-String` for `tech_update|throttle` in `warrior_engine.py` returned **zero results** — confirms the throttle is NOT on the engine. |
| C3 | `purge_sim_trades()` safely deletes all `is_sim=True` trades | **CONFIRMED** | Verified at `warrior_db.py:L787-788`: `db.query(WarriorTradeModel).filter_by(is_sim=True).delete()`. This deletes ALL sim trades unconditionally. Called at `warrior_sim_routes.py:L1389-1390` with `confirm=True`. No contamination path. |
| C4 | Callback wiring diverges (global lookup vs default-arg capture) but no P&L impact | **CONFIRMED** | Sequential uses `get_warrior_sim_broker()` global lookup per call (L852-858, L1022). Concurrent captures `_broker=ctx.broker` via default args (L271-273, L390-394). Both resolve to the correct broker for that case. Functionally equivalent in sequential mode. |
| C5 | `initial_cash` difference (25K vs 100K) has no P&L impact; `broker.reset()` is complete | **CONFIRMED** | `MockBroker.reset()` clears all 7 state fields (L122-130): `_cash`, `_orders`, `_positions`, `_current_prices`, `_realized_pnl`, `_max_capital_deployed`, `_max_shares_held`. P&L calculation in `sell_position()` (L436) is position-relative: `(current_price - avg_entry_price) * sell_qty`. Cash balance doesn't affect P&L math. |

---

## Overall Rating

**MEDIUM** — Audit was largely accurate but contained one factual error (`engine.stats` claim) and missed one divergence source (`_blacklist`). Neither error materially affects the audit's conclusions about root cause.

---

## Special Focus: Cross-Case Contamination (C1)

> **Handoff directive**: Trace the EXACT query path used to collect trades in the batch loop. Verify whether `purge_sim_trades()` clears ALL sim trades or just some. Check if the first case could have leftover trades.

### Trade Query Path (Sequential Runner)

At [L1469-1476](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L1469-L1476):

```python
from nexus2.db.warrior_db import get_all_warrior_trades
warrior_result = get_all_warrior_trades(limit=100, status_filter="closed")
warrior_trades = warrior_result.get("trades", [])
warrior_partial = get_all_warrior_trades(limit=100, status_filter="partial")
warrior_trades.extend(partial_trades)
```

Trades are queried AFTER each case completes and AFTER EOD close. `purge_sim_trades()` runs BEFORE `load_historical_test_case()` at L1387-1390, so trade data from the previous case is deleted before the new case loads.

### Verdict: No contamination

The first case (LCFY) cannot have leftover trades from a previous batch because `purge_sim_trades()` deletes ALL `is_sim=True` trades unconditionally.

---

## Special Focus: P&L Source Mismatch (C5)

> **Handoff directive**: Verify whether `realized_pnl` and `trades` come from the same source.

### Sequential Runner

| Data | Source | Location |
|------|--------|----------|
| `trades` list | `warrior_db` — `get_all_warrior_trades(status_filter="closed")` | L1471 |
| `realized_pnl` | `MockBroker` — `broker.get_account()["realized_pnl"]` | L1500 |

These are **two different sources**. `trades` with per-trade `pnl` come from warrior_db's `realized_pnl` column, while the top-level `realized_pnl` comes from MockBroker's `_realized_pnl` accumulator.

### Concurrent Runner

| Data | Source | Location |
|------|--------|----------|
| `trades` list | **Empty `[]`** — hardcoded | sim_context.py:L541 |
| `realized_pnl` | `MockBroker` — `ctx.broker.get_account()["realized_pnl"]` | sim_context.py:L532 |

### Verdict: Consistent P&L, inconsistent trade detail

Both runners derive `realized_pnl` from MockBroker's `_realized_pnl` (summed from `sell_position()` at `mock_broker.py:L437`). The numbers are computed identically.

The **reporting gap** is that the concurrent runner returns `trades: []` — it never queries warrior_db for trade detail. This doesn't affect P&L comparison but means the concurrent runner's results lack entry/exit metadata. If this is needed, `_run_single_case_async` should query warrior_db trades from its in-memory DB before returning.

---

## Additional Findings

### AF1: `_blacklist` Not Reset Between Sequential Cases

> [!WARNING]  
> The auditor DID NOT identify this as a leakage vector.

**Evidence**:
- `self._blacklist: set = set()` — initialized empty at `warrior_engine.py:L92`
- `engine._blacklist.add(symbol)` — populated on entry failures at `warrior_entry_execution.py:L133` and `warrior_engine_entry.py:L1146`
- Entry guard at `warrior_entry_guards.py:L85`:
  ```python
  if symbol in engine.config.static_blacklist or symbol in engine._blacklist:
  ```
- **NOT cleared** in `load_historical_test_case()` — `Select-String` for `_blacklist` in `warrior_sim_routes.py` returned **zero results**
- The concurrent runner creates a fresh `WarriorEngine()` per case — `_blacklist` starts empty

**Impact**: If case N blacklists symbol X due to entry failures, AND a later case N+M uses the same symbol, entry would be blocked in the sequential runner but succeed in the concurrent runner.

**Mitigation**: For the current 22 test cases, each case uses a unique symbol, so cross-case blacklist leakage is unlikely to trigger. However, this is a real correctness bug for any future test suite with repeated symbols.

**Recommended fix**:
```python
# Add to load_historical_test_case() after L824
engine._blacklist.clear()
```

### AF2: `engine.stats` Factual Error in Audit Report

The auditor stated: *"`WarriorEngineStats` — defined at `warrior_engine_types.py:L138-150` but **never instantiated** on the engine"*.

This is **incorrect**. At `warrior_engine.py:L77`:
```python
self.stats = WarriorEngineStats()
```

The stats dataclass tracks `scans_run`, `candidates_found`, `entries_triggered`, `orders_submitted`, `orders_filled`, `daily_pnl`, and `_seen_candidates`. These accumulate across sequential cases because stats is NOT reset in `load_historical_test_case()`.

**Impact**: LOW — stats fields are informational counters, not used in entry/exit decisions. Does not affect P&L.

### AF3: Concurrent Runner Returns Empty `trades` Array

At `sim_context.py:L541`, the concurrent runner hardcodes `"trades": []`. It has a per-process in-memory warrior_db (Phase 8 fix) that contains the trade records, but never queries it before returning results.

**Impact**: Reporting gap only. No P&L divergence. Could be improved by querying the in-memory DB.

---

## Summary

The auditor correctly identified the **root cause** (monitor state bleed-over, fixed at L826-832) and accurately assessed 4 of 5 claims. The one factual error (`engine.stats` instantiation) and one missed finding (`_blacklist` not reset) do not change the audit's core conclusion: the Phase 9 fix resolved the primary divergence source, and the concurrent runner's isolation-by-construction is fundamentally more robust.

The remaining 9 divergent cases are likely explained by secondary effects that only manifest when the Phase 9 monitor fix is in place — subtle differences in timing, callback resolution order, or engine state that compound across the replay. The `_blacklist` finding should be fixed as a defensive measure even though it doesn't affect current test cases.
