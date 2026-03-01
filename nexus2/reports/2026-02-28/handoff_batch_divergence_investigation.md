# Batch Test Divergence Investigation

**Agent:** Backend Planner  
**Priority:** HIGH  
**Type:** Runtime divergent behavior → Trace investigation  
**Date:** 2026-02-28

---

## Problem Statement

Running `run_batch_concurrent` on the exact same code produces **wildly different PnL** between local machine and VPS.

---

## Verified Facts

### Fact 1: Local batch result
**Verified with:** `Invoke-RestMethod -Method POST -Uri "http://localhost:8000/warrior/sim/run_batch_concurrent"` (Clay ran locally)
```
total_pnl: $391,215.23
cases_profitable: 28/38
runtime_seconds: 82.91
```

### Fact 2: VPS batch result  
**Verified with:** `Invoke-RestMethod -Method POST -Uri "http://100.113.178.7:8000/warrior/sim/run_batch_concurrent"` (VPS run)
```
total_pnl: $253,757.74
cases_profitable: 27/38
runtime_seconds: 556.57
```

### Fact 3: Delta = $137,457 (35% lower on VPS)

### Fact 4: Biggest per-case divergences

| Case | Local PnL | VPS PnL | Δ | Guard Blocks (Local) | Guard Blocks (VPS) |
|------|-----------|---------|---|---------------------|-------------------|
| BATL-0126 | $61,366 | -$1,229 | -$62,595 | 15,679 | 126 |
| ROLR | $45,723 | -$1,458 | -$47,181 | 1,316 | 44 |
| NPT | $68,021 | $41,280 | -$26,741 | 0 | 18 |
| EVMN | $42,354 | $13,554 | -$28,800 | 0 | 0 |
| PRFX | $25,200 | $42,000 | +$16,800 | 184 | 0 |

### Fact 5: Guard block counts differ wildly
- BATL-0126: 15,679 local → 126 VPS (125x difference)
- PAVM: 14,960 local → 64 VPS (234x difference)
- ROLR: 1,316 local → 44 VPS (30x difference)

### Fact 6: VPS is ~6.7x slower (557s vs 83s)
- **Local machine:** 10 cores → `asyncio.gather()` runs cases truly in parallel
- **VPS:** 1 core → cases serialize on the event loop
- This is expected for speed — but should NOT cause PnL divergence unless real wall-clock time leaks into logic

### Fact 7: Both environments run the same Git commit
**Verified with:** `git pull` on VPS pulled `35a4844` which is the same HEAD as local.

### Fact 8: VPS concurrency may have regressed (Clay's observation)
- Clay notes: "At one time, we used to have concurrency [on VPS], so I don't know when that changed"
- This suggests a regression where cases that should be independent may now share mutable state

---

## Open Questions (Investigate These)

### Q1: Does `_get_eastern_time()` in entry guards use real wall clock or sim clock?
- **Starting point:** `warrior_entry_guards.py` — search for `_get_eastern_time()`  
- The EoD entry cutoff guard and progressive spread gates use this function
- Previous fix (`c77756b`) patched it for the **singleton engine** but may NOT have patched it for the **per-case concurrent runner** engine
- If real clock is used: VPS running at ~3PM ET would start blocking entries that local (83s) wouldn't

### Q2: Does the concurrent runner's engine have `_sim_clock` set?
- **Starting point:** `sim_context.py` — search for `_sim_clock` or `sim_clock`
- The singleton engine gets `_sim_clock` set in `load_historical`
- But the concurrent runner creates fresh engines — does it wire `_sim_clock`?

### Q3: Are there guard functions that reference `time.time()` (real wall clock)?
- **Starting point:** `warrior_entry_guards.py` — search for `time.time()` or `datetime.now()`
- Any guard using real time instead of sim time would produce different results on fast vs slow machines

### Q4: Do persisted config/monitor settings differ between local and VPS?
- **Starting point:** Check what `get_warrior_config()` and `get_warrior_monitor_settings()` return on each environment
- Different settings (e.g., `max_entry_spread_percent`, `mental_stop_cents`) would produce different sizing and guard behavior

### Q5: Is there non-determinism / shared state in the concurrent runner?
- **Starting point:** `sim_context.py` — look for shared mutable state across concurrent cases
- If multiple cases share a singleton (e.g., `get_warrior_sim_broker()`, global engine state), cases could bleed into each other
- With 1 core (VPS), cases serialize — so case N's leftover state could affect case N+1
- With 10 cores (local), cases run truly parallel — less cross-contamination
- **Critical test:** Run the SAME batch twice on the SAME machine — do results match? If not, it's non-determinism. If yes, it's environment-specific.

### Q6: Did concurrency regress on VPS?
- Clay says VPS used to produce concurrent results matching local
- Something changed — possibly a code change introduced shared global state
- **Starting point:** Check `git log --oneline -20` for recent changes to `sim_context.py` or `warrior_sim_routes.py` that touch global state

### Q7: Why do some cases have dramatically different guard block counts?
- Guard blocks should be deterministic for the same code + data
- BATL-0126: 15,679 vs 126 — this is not a small timing difference, it's fundamentally different behavior
- Investigate whether guard evaluation is deterministic in the concurrent runner

---

## Suggested Approach

1. **First:** Run batch twice on VPS to check for same-machine non-determinism
2. **Then:** Grep `_get_eastern_time()`, `time.time()`, `datetime.now()` in guard files
3. **Then:** Check if `sim_context.py` sets `engine._sim_clock` on per-case engines
4. **Finally:** Compare persisted configs between local and VPS

---

## Deliverable

A report at `nexus2/reports/2026-02-28/research_batch_divergence.md` with:
- Root cause(s) identified with code evidence
- Proposed fix(es)
- Whether the issue is determinism (same-machine divergence) or environment-specific (config differences)
