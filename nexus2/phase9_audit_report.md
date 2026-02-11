# Phase 9 Audit Report: Runner Divergence Root Cause Analysis

**Date**: 2026-02-11  
**Auditor**: Code Auditor Agent  
**Scope**: Claims C1–C5 from [phase9_audit_handoff.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/phase9_audit_handoff.md)  
**Status**: ✅ COMPLETE

---

## Executive Summary

The P&L divergence between the sequential batch runner (`/sim/run_batch`) and the concurrent batch runner (`/sim/run_batch_concurrent`) was caused by **monitor state bleed-over in the sequential runner**. Specifically, `_positions` and `_recently_exited` dicts on the shared `WarriorMonitor` were NOT cleared between cases, causing:

1. **Stale position objects** from case N remaining in case N+1's monitor
2. **Re-entry cooldowns** from case N blocking entries in case N+1

The Phase 9 fix at [warrior_sim_routes.py:L826-832](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L826-L832) correctly addresses this by clearing these dicts. The concurrent runner avoids this entirely by creating a fresh `WarriorMonitor()` per case via `SimContext.create()`.

---

## Claim Verdicts

| Claim | Description | Verdict | P&L Impact |
|-------|-------------|---------|------------|
| C1 | Shared engine state in sequential runner | ✅ CONFIRMED | **LOW** — engine watchlist/pending/fails are already cleared (L822-824), stats dataclass is defined but never instantiated |
| C2 | Wall-clock throttle divergence | ✅ CONFIRMED NON-ISSUE | **NONE** — `_last_tech_update_ts` lives on `WatchedCandidate`, fresh per case in both runners |
| C3 | Trade DB contamination between sequential cases | ✅ CONFIRMED SAFE | **NONE** — `purge_sim_trades()` correctly deletes all `is_sim=True` trades (L788) |
| C4 | Callback wiring differences | ✅ CONFIRMED DIVERGENT | **LOW** — sequential closures over globals are functionally equivalent when broker is reset per case |
| C5 | MockBroker `initial_cash` and reset completeness | ✅ CONFIRMED DIVERGENT | **NONE** — `initial_cash` (25K vs 100K) doesn't affect position-relative P&L calculations |

> [!IMPORTANT]
> The **actual root cause** was NOT any of C1–C5. It was **monitor state bleed-over** (`_positions`, `_recently_exited`), which was fixed at L826-832 before this audit began. Claims C1–C5 are contributing factors but none independently cause P&L divergence.

---

## Detailed Findings

### C1: Shared Engine State in Sequential Runner

**Claim**: The sequential runner reuses a global `WarriorEngine` via `get_engine()`. State from case N may leak into case N+1.

**Evidence**:

The sequential runner at [L1356](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L1356) calls `get_engine()` once, then iterates through cases. Within `load_historical_test_case()`, the following state IS cleared per case:

```python
# L822-824: Explicitly cleared per case
engine._watchlist.clear()
engine._pending_entries.clear()
engine._symbol_fails.clear()
```

The concurrent runner creates a wholly new `WarriorEngine` per case at [SimContext.create() L42-52](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L42-L52).

**What IS reset** (sequential):
- `_watchlist` ✅ (L822)
- `_pending_entries` ✅ (L823)
- `_symbol_fails` ✅ (L824)
- `monitor._positions` ✅ (L830, Phase 9 fix)
- `monitor._recently_exited` ✅ (L831, Phase 9 fix)
- `monitor._recently_exited_sim_time` ✅ (L849)
- `monitor.realized_pnl_today` ✅ (L850)

**What is NOT reset** (sequential):
- `WarriorEngineStats` — defined at `warrior_engine_types.py:L138-150` but **never instantiated** on the engine (`self.stats` not found in `warrior_engine.py`). **No impact.**
- `_last_scan_started`, `_last_scan_result` — irrelevant in batch mode (scans are not used; candidates are injected directly)
- Engine `config` — same config across cases (intentional)

**Verdict**: CONFIRMED but **no remaining P&L impact** after Phase 9 fix.

---

### C2: Wall-Clock Throttle Divergence

**Claim**: Both runners throttle `update_candidate_technicals` using `time.time()` (wall-clock). In headless batch mode, bars replay in <1s — technicals may only compute once per case. The sequential runner's `_last_tech_update_ts` could carry over between cases.

**Evidence**:

