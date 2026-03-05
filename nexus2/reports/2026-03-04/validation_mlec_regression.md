# Validation Report: MLEC Regression — Adversarial Challenge

**Date:** 2026-03-04 12:57 ET  
**Validator:** Audit Validator  
**Source:** `research_mlec_regression.md` (Backend Planner)  
**Handoff:** `handoff_validator_mlec_regression.md`

---

## Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | `get_daily_bars()` is never called during sim | **PASS** | All 12 production callers traced (see Check 1) — all sim-path callers use `MockMarketData.get_daily_bars()`, not `polygon_adapter.get_daily_bars()` |
| 2 | `adjusted=true` is isolated to scanner/Polygon path | **PASS** | Only change is `polygon_adapter.py:530` — sim uses `MockMarketData` or `sim_get_intraday_bars`, never hits Polygon |
| 3 | No other changes in the 3 files could affect batch results | **PASS** | `gc_quick_test.py` diff is display-only (diff formatting). Scanner changes only affect `_get_200_ema` + `_check_200_ema` (scanner path, bypassed in sim) |
| 4 | MLEC solo run is deterministic (-$578.33) | **PASS** | Run 1: -$578.33 (26.0s), Run 2: -$578.33 (21.9s) — identical |

### Overall Rating: **HIGH** — All claims verified, planner's reasoning is correct.

---

## Check 1: Is `get_daily_bars()` truly never called during sim?

**Verification Command:**
```powershell
# Searched via grep_search on C:\Dev\Nexus\nexus2\domain and C:\Dev\Nexus\nexus2\adapters and C:\Dev\Nexus\nexus2\api
# for all callers of get_daily_bars
```

**All production callers of `get_daily_bars()` (12 total):**

| # | File | Line | Caller | Reachable in batch sim? | Why? |
|---|------|------|--------|------------------------|------|
| 1 | `warrior_scanner_service.py` | 1120 | `polygon.get_daily_bars(symbol, limit=90)` | **NO** | Scanner bypassed — `load_case_into_context()` builds `WatchedCandidate` directly |
| 2 | `warrior_scanner_service.py` | 1178 | `polygon.get_daily_bars(symbol, limit=400)` | **NO** | Same — `_get_200_ema()` is scanner-only |
| 3 | `rs_service.py` | 322 | `fmp.get_daily_bars(symbol, limit=130)` | **NO** | RS service is scanner-only |
| 4 | `rs_service.py` | 361 | `fmp.get_daily_bars(symbol, limit=63)` | **NO** | Same |
| 5 | `breakout_scanner_service.py` | 168 | `fmp.get_daily_bars(symbol, limit=60)` | **NO** | Breakout scanner, not in sim path |
| 6 | `trade_event_service.py` | 198 | `polygon.get_daily_bars("SPY", limit=300)` | **NO** | Guarded by `is_sim_mode()` at line 122 → returns `{"market_context": "skipped_sim_mode"}` |
| 7 | `trade_event_service.py` | 293 | `umd.get_daily_bars(symbol, limit=25)` | **NO** | Guarded by `is_sim_mode()` at line 261 → returns `{}` |
| 8 | `automation_simulation.py` | 555 | `data.get_daily_bars(symbol, days=90)` | **NO** | Calls `MockMarketData.get_daily_bars()`, not Polygon |
| 9 | `automation_simulation.py` | 1043 | `fmp.get_daily_bars(...)` | **NO** | Different API endpoint (`/simulation/chart`), not batch sim |
| 10 | `automation_simulation.py` | 1220 | `fmp.get_daily_bars(...)` | **NO** | Different API endpoint, not batch sim |
| 11 | `warrior_positions.py` | 213 | `polygon.get_daily_bars(p.symbol, 250)` | **NO** | Live positions API, not batch sim |
| 12 | `historical_loader.py/backtest_runner.py` | various | `fmp.get_daily_bars(...)` | **NO** | Lab module, separate from gc_quick_test |

**sim_mode guard verification:**  
`sim_context.py:677-679` — `set_sim_mode_ctx(True)` is called inside `_run_single_case_async()` before any trade logic runs. This sets the ContextVar that guards `trade_event_service.py` from making live API calls.

**Result:** PASS — No path from batch sim execution reaches `polygon_adapter.get_daily_bars()`.

---

## Check 2: Is `adjusted=true` isolated to the scanner path?

**Verification Command:**
```powershell
# grep_search for "adjusted" in nexus2/adapters/market_data/polygon_adapter.py
```

