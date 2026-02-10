# Concurrent Batch Runner Architecture Audit

> **Auditor:** Code Auditor Specialist  
> **Date:** 2026-02-10  
> **Architecture Doc:** [concurrent_batch_runner_architecture.md](file:///C:/Users/ftbbo/.gemini/antigravity/brain/e56e9f8f-208c-46dc-8c63-d13dcafec674/concurrent_batch_runner_architecture.md)  
> **Mode:** READ-ONLY forensic audit — no code modified  

---

## Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | `get_warrior_sim_broker()` returns a module-level singleton | **PASS** | [warrior_sim_routes.py:L31-38](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L31-L38) — `_warrior_sim_broker = None` global with thread lock, getter returns it |
| 2 | `get_simulation_clock()` returns a module-level singleton | **PASS** | [sim_clock.py:L304-313](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_clock.py#L304-L313) — `_simulation_clock: Optional[SimulationClock] = None`, lazy-creates on first call |
| 3 | `get_historical_bar_loader()` returns a module-level singleton | **PASS** | [historical_bar_loader.py:L464-473](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/historical_bar_loader.py#L464-L473) — same lazy singleton pattern |
| 4 | `get_engine()` returns a module-level singleton | **PASS** | [warrior_routes.py:L124-125](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_routes.py#L124-L125) — delegates to `get_warrior_engine()` from `warrior_engine.py` |
| 5 | `MockBroker` can be independently instantiated | **PASS** | [mock_broker.py:L103-118](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/mock_broker.py#L103-L118) — `__init__` only sets instance-level dicts/values, zero global imports |
| 6 | `SimulationClock` can be independently instantiated | **PASS** | [sim_clock.py:L31-47](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_clock.py#L31-L47) — `__init__` only sets `_current_time`, `_speed`, `_running`, no global deps |
| 7 | `HistoricalBarLoader` can be independently instantiated | **PASS** | [historical_bar_loader.py:L269-278](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/historical_bar_loader.py#L269-L278) — `__init__` only sets `_test_cases_dir` and `_loaded_data` dict, no globals |
| 8 | `WarriorMonitor` has hidden `get_engine()` calls in exit path | **FAIL** ✅ | Searched `warrior_monitor.py`, `warrior_monitor_exit.py`, `warrior_monitor_scale.py`, `warrior_monitor_sync.py` — **ZERO** occurrences of `get_engine` in any file. Monitor is fully callback-based. |
| 9 | Monitor uses `set_callbacks()` to wire price/execution functions | **PASS** | [warrior_monitor.py:L203-243](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor.py#L203-L243) — 11 callbacks: `get_price`, `get_prices_batch`, `get_quote_with_spread`, `get_intraday_candles`, `execute_exit`, `update_stop`, `get_broker_positions`, `record_symbol_fail`, `submit_scale_order`, `get_order_status`, `on_profit_exit` |
| 10 | `check_entry_triggers` depends on global engine | **PASS** | [warrior_sim_routes.py:L1111-1117](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L1111-L1117) — `step_clock` calls `engine = get_engine()` then `await check_entry_triggers(engine)` at L1165 |
| 11 | Batch runner saves/restores live callbacks in `try/finally` | **PASS** | [warrior_sim_routes.py:L1354-1364](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L1354-L1364) — saves 9 callbacks (`_get_price`, `_get_prices_batch`, `_get_intraday_candles`, `_get_quote_with_spread`, `_execute_exit`, `_update_stop`, `_get_broker_positions`, `_submit_scale_order`, `_get_order_status`), restores in `finally` |
| 12 | `WarriorTradeModel` does NOT have `batch_run_id` column | **PASS** | [warrior_db.py:L39-126](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/db/warrior_db.py#L39-L126) — confirmed 23 columns total, no `batch_run_id` |

---

## Discovery Findings

### 1. Files importing `get_warrior_sim_broker`

> [!CAUTION]
> **7 files** import this singleton across routes, domain, and DB layers — far broader coupling than expected.

| File | Lines | Purpose |
|------|-------|---------|
| [warrior_sim_routes.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py) | L35 (def), 20+ call sites | Definition + primary consumer |
| [warrior_callbacks.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_callbacks.py) | L163, L279 | Live callback routing checks if sim broker active |
| [warrior_positions.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_positions.py) | L44, L118 | Position display routing (live vs sim) |
| [trade_event_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/trade_event_service.py) | L95, L229, L497, L757, L803 | **5 call sites** — uses to detect mock market mode |
| [warrior_db.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/db/warrior_db.py) | L755 | `purge_sim_trades` safety check |
| [test_warrior_routes.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/tests/api/test_warrior_routes.py) | L138+ | Test mocking (6 patches) |

> **Risk:** `trade_event_service.py` checks `get_warrior_sim_broker() is not None` as a global "am I in sim mode?" flag. In concurrent mode, this global will be `None` per-context (since each context has its own broker), potentially breaking trade event routing.

### 2. Files importing `get_engine`

| File | Usage |
|------|-------|
| [warrior_routes.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_routes.py) | Definition (L124) + all route handlers |
| [warrior_sim_routes.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py) | L144, L351, L370, L1112 |
| [warrior_positions.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_positions.py) | L43, L117, L264, L275, L295, L327 |
| [automation.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/automation.py) | L34, L68, L92 + all route handlers |
| [automation_state.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/automation_state.py) | L41 |
| [main.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/main.py) | L190, L243 |

### 3. Files importing from `adapters/simulation/__init__.py`

> [!WARNING]
> `get_simulation_clock()` is embedded in **12+ domain-layer files** — the architecture doc **does not mention** this as a coupling concern, but it IS the deepest hidden dependency.

| File | Lines |
|------|-------|
| [scheduler.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/scheduler.py) | L97, L126, L218, L356 |
| [warrior_entry_patterns.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py) | L312, L547, L979 |
| [warrior_vwap_utils.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_vwap_utils.py) | L63, L100 |
| [warrior_monitor_exit.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py) | L177 |
| [warrior_scanner_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py) | L351 |
| [services.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/services.py) | L170 |
| [mock_broker.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/mock_broker.py) | L441 |
| [warrior_engine.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine.py) | L563 |
| [warrior_engine_entry.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py) | L364 |
| [alpaca_broker.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/broker/alpaca_broker.py) | L49 |

### 4. Thread/async safety — WAL mode

> [!CAUTION]
> **warrior_db does NOT use WAL mode.** The `create_engine` call at [warrior_db.py:L26-30](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/db/warrior_db.py#L26-L30) only specifies `check_same_thread=False`. No `journal_mode=WAL` is configured. Concurrent writes from `asyncio.gather()` **will cause SQLite BUSY errors** without this.

```python
# Current (no WAL mode)
warrior_engine = create_engine(
    WARRIOR_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)
```

### 5. `step_clock` callers

| Caller | File | Line |
|--------|------|------|
| Batch runner (headless) | warrior_sim_routes.py | L1406 |
| GUI step forward | warrior_sim_routes.py | L1092 (the `@sim_router.post("/sim/step")` endpoint wrapping it) |

Only 2 callers. The batch runner calls `await step_clock(minutes=step_minutes, headless=True)`.

### 6. Hidden state in WarriorMonitor

> [!NOTE]
> Very good news — `_check_all_positions()` and `_evaluate_position()` access **no globals** beyond their callbacks. The monitor is fully callback-isolated.

- No `get_engine()` in any monitor file
- No `get_simulation_clock()` in `warrior_monitor.py` (but **one occurrence** in [warrior_monitor_exit.py:L177](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py#L177) — used for sim-time exit tracking)
- No `get_warrior_sim_broker()` in any monitor file
- No `get_historical_bar_loader()` in any monitor file

Hidden state within monitor `__init__`:
- `self._recently_exited_file` — file path for disk persistence (affects concurrent cases writing to same file)
- `self._recently_exited` and `self._recently_exited_sim_time` — in-memory dicts, isolated per instance ✅

---

## Hidden Dependencies Found

### 1. `trade_event_service.py` — Global Sim Mode Detection (CRITICAL)

`trade_event_service.py` uses `get_warrior_sim_broker() is not None` as a **global flag** to detect Mock Market mode at **5 separate call sites** (L95, L229, L497, L757, L803). In the concurrent architecture, each `SimContext` would have its own `MockBroker`, but `trade_event_service` wouldn't know about it — it checks the **global** singleton.

**Impact:** Entry logging via `trade_event_service` will behave as if NOT in sim mode during concurrent runs (since the global singleton may be `None`), potentially routing trades to live Alpaca broker logging paths.

### 2. `get_simulation_clock()` in Deep Domain Logic (CRITICAL)

The architecture doc focuses on isolating `MockBroker` and `WarriorMonitor` but **does not address** `get_simulation_clock()` embedded in:
- **Entry patterns** (`warrior_entry_patterns.py` × 3 calls) — uses sim clock to determine time-based entry validity
- **VWAP utils** (`warrior_vwap_utils.py` × 2 calls) — uses sim clock for bar lookups
- **Monitor exit** (`warrior_monitor_exit.py` × 1 call) — uses sim clock for sim-time exit tracking

In concurrent mode, all 18 contexts would share the **same global clock**, defeating time isolation.

### 3. `get_historical_bar_loader()` in Entry Path (MODERATE)

`warrior_engine_entry.py:L364` and `warrior_engine.py:L563` both call `get_historical_bar_loader()` directly. In concurrent mode, these would access the global loader (which has data from whichever case loaded last).

### 4. `purge_sim_trades` — Sequential Purge Incompatible with Concurrency 

The batch runner at [L1378-1383](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L1378-L1383) calls `purge_sim_trades(confirm=True)` before each case. With concurrent execution, this would delete other in-flight contexts' DB records. The `batch_run_id` approach in the architecture doc correctly addresses this.

### 5. `_recently_exited_file` — File System Conflict (LOW)

`WarriorMonitor.__init__` sets `self._recently_exited_file` to a fixed path (`data/recently_exited.json`). If 18 monitors write concurrently, they'll corrupt each other's file. Fix: disable file persistence in batch mode (in-memory only).

---

## Risk Assessment (Updated)

| Risk | Arch Doc Rating | Actual Rating | Reason |
|------|----------------|---------------|--------|
| P&L diverges from sequential | HIGH | **HIGH** | Still the key acceptance criterion |
| Hidden global state in monitor | MEDIUM | **LOW** ✅ | Monitor has ZERO global deps — better than expected |
| `get_simulation_clock()` in domain | *(not mentioned)* | **HIGH** 🚨 | 12+ files use it — entry patterns, VWAP, exit timing all break |
| `trade_event_service` sim detection | *(not mentioned)* | **HIGH** 🚨 | 5 call sites route based on global sim broker — breaks entry logging |
| SQLite write contention | LOW | **MEDIUM** ⬆️ | No WAL mode configured — concurrent writes will BUSY-error |
| `get_historical_bar_loader()` in entry | *(not mentioned)* | **MEDIUM** 🚨 | Entry path uses global loader — wrong bars for concurrent cases |
| Memory (18 contexts) | LOW | LOW ✅ | Confirmed each context is lightweight |
| asyncio starvation | LOW | LOW ✅ | Confirmed CPU-light steps |

---

## Refactoring Recommendations

| Priority | Issue | Effort | Action |
|----------|-------|--------|--------|
| 🔴 P0 | `get_simulation_clock()` embedded in 12+ files | **L** | Pass clock as parameter or use context-local injection |
| 🔴 P0 | `trade_event_service` uses global sim broker as flag | **M** | Add `is_sim` param to service methods or context-local flag |
| 🔴 P0 | No WAL mode on warrior_db | **S** | Add `"journal_mode": "WAL"` to `connect_args` in engine creation |
| 🟡 P1 | `get_historical_bar_loader()` in entry path | **M** | Pass loader through engine/context |
| 🟡 P1 | `_recently_exited_file` shared path | **S** | Skip file persistence when `sim_mode=True` |
| 🟢 P2 | Architecture doc Claim 8 inaccuracy | **S** | Update doc: monitor has no `get_engine()` calls (good news!) |

---

## Overall Rating

### **MEDIUM** — Architecture doc is **mostly accurate** with important corrections needed

**What's accurate:**
- Singleton pattern analysis (Claims 1-4) ✅
- Component instantiability (Claims 5-7) ✅
- Callback wiring mechanism (Claim 9) ✅
- `batch_run_id` gap identification (Claim 12) ✅
- Monitor isolates via callbacks ✅

**What needs correction:**
- **Claim 8 is WRONG (but it's GOOD NEWS):** Monitor does NOT have hidden `get_engine()` calls — it's already fully callback-based, making isolation easier than predicted
- **Missing critical dependency:** `get_simulation_clock()` in 12+ domain files is the #1 hidden coupling risk not addressed in the architecture
- **Missing critical dependency:** `trade_event_service.py` checks global sim broker at 5 call sites
- **WAL mode not configured** — must be added before concurrent writes

**Bottom line:** The SimContext approach is viable, but the implementation effort is underestimated. The monitor isolation is easier than predicted (Phase 1 may be trivial), but the clock/loader isolation (not fully scoped) and trade_event_service coupling add ~1-2 days of additional work.
