# Concurrent Batch Runner v4 — Convergence Audit (Round 4)

> **Auditor:** Code Auditor Specialist (Claude)
> **Date:** 2026-02-10
> **Scope:** Convergence confirmation — verify all 7 prior issues addressed, adversarial state hunt
> **Architecture Doc:** [concurrent_batch_runner_architecture.md](file:///C:/Users/ftbbo/.gemini/antigravity/brain/e56e9f8f-208c-46dc-8c63-d13dcafec674/concurrent_batch_runner_architecture.md)
> **Mode:** READ-ONLY forensic audit — no code modified

---

## Task 1: Hidden State Catalog Completeness (10 items)

Verified `SimContext.create()` (v4 doc L74-117) against every `self._*` and `self.*` assignment in all three `__init__` methods.

| # | Catalog Item | Owner | Source | In `SimContext.create()`? | Evidence |
|---|-------------|-------|:------:|:---:|----------|
| 1 | `_recently_exited` dict | Monitor | R2 | ✅ YES | L97: `monitor._recently_exited = {}` |
| 2 | `_recently_exited_sim_time` dict | Monitor | R2 | ✅ YES | L98: `monitor._recently_exited_sim_time = {}` |
| 3 | `recently_exited.json` disk file | Monitor | R2 | ✅ YES | L96: `monitor._recently_exited_file = None` |
| 4 | `_watchlist` dict | Engine | R3 | ✅ YES | L101-105: `WarriorEngine(...)` creates new instance → clean `_watchlist = {}` (L89) |
| 5 | `_blacklist` set | Engine | R3 | ✅ YES | New engine → clean `_blacklist = set()` (L92) |
| 6 | `_pending_entries` dict | Engine | R3 | ✅ YES | New engine → clean `_pending_entries = {}` (L95) |
| 7 | `_symbol_fails` dict | Engine | R3 | ✅ YES | New engine → clean `_symbol_fails = {}` (L102) |
| 8 | `stats._seen_candidates` set | Engine | R3 | ✅ YES | New engine → `self.stats = WarriorEngineStats()` (L77) → `_seen_candidates: set = field(default_factory=set)` (types L150) |
| 9 | `pending_entries.json` disk file | Engine | R3 | ✅ YES | L106: `engine._pending_entries_file = None` |
| 10 | `_cache` dict | Scanner | R3 | ✅ YES | L103: `scanner=WarriorScannerService()` creates new scanner → clean `_cache = {}` (scanner L506) |

**Verdict: 10/10 catalog items covered by `SimContext.create()`.** ✅

---

## Task 2: Adversarial — Additional Mutable State Hunt

Exhaustive review of every `self.*` assignment in `__init__` for all three classes, looking for mutable state NOT in the catalog that could cause cross-case contamination.

### WarriorEngine.__init__ (L61-122) — Complete Inventory

| Attribute | Line | Type | Mutable? | In Catalog? | Cross-Case Risk? |
|-----------|:----:|------|:---:|:---:|----------|
| `config` | L67 | WarriorEngineConfig (dataclass) | Mostly immutable fields | No | ❌ None — config is read-only during execution |
| `scanner` | L68 | WarriorScannerService | Contains `_cache` | `_cache` is #10 | ✅ Covered |
| `monitor` | L70-74 | WarriorMonitor | Contains state | #1-3 | ✅ Covered |
| `state` | L76 | Enum | Scalar | No | ❌ None — per-instance |
| `stats` | L77 | WarriorEngineStats | Contains `_seen_candidates` | #8 | ✅ Covered |
| `_watchlist` | L89 | Dict | **YES** | #4 | ✅ Covered |
| `_blacklist` | L92 | set | **YES** | #5 | ✅ Covered |
| `_pending_entries` | L95 | Dict | **YES** | #6 | ✅ Covered |
| `_pending_entries_file` | L96 | Path | Disk handle | #9 | ✅ Covered |
| `_symbol_fails` | L102 | Dict | **YES** | #7 | ✅ Covered |
| `_max_fails_per_symbol` | L103 | int | Scalar | No | ❌ None — immutable |
| `_scan_task` | L106 | asyncio.Task / None | Reference | No | ❌ None — batch runner doesn't use `start()`, calls `check_entry_triggers` directly |
| `_watch_task` | L107 | asyncio.Task / None | Reference | No | ❌ Same — not used in batch path |
| `_scan_interrupt` | L110 | asyncio.Event / None | Reference | No | ❌ Same — not used in batch path |
| `_last_scan_started` | L111 | datetime / None | Scalar | No | ❌ None — per-instance, informational |
| `_last_scan_result` | L112 | dict / None | **YES** | No | ⚠️ **See analysis below** |
| Callbacks (L115-122) | L115-122 | Callable / None | References | No | ❌ None — set per-context via `wire_batch_callbacks()` |

**A1: `_last_scan_result` (Engine L112)** — This is a mutable dict assigned in `_run_scan()` (L438-452). However, in batch mode the scanner is called via `check_entry_triggers` which does NOT call `_run_scan()` — it calls the delegated `check_entry_triggers()` function directly. The `_run_scan()` method is only invoked by `_scan_loop()` which is a background task that batch runner does NOT start. **No risk in batch path.**

### WarriorScannerService.__init__ (L497-506) — Complete Inventory

| Attribute | Line | Type | Mutable? | In Catalog? | Cross-Case Risk? |
|-----------|:----:|------|:---:|:---:|----------|
| `settings` | L503 | WarriorScanSettings | Dataclass (read-only) | No | ❌ None |
| `market_data` | L504 | UnifiedMarketData | Stateful service | No | ⚠️ **See analysis below** |
| `alpaca_broker` | L505 | Optional broker ref | Reference | No | ❌ None — read-only |
| `_cache` | L506 | Dict | **YES** | #10 | ✅ Covered |

**A2: `market_data` (Scanner L504)** — `UnifiedMarketData` is a data adapter. If `WarriorScannerService()` is called without arguments (as in `SimContext.create()` L103), it creates a **new** `UnifiedMarketData()` instance. In batch mode, the scanner's `scan()` is NOT called (batch uses `check_entry_triggers` for already-loaded watchlist candidates). Even if scanner called market data, each scanner gets a fresh instance. **No risk.**

### WarriorMonitor.__init__ (L53-107) — Complete Inventory

| Attribute | Line | Type | Mutable? | In Catalog? | Cross-Case Risk? |
|-----------|:----:|------|:---:|:---:|----------|
| `settings` | L54 | WarriorMonitorSettings | Dataclass | No | ❌ None |
| `_running` | L56 | bool | Scalar | No | ❌ Per-instance |
| `_task` | L57 | asyncio.Task / None | Reference | No | ❌ Not started in batch |
| `_positions` | L60 | Dict | **YES** | No | ❌ Per-instance — new monitor per context, starts empty |
| `_get_price` → `_on_profit_exit` | L63-73 | Callable / None | References | No | ❌ Set via `wire_batch_callbacks()` |
| `_sync_counter` | L77 | int | Scalar | No | ❌ Per-instance |
| `_sync_interval` | L78 | int | Scalar | No | ❌ Immutable |
| `checks_run` | L81 | int | Scalar | No | ❌ Per-instance counter |
| `exits_triggered` | L82 | int | Scalar | No | ❌ Per-instance counter |
| `partials_triggered` | L83 | int | Scalar | No | ❌ Per-instance counter |
| `last_check` | L84 | datetime / None | Scalar | No | ❌ Per-instance |
| `last_error` | L85 | str / None | Scalar | No | ❌ Per-instance |
| `sim_mode` | L88 | bool | Scalar | No | ❌ Set in SimContext.create L95 |
| `realized_pnl_today` | L91 | Decimal | Scalar | No | ❌ Per-instance |
| `_pnl_date` | L92 | datetime / None | Scalar | No | ❌ Per-instance |
| `_recently_exited` | L96 | Dict | **YES** | #1 | ✅ Covered |
| `_recovery_cooldown_seconds` | L97 | int | Scalar | No | ❌ Immutable |
| `_recently_exited_file` | L98 | Path | Disk handle | #3 | ✅ Covered |
| `_recently_exited_sim_time` | L103 | Dict | **YES** | #2 | ✅ Covered |
| `_reentry_cooldown_minutes` | L104 | int | Scalar | No | ❌ Immutable |

**Verdict: NO additional mutable state with cross-case contamination risk found.** ✅

All mutable dicts/sets that could accumulate across cases are either:
1. In the catalog (10 items) and explicitly handled, OR
2. Per-instance (new object created per `SimContext`) and start empty

---

## Task 3: WarriorEngine Constructor Params

**Claim:** Engine `__init__` already accepts `scanner` and `monitor` params.

**Evidence:** ([warrior_engine.py:L61-65](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine.py#L61-L65))

```python
def __init__(
    self,
    config: Optional[WarriorEngineConfig] = None,
    scanner: Optional[WarriorScannerService] = None,
    monitor: Optional[WarriorMonitor] = None,
):
```

When `scanner` is passed, L68 uses it directly: `self.scanner = scanner or WarriorScannerService()`.
When `monitor` is passed, L70-71 uses it directly: `if monitor: self.monitor = monitor`.

**Verdict: ✅ CONFIRMED.** The v4 doc's `SimContext.create()` code is a valid constructor call.

---

## Task 4: WarriorEngineConfig(sim_only=True) Pattern

**Claim:** `WarriorEngineConfig(sim_only=True)` is a valid constructor pattern.

**Evidence:** ([warrior_engine_types.py:L53-103](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_types.py#L53-L103))

```python
@dataclass
class WarriorEngineConfig:
    """Configuration for Warrior automation engine."""
    # ... (many fields) ...
    sim_only: bool = False  # Default to paper trading on Alpaca (LINE 103)
```

Since `WarriorEngineConfig` is a standard `@dataclass`, keyword constructor `WarriorEngineConfig(sim_only=True)` is valid Python. Default values are provided for all fields.

> [!NOTE]
> `sim_only=True` controls `_scan_loop` behavior (L362: `if not self.config.sim_only: ... market calendar checks`) and `_watch_loop` (L559: `if self.config.sim_only: ... historical replay check`). In batch mode, neither loop is started — the batch runner calls `check_entry_triggers` and `_check_all_positions()` directly. The flag is still useful as a safety marker.

**Verdict: ✅ CONFIRMED.** Valid pattern.

---

## Task 5: Standard Re-verification (S1-S5)

| # | Claim | Result | Evidence |
|---|-------|:------:|----------|
| S1 | Monitor has zero `get_engine()` calls | ✅ PASS | `grep_search` for `get_engine` in all 4 monitor files: `warrior_monitor.py` (0 results), `warrior_monitor_exit.py` (0 results), `warrior_monitor_sync.py` (0 results), `warrior_monitor_scale.py` (0 results) |
| S2 | All clock calls are runtime function-level imports | ✅ PASS | Confirmed by R3 and re-verified: no module-level `from ... import get_simulation_clock` in batch-path files. All inside function bodies. |
| S3 | `get_simulation_clock()` has exactly 1 definition | ✅ PASS | `grep_search` for `def get_simulation_clock` — exactly 1 result at `sim_clock.py:L308` |
| S4 | No `batch_run_id` in warrior_db | ✅ PASS | `grep_search` for `batch_run_id` in `warrior_db.py` — 0 results |
| S5 | No WAL mode configured | ✅ PASS | `grep_search` for `journal_mode` and `WAL` in `db/` — 0 results in `.py` files |

---

## Convergence Assessment

| Check | Result |
|-------|:------:|
| Hidden State Catalog (10 items) | ✅ All covered by `SimContext.create()` |
| Adversarial: additional mutable state in Engine | ✅ None with cross-case risk |
| Adversarial: additional mutable state in Scanner | ✅ None with cross-case risk |
| Adversarial: additional mutable state in Monitor | ✅ None with cross-case risk |
| Engine accepts `scanner` + `monitor` params | ✅ Confirmed (L64-65) |
| `WarriorEngineConfig(sim_only=True)` valid | ✅ Confirmed (dataclass L103) |
| S1: Monitor has 0 `get_engine()` calls | ✅ Re-verified |
| S2: Clock imports are function-level | ✅ Re-verified |
| S3: `get_simulation_clock` single definition | ✅ Re-verified |
| S4: No `batch_run_id` in DB | ✅ Re-verified |
| S5: No WAL mode yet | ✅ Re-verified |

- New critical issues found: **0**
- New medium issues found: **0**
- New low issues found: **0**

---

## Verdict

### ✅ CONVERGED

The v4 architecture document fully addresses all 7 issues discovered across 3 prior audit rounds. No new issues found. The `SimContext.create()` factory correctly creates isolated instances of all stateful components, and the Hidden State Catalog is complete — every mutable dict, set, and disk file that could cause cross-case contamination is accounted for.

### Progress Across Rounds

| Round | Critical | Medium | Low | Status |
|:-----:|:--------:|:------:|:---:|--------|
| R1 | 3 | 1 | 2 | Not converged |
| R2 | 0 | 2 | 0 | Not converged |
| R3 | 0 | 2 | 2 | Not converged |
| **R4** | **0** | **0** | **0** | **✅ Converged** |

### Recommendation

The architecture is ready for implementation. Suggest updating:
1. Architecture doc convergence header to reference this R4 report
2. ROADMAP.md to move concurrent batch runner from "planned" to "ready for implementation"

---

## Overall Rating

**HIGH** — All claims verified, no new issues. Architecture has converged after 4 rounds.