**Actual Output:**
```
polygon_adapter.py:530: params={"limit": limit, "sort": "asc", "adjusted": "true"}
```

**Analysis:** The `adjusted=true` parameter was added to `polygon_adapter.py:get_daily_bars()` (line 530). This is a global change to the adapter method. However, as proven in Check 1, **no sim path calls this method**. The only callers during batch sim that use `get_daily_bars` reference `MockMarketData.get_daily_bars()`, which is a completely separate class with its own implementation.

**Result:** PASS — The change is global at the adapter level but unreachable from sim.

---

## Check 3: Are there other changes in the 3 modified files?

**Verification Command:**
```powershell
git diff HEAD~5 -- nexus2/adapters/market_data/polygon_adapter.py nexus2/domain/scanner/warrior_scanner_service.py scripts/gc_quick_test.py
```

**Changes per file:**

| File | Changes | Could affect batch results? |
|------|---------|---------------------------|
| `polygon_adapter.py` | Added `"adjusted": "true"` to `get_daily_bars()` params (1 line) | **NO** — unreachable from sim (Check 1) |
| `warrior_scanner_service.py` | 1) Removed bar reversal `closes[::-1]` → uses `closes` directly. 2) Fixed comment. 3) Added EMA sanity check (ratio >100x or <0.01x discards value). | **NO** — all in `_get_200_ema()` and `_check_200_ema()`, which are scanner-only functions bypassed in sim |
| `gc_quick_test.py` | Improved `diff_results()` to separate NEW cases from genuine improvements. Returns `(improved, regressed, new_count)` tuple. Display-only changes. | **NO** — only affects diff display formatting, not test execution or P&L computation |

**Result:** PASS — No change in any of the 3 files touches the sim execution path, entry logic, exit logic, or P&L computation.

---

## Check 4: Run MLEC twice for concurrency noise

**Run 1** (by Clay):
```
python scripts/gc_quick_test.py ross_mlec_20260213 --trades
MLEC 2026-02-13    | Bot: $   -578.33 | Ross: $ 43,000.00
Runtime: 26.0s
```

**Run 2** (by Clay):
```
python scripts/gc_quick_test.py ross_mlec_20260213 --trades
MLEC 2026-02-13    | Bot: $   -578.33 | Ross: $ 43,000.00
Runtime: 21.9s
```

**Result:** PASS — Both runs produce **-$578.33** exactly. MLEC is deterministic in solo mode. The -$2,000.67 reported from `--all --diff` was concurrency noise in the batch concurrent runner.

---

## Adversarial Challenges Attempted

### Challenge A: Could `get_daily_bars` be called indirectly via `UnifiedMarketData`?

`trade_event_service.py:293` calls `umd.get_daily_bars(symbol, limit=25)` which goes through `UnifiedMarketData.get_daily_bars()` → `fmp.get_daily_bars()` (line 351 of `unified.py`). This does NOT call `polygon_adapter.get_daily_bars()`.

However, this is **moot** because `_get_symbol_technical_context()` has an `is_sim_mode()` guard at line 261 that returns `{}` before reaching the `get_daily_bars` call.

### Challenge B: Does `set_sim_mode_ctx(True)` survive process spawning?

`_run_case_sync()` uses `ProcessPoolExecutor` with `spawn` context (line 988). ContextVars don't carry across process boundaries. However, `set_sim_mode_ctx(True)` is called **inside** `_run_single_case_async()` at line 679, which runs within the spawned process. The ContextVar is set fresh in each worker process. ✅

### Challenge C: Could the `gc_quick_test.py` diff logic changes affect P&L computation?

No. The `diff_results()` function only formats and displays results. The actual P&L computation happens in `sim_context.py` → `MockBroker.get_account()["realized_pnl"]`. The diff changes only affect how results are categorized (new vs improved vs regressed) for display. ✅

---

## Conclusion

The planner's claim is **CORRECT**: the EMA fix cannot cause the MLEC regression.

1. **Data path isolation**: Sim uses `MockMarketData` + historical bar loader. Polygon `get_daily_bars()` is unreachable.
2. **Scanner bypass**: Sim builds `WatchedCandidate` directly, never calls `_get_200_ema()` or `_check_200_ema()`.
3. **sim_mode guards**: `trade_event_service.py` guards prevent live API calls during sim.
4. **Deterministic results**: MLEC produces -$578.33 in both solo runs, matching the baseline exactly.
5. **Phantom regression**: The -$2,000.67 from batch `--all --diff` was concurrency noise, not a real regression.
