# Runner Divergence Audit — Validation Report

**Validation Date**: 2026-02-11  
**Validator**: Audit Validator Agent  
**Report Under Validation**: `runner_divergence_audit_report.md`

---

## Claim Verification Table

| # | Claim | Report Verdict | Validation Result | Evidence |
|---|-------|---------------|-------------------|----------|
| C1 | Sequential uses `get_engine()` singleton; concurrent creates fresh `WarriorEngine` per case | ✅ CONFIRMED | **PASS** | `get_engine` appears 19x in warrior_sim_routes.py (L144,150,351,356,370,374,450,574,664,709,817,1112,1117,1346,1347,1755,1757,1775,1780); `WarriorEngine(` at sim_context.py L47 |
| C2 | MockMarketData uses singleton+reset (seq) vs fresh instance (conc) | ✅ CONFIRMED | **PASS** | Sequential: `get_mock_market_data()` at L743-746; Concurrent: `MockMarketData()` at sim_context.py L198 |
| C3 | `set_sim_mode_ctx` never called in sequential path | ✅ CONFIRMED | **PASS** | `Select-String` returns **zero results** for `set_sim_mode_ctx` in warrior_sim_routes.py; sim_context.py L484-486 calls it |
| C4 | Sequential callbacks close over global lookups; concurrent captures via default args | ✅ CONFIRMED | **PASS** | Sequential L843: `broker = get_warrior_sim_broker()`; Concurrent L271: `_broker=ctx.broker` |
| C5 | Sequential uses `reset_simulation_clock()` global; concurrent creates fresh clock | ✅ CONFIRMED | **PASS** | Sequential L730; Concurrent: sim_context.py L34 |
| C6 | `time.time()` used for 60s throttle (wall clock, not sim clock) | ✅ CONFIRMED | **PASS** | warrior_engine_entry.py L399: `_time.time() - _last >= 60`; L401: `watched._last_tech_update_ts = _time.time()` |
| C6-Adv | No sim-clock-aware throttle path exists | ✅ CONFIRMED | **PASS** | Zero results for `_sim_clock` or `get_time_string` in warrior_engine_entry.py |
| C7 | `_pending_entries` and `_symbol_fails` NEVER cleared between sequential cases | ❌ REFUTED | **⛔ FAIL** | Both ARE cleared at L823-824 inside `load_historical_test_case()`, which is called per case in the batch loop at L1387 |
| C7 | `_watchlist` only "partially reset" | ❌ REFUTED | **⛔ FAIL** | `engine._watchlist.clear()` at L822 is a FULL clear, not partial |
| C7 | `stats` never reset between cases | Claimed ❌ | **PASS** (unverified — no `stats` reset found in L810-833, plausible claim) |

---

## Critical Failure: C7 Sub-Claims Are Wrong

The audit report's **primary root cause** (C7: Engine State Bleed-Over) is built on claims that are **factually incorrect**.

### What the Report Claims (L201-208)

| State Field | Report Claim |
|------------|-------------|
| `_watchlist` | "Partially (set to new symbol, but old entries may persist)" |
| `_pending_entries` | "❌ Never reset" |
| `_symbol_fails` | "❌ Never reset" |

### What the Code Actually Shows (L820-825)

```python
# FRESH START: Clear all watchlist entries and pending entries when loading new test case
# This prevents old symbols (e.g., PAVM) from trading when loading a new case (e.g., LCFY)
engine._watchlist.clear()          # L822 — FULL clear
engine._pending_entries.clear()    # L823 — FULL clear
engine._symbol_fails.clear()      # L824 — FULL clear
print(f"[Historical Replay] Cleared watchlist, pending entries, and fail counters for fresh start")
```

### The Call Chain

```
run_batch_tests (L1370 loop)
  └── for case in cases:
        └── load_result = await load_historical_test_case(case_id)  # L1387
              └── engine._watchlist.clear()        # L822
              └── engine._pending_entries.clear()   # L823
              └── engine._symbol_fails.clear()      # L824
```

`load_historical_test_case()` is called **once per case** inside the `run_batch_tests` loop at L1387. Since all three `clear()` calls are inside this function (L822-824), they execute before each case. The report's claim of "never reset" is **wrong**.

> [!IMPORTANT]
> This invalidates the report's **Root Cause #1** ("C7: Engine state bleed-over") as the primary explanation for P&L divergence. The `_watchlist`, `_pending_entries`, and `_symbol_fails` fields DO NOT bleed between sequential cases.

### What Actually Bleeds

Only `engine.stats` (entries_triggered, orders_submitted counters) was not found to be reset. However, `stats` is a **counter** — it doesn't affect entry/exit decisions and cannot cause P&L divergence.

---

## Throttle Impact Test

**Claim**: Does `_last_tech_update_ts` live on `WatchedCandidate` (reset per case) or on the engine (bleeds)?