At [warrior_engine_entry.py:L398-401](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py#L398-L401):

```python
_last = getattr(watched, '_last_tech_update_ts', 0)    # On WatchedCandidate
if _time.time() - _last >= 60:
    await update_candidate_technicals(engine, watched, current_price)
    watched._last_tech_update_ts = _time.time()          # Set on WatchedCandidate
```

Key insight: `_last_tech_update_ts` is stored on the `WatchedCandidate` object, **not** the engine. A new `WatchedCandidate` is created per case in **both** runners:
- Sequential: [L809](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L809)
- Concurrent: [sim_context.py:L246](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L246)

Since `getattr(watched, '_last_tech_update_ts', 0)` defaults to 0, the first technicals update **always fires** for every case in both runners. The 60s throttle affects subsequent updates within the same case identically.

**Verdict**: CONFIRMED NON-ISSUE. No divergence source.

---

### C3: Trade DB Contamination Between Sequential Cases

**Claim**: The sequential runner calls `purge_sim_trades()` before each case. Does it fully delete all sim trades?

**Evidence**:

At [warrior_db.py:L787-788](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/db/warrior_db.py#L787-L788):

```python
with get_warrior_session() as db:
    count = db.query(WarriorTradeModel).filter_by(is_sim=True).delete()
    db.commit()
```

This correctly deletes **all** trades where `is_sim=True`. The sequential runner at [L1389-1390](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L1389-L1390) calls this with `confirm=True` and the MockBroker is active (safety check passes).

The concurrent runner sidesteps this entirely by replacing the shared warrior.db with an in-memory SQLite per process at [sim_context.py:L451-458](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L451-L458):

```python
mem_engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
wdb.warrior_engine = mem_engine
wdb.WarriorSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=mem_engine)
wdb.WarriorBase.metadata.create_all(bind=mem_engine)
```

**Note**: The sequential runner reads P&L from `get_all_warrior_trades(limit=100, status_filter="closed")` at [L1471](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L1471) AFTER purging. Since purge happens before `load_historical_test_case`, any trades returned are from the current case only.

**Verdict**: CONFIRMED SAFE. No contamination.

---

### C4: Callback Wiring Differences

**Claim**: Sequential runner re-wires callbacks on the global engine/monitor using closures that reference `get_warrior_sim_broker()`. Concurrent runner captures `ctx` components via default arguments.

**Evidence**:

**Sequential** (at [L852-858](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L852-L858)):
```python
async def sim_get_price(symbol: str):
    sim_broker = get_warrior_sim_broker()  # Global lookup each call
    if sim_broker:
        price = sim_broker.get_price(symbol)
        ...
```

**Concurrent** (at [sim_context.py:L271-273](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L271-L273)):
```python
async def sim_get_price(symbol: str, _broker=ctx.broker):  # Captured at definition
    price = _broker.get_price(symbol)
    ...
```

The sequential approach re-resolves the broker on every call, while the concurrent approach captures it once. However, since the sequential runner resets and reuses the **same** global broker instance per case (`broker.reset()` at L740), both resolve to the correct broker for that case.

The concurrent approach is strictly safer because it prevents any possibility of cross-context leakage in parallel execution. For sequential execution, the global lookup is functionally equivalent.

**Verdict**: CONFIRMED DIVERGENT in mechanism, but **no P&L impact** in sequential mode.

---

### C5: MockBroker `initial_cash` and Reset Completeness

**Claim**: Sequential runner uses `MockBroker(initial_cash=25000)`, concurrent uses `MockBroker(initial_cash=100_000)`. Does this affect P&L?

**Evidence**:

Sequential initialization at [L735-736](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L735-L736):
```python
broker = MockBroker(initial_cash=25000.0)
```

Concurrent initialization at [SimContext.create() L37](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L37):
```python
broker = MockBroker(initial_cash=100_000, clock=clock)
```

`MockBroker.reset()` at [mock_broker.py:L105-112](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/mock_broker.py#L105-L112) resets:
- `_cash` → `_initial_cash` ✅
- `_orders` → cleared ✅
- `_positions` → cleared ✅
- `_current_prices` → cleared ✅
- `_realized_pnl` → 0 ✅
- `_max_capital_deployed` → 0 ✅
- `_max_shares_held` → 0 ✅

The `initial_cash` difference (25K vs 100K) could theoretically affect:
- Whether a large order is rejected for insufficient buying power
- Account-level metrics reported

However, P&L calculations in `sell_position()` are position-relative (exit_price − entry_price × shares), not cash-relative. The `initial_cash` doesn't affect `realized_pnl`.

> [!NOTE]
> There is a theoretical edge case where `initial_cash=25000` with the sequential runner could cause an order rejection if position size × limit price > $25,000. Most test cases have small positions ($500–$2000), so this is unlikely to trigger in practice.

**Verdict**: CONFIRMED DIVERGENT but **no P&L impact** for current test cases.

---

## Root Cause: Monitor State Bleed-Over (Phase 9 Fix)

The actual root cause was identified and fixed before this audit began. The fix at [L826-832](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L826-L832):

```python
# MONITOR STATE RESET (Phase 9 fix)
engine.monitor._positions.clear()
engine.monitor._recently_exited.clear()
```

Plus additional resets at [L849-850](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L849-L850):
```python
engine.monitor._recently_exited_sim_time.clear()
engine.monitor.realized_pnl_today = Decimal("0")
```

Without these clears:
- **FLYE** and **RVSN** produced $0 P&L in the sequential runner because `_recently_exited` cooldowns from previous cases blocked their entries
- **BATL** over-traded because stale `_positions` from previous cases affected monitor eval

The concurrent runner never had this issue because `SimContext.create()` instantiates a fresh `WarriorMonitor()` per case.

---

## Remaining Differences (Non-Critical)

| Difference | Sequential | Concurrent | Risk |
|-----------|-----------|------------|------|
| `initial_cash` | $25,000 | $100,000 | LOW — buying power rejection unlikely |
| Callback pattern | Global lookup | Default-arg capture | NONE for sequential |
| DB isolation | `purge_sim_trades()` | In-memory SQLite per process | NONE — both effective |
| Engine isolation | Shared singleton + explicit resets | Fresh instance per case | LOW — all relevant state cleared |
| Monitor isolation | Shared singleton + Phase 9 resets | Fresh instance per case | NONE after Phase 9 fix |

---

## Recommendations

1. **Unify `initial_cash`** — Set sequential runner to `100_000` to match concurrent, eliminating this difference entirely
2. **Consider extracting reset logic** — The sequential runner's reset code at L820-850 is fragile (must remember every dict). A `WarriorEngine.reset_for_batch()` method would be safer
3. **The concurrent runner is the canonical implementation** — Its isolation-by-construction approach is fundamentally more robust than the sequential runner's reset-everything approach. New test code should use the concurrent path.
