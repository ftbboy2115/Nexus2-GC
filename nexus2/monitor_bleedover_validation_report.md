# Validation Report: Monitor Bleed-Over Theory

**Date**: 2026-02-10  
**Validator**: Audit Validator Agent  
**Handoff**: `monitor_bleedover_validation_handoff.md`

---

## Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| V1 | `remove_position()` never called in `warrior_sim_routes.py` | **PASS** | `grep_search("remove_position", warrior_sim_routes.py)` → **zero matches**. Confirmed: the method is never invoked anywhere in the sequential runner file. |
| V2 | `_positions` never cleared in `load_historical_test_case` | **PASS** | `grep_search("_positions", warrior_sim_routes.py)` → **18 matches**, all are reads/checks (`get_positions()`, `_check_all_positions()`, `if engine.monitor._positions`). **Zero** matches for `_positions.clear()` or `_positions = {}`. L820-824 clears `_watchlist`, `_pending_entries`, `_symbol_fails` — but `monitor._positions` is **conspicuously absent**. |
| V3 | Only `_recently_exited_sim_time` cleared, NOT `_recently_exited` | **PASS** | `grep_search("recently_exited", warrior_sim_routes.py)` → **1 match**: L841 `engine.monitor._recently_exited_sim_time.clear()`. No match for `_recently_exited.clear()` or `_recently_exited = {}`. The wall-clock cooldown dict bleeds across cases. |
| V4 | EOD close sells broker positions but does NOT clear monitor | **PASS** | `grep_search("sell_position", warrior_sim_routes.py)` → **5 matches**, including L1424 `broker.sell_position(pos_symbol, pos_qty)` in the EOD close block (L1408-1442). `grep_search("remove_position", warrior_sim_routes.py)` → **zero matches**. EOD close removes positions from the broker but the monitor retains stale position objects. |
| V5 | Concurrent runner creates fresh monitor per case | **PASS** | `grep_search("WarriorMonitor\|_recently_exited", sim_context.py)` → **7 matches**: L40 `monitor = WarriorMonitor()`, L42 `monitor._recently_exited_file = None`, L43 `monitor._recently_exited = {}`, L44 `monitor._recently_exited_sim_time = {}`. Fresh instance with explicit zero state. |

---

## Verdict

### **CONFIRMED** — Monitor state bleed is the root cause of sequential runner divergence.

---

## Evidence Summary

### What the sequential runner clears between cases (L820-824, L841):

```python
engine._watchlist.clear()           # ✅ Cleared
engine._pending_entries.clear()     # ✅ Cleared
engine._symbol_fails.clear()        # ✅ Cleared
engine.monitor._recently_exited_sim_time.clear()  # ✅ Cleared (L841)
```

### What the sequential runner does NOT clear:

```python
engine.monitor._positions           # ❌ NEVER cleared
engine.monitor._recently_exited     # ❌ NEVER cleared (wall-clock dict)
```

### EOD close gap (L1408-1442):

```python
broker.sell_position(pos_symbol, pos_qty)  # Sells from broker
# monitor.remove_position()  ← NEVER CALLED
# monitor._positions.clear() ← NEVER CALLED
```

### Concurrent runner (L40-44 in sim_context.py):

```python
monitor = WarriorMonitor()                  # Fresh instance
monitor._recently_exited_file = None        # Explicit reset
monitor._recently_exited = {}               # Explicit reset
monitor._recently_exited_sim_time = {}      # Explicit reset
```

---

## Impact Analysis

The bleed-over means that when the sequential batch runner processes case N+1:

1. **`_positions` still contains case N's positions** — the monitor may attempt exit checks on symbols from the previous case, potentially interfering with new entries
2. **`_recently_exited` retains case N's exit cooldowns** — if a symbol from case N was also tested in a later case, the re-entry cooldown could block entry (explains FLYE and RVSN producing $0)
3. **EOD close sells broker positions but the monitor doesn't know** — creating ghost positions that the monitor tracks but the broker no longer has

---

## Additional Finding

The `saved_callbacks` save/restore block at L1344-1364 saves and restores monitor *callbacks* but does NOT save/restore monitor *state* (`_positions`, `_recently_exited`). This is a secondary confirmation that state management was not considered for the batch loop.

---

## Quality Rating

**HIGH** — All 5 claims verified cleanly with direct evidence. The theory is well-supported.