**Result**: **PASS** — it lives on `WatchedCandidate`.

```python
# warrior_engine_entry.py L398-401
_last = getattr(watched, '_last_tech_update_ts', 0)    # On watched, not engine
if _time.time() - _last >= 60:
    await update_candidate_technicals(engine, watched, current_price)
    watched._last_tech_update_ts = _time.time()          # Set on watched
```

Since a new `WatchedCandidate` is created per case (L809 in `load_historical_test_case`), `_last_tech_update_ts` starts at 0 for every case in BOTH runners. This means C6 (wall-clock throttle) affects both runners **identically** on a per-case basis — it cannot be a divergence source between runners either. The first technicals update always fires, and subsequent updates are throttled equally.

---

## Verified Claims Summary

### C6: Wall-Clock Throttle — Confirmed but NOT a Divergence Source

The throttle uses `time.time()` (wall clock), meaning technicals only update once during fast headless replay. But since:
1. `_last_tech_update_ts` lives on `WatchedCandidate` (fresh per case in both runners)
2. The first update always fires (initial value = 0)
3. Subsequent updates are throttled identically in both runners

The throttle creates an **accuracy issue** (technicals frozen after first update) but NOT a **divergence** between sequential and concurrent. Both runners experience the same throttle behavior per case.

### C3: ContextVar — Confirmed, Impact Depends on Fallback

`set_sim_mode_ctx(True)` is never called in the sequential path. The sequential path relies on the legacy fallback (`get_warrior_sim_broker() is not None`). If any code path checks `_is_sim_mode.get()` directly without the fallback, it would fail to detect sim mode in sequential — but this needs further investigation to determine if such paths exist.

---

## Revised Root Cause Assessment

With C7 (state bleed-over) largely debunked for `_watchlist`, `_pending_entries`, and `_symbol_fails`, the remaining divergence candidates are:

| Rank | Candidate | Mechanism | Status |
|------|-----------|-----------|--------|
| 1 | **C1: Singleton vs Fresh Engine** | `apply_settings_to_config` may load different config values; `sim_only` override risk | Plausible — needs deeper investigation |
| 2 | **C3: ContextVar not set in sequential** | `is_sim_mode()` may return different values affecting `trade_event_service` behavior | Plausible — needs code path tracing |
| 3 | **C4: Global vs bound callbacks** | If another async task modifies the singleton broker between calls | Unlikely in headless batch mode |
| 4 | **C7: `stats` accumulation** | Won't cause P&L divergence — counters only | Eliminated |
| 5 | **C6: Wall-clock throttle** | Same behavior in both runners per-case | Eliminated as divergence source |
| 6 | **Callback wiring differences** | Sequential wires `engine._sim_clock` on monitor (L840) differently than concurrent (L434 on engine, L267 on monitor) | Needs investigation |

### FLYE/RVSN Mystery ($0 in Batch)

The most revealing cases (FLYE producing $0 in batch but -$267.67 in GUI) cannot be explained by state bleed-over since both runners now appear to start each case cleanly. The root cause must lie in:
- A **callback wiring difference** that prevents entry triggers from firing
- A **config difference** from `apply_settings_to_config` affecting entry logic
- A **ContextVar difference** affecting trade logging (trade appears to happen but P&L not captured)

---

## Quality Rating

**MEDIUM** — The audit correctly identified 6 of 7 top-level claims (C1-C6 all pass), but the **primary root cause (C7) contains factual errors** in 3 of 4 sub-claims. The state bleed-over table at L201-208 directly contradicts the code at L820-825. The report's conclusion and refactoring recommendations are built on this incorrect foundation.

### Specific Issues

1. **C7 Table (L201-208)**: Claims `_pending_entries` "❌ Never reset" and `_symbol_fails` "❌ Never reset" — both are cleared at L823-824
2. **C7 Table**: Claims `_watchlist` "Partially reset" — it's fully cleared at L822
3. **Root Cause #1 (L233-239)**: Built entirely on the incorrect C7 findings
4. **Recommendation R1 (L266-275)**: Proposes adding `clear()` calls that already exist
5. **Verification command at L336**: The report's own verification grep would have caught this — `_pending_entries` appears at L823

### What Was Done Well

- C6 (wall-clock throttle) analysis is accurate and important
- C3 (ContextVar) finding is accurate
- C1 (`apply_settings_to_config` override risk) is insightful
- File inventory and callback comparison are thorough
- Refactoring recommendations R2-R5 remain valid

---

## Recommendation

The audit report needs **rework on C7**. Specifically:
1. Correct the state field table at L201-208
2. Revise the root cause ranking — C7 state bleed-over should be **demoted**
3. Investigate the **actual root cause** of P&L divergence, likely in callback wiring differences or config loading
4. Remove recommendation R1 (the clear() calls already exist)
