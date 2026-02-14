# Warrior Automation Code Health Audit

**Date**: 2026-02-13  
**Auditor**: Code Auditor Agent  
**Scope**: 35 files in `nexus2/domain/automation/` (17 warrior + 18 supporting)

---

## A. File Inventory

| # | File | Lines | Notes |
|---|------|------:|-------|
| 1 | `__init__.py` | 36 | ⚠️ SMALL |
| 2 | `ai_catalyst_validator.py` | 973 | Layer violation (DB commit) |
| 3 | `automation_logger.py` | 175 | |
| 4 | `catalyst_classifier.py` | 334 | Dead code (`classify_headlines`, `formatTime`) |
| 5 | `catalyst_search_service.py` | 180 | Dead code (`get_symbols_with_catalyst_type`) |
| 6 | `ema_check_job.py` | 560 | |
| 7 | `engine.py` | 323 | Dead code (`process_signal`—only test caller) |
| 8 | `indicator_service.py` | 416 | VWAP indicator duplication (L202-210 ≡ L301-309) |
| 9 | `ipo_service.py` | 224 | |
| 10 | `ma_affinity.py` | 332 | |
| 11 | `monitor.py` | 703 | NACbot monitor |
| 12 | `rejection_tracker.py` | 201 | |
| 13 | `reverse_split_service.py` | 316 | Dead code (`get_days_since_split`, `get_score_boost`) |
| 14 | `scheduler.py` | 591 | |
| 15 | `services.py` | 399 | Layer violation (imports route model); Dead (`initialize_engine`) |
| 16 | `signals.py` | 221 | |
| 17 | `trade_analysis_service.py` | 523 | |
| 18 | `trade_event_service.py` | 1008 | Layer violations (DB commit); Dead (`log_nac_stop_moved`—test only) |
| 19 | `unified_scanner.py` | 523 | |
| 20 | `validation.py` | 234 | |
| 21 | `warrior_engine.py` | 759 | Dead code (`_check_orb_setup`, `_enter_position`—test only, `reset_daily_fails`) |
| 22 | `warrior_engine_entry.py` | 1438 | **6 duplicated functions** (see D1) |
| 23 | `warrior_engine_types.py` | 265 | |
| 24 | `warrior_entry_execution.py` | 634 | |
| 25 | `warrior_entry_guards.py` | 442 | |
| 26 | `warrior_entry_helpers.py` | 373 | Canonical source of 5 helper functions |
| 27 | `warrior_entry_patterns.py` | 1254 | |
| 28 | `warrior_entry_scoring.py` | 201 | |
| 29 | `warrior_entry_sizing.py` | 189 | |
| 30 | `warrior_monitor.py` | 729 | |
| 31 | `warrior_monitor_exit.py` | 1176 | Dead code (`_check_profit_target`) |
| 32 | `warrior_monitor_scale.py` | 284 | |
| 33 | `warrior_monitor_sync.py` | 631 | |
| 34 | `warrior_types.py` | 174 | |
| 35 | `warrior_vwap_utils.py` | 255 | |

**Total**: ~16,473 lines across 35 files

---

## B. Dependency Graph

### Warrior Module Cluster

```
warrior_engine
  ├── imports: ai_catalyst_validator, trade_event_service, warrior_engine_entry,
  │            warrior_engine_types, warrior_monitor
  └── imported by: warrior_engine_entry, warrior_entry_execution,
                   warrior_entry_guards, warrior_entry_helpers,
                   warrior_entry_patterns, warrior_entry_sizing, warrior_vwap_utils

warrior_engine_entry
  ├── imports: trade_event_service, warrior_engine, warrior_engine_types,
  │            warrior_entry_execution, warrior_entry_guards,
  │            warrior_entry_helpers, warrior_entry_patterns,
  │            warrior_entry_scoring, warrior_entry_sizing,
  │            warrior_monitor_scale
  └── imported by: warrior_engine

warrior_monitor
  ├── imports: trade_event_service, warrior_monitor_exit,
  │            warrior_monitor_scale, warrior_monitor_sync, warrior_types
  └── imported by: warrior_engine, warrior_monitor_exit,
                   warrior_monitor_scale, warrior_monitor_sync

warrior_monitor_exit
  ├── imports: trade_event_service, warrior_monitor, warrior_types
  └── imported by: warrior_monitor

warrior_monitor_scale
  ├── imports: trade_event_service, warrior_monitor, warrior_types
  └── imported by: warrior_monitor, warrior_engine_entry

warrior_monitor_sync
  ├── imports: trade_event_service, warrior_monitor, warrior_types
  └── imported by: warrior_monitor

warrior_types -> (no local imports, imported by monitor cluster)
warrior_engine_types -> (no local imports, imported by entry cluster)
warrior_vwap_utils -> warrior_engine (circular: also imports itself)
```

### Non-Warrior Cluster

```
services -> engine, signals, trade_event_service, unified_scanner
engine -> signals
unified_scanner -> ipo_service, signals
ema_check_job -> ma_affinity
validation -> ai_catalyst_validator, catalyst_classifier
__init__ -> engine, monitor, scheduler, services, signals, unified_scanner
```

### Observations

- **No circular dependencies** between warrior files (imports use TYPE_CHECKING guards)
- `warrior_engine` is the central hub — imported by 6 warrior files
- `trade_event_service` is imported by 8 files (highest fan-in)
- `warrior_vwap_utils` has a self-import (L16: `from nexus2.domain.automation.warrior_vwap_utils import`) — used in docstring example, harmless but unusual

---

## C. Dead Code Analysis

### C1. Confirmed Dead — No Callers Anywhere in Codebase

These functions have **zero callers** across all 262 Python files in `nexus2/`:

| # | Function | File | Line | Evidence |
|---|----------|------|-----:|----------|
| 1 | `_check_orb_setup` | `warrior_engine.py` | 615 | Superseded by `check_orb_setup` in `warrior_engine_entry.py` |
| 2 | `_check_profit_target` | `warrior_monitor_exit.py` | 618 | Replaced by `_check_base_hit_target` |
| 3 | `_scale_into_existing_position` | `warrior_engine_entry.py` | 833 | Superseded by `scale_into_existing_position` in `warrior_entry_execution.py` |
| 4 | `ai_validate_catalyst` | `ai_catalyst_validator.py` | 485 | Module-level function never called |
| 5 | `classify_headlines` | `catalyst_classifier.py` | 263 | Method never called |
| 6 | `get_cached_headlines` | `ai_catalyst_validator.py` | 226 | Method never called |
| 7 | `get_days_since_split` | `reverse_split_service.py` | 216 | Method never called |
| 8 | `get_score_boost` | `reverse_split_service.py` | 250 | Method never called |
| 9 | `get_symbols_with_catalyst_type` | `catalyst_search_service.py` | 116 | Method never called |
| 10 | `initialize_engine` | `services.py` | 381 | Initializes old `AutomationEngine`, not `WarriorEngine` |
| 11 | `queue_comparison` | `ai_catalyst_validator.py` | 731 | Method never called |
| 12 | `reset_daily_fails` | `warrior_engine.py` | 670 | Method never called |

**Verify** (run for any function above):
```powershell
python -c "import pathlib; f='FUNCTION_NAME'; [print(f'{p}:{i+1}: {l.strip()}') for p in pathlib.Path('nexus2').rglob('*.py') for i,l in enumerate(p.read_text(encoding='utf-8',errors='replace').splitlines()) if f in l]"
```

### C2. Test-Only Functions — No Production Callers

These functions are only called from test files, never from production code:

| # | Function | File | Line | Callers |
|---|----------|------|-----:|---------|
| 1 | `_enter_position` | `warrior_engine.py` | 624 | 14 calls in `test_warrior_engine.py` only |
| 2 | `process_signal` | `engine.py` | 287 | 1 call in `test_full_simulation.py` only |
| 3 | `log_nac_stop_moved` | `trade_event_service.py` | 379 | 1 call in `test_trade_events.py` only |

> [!NOTE]
> These are safe to keep if those tests are still valuable. But `_enter_position` on `warrior_engine.py` appears to be the OLD entry path before extraction — tests may need updating to use the new `enter_position()` in `warrior_engine_entry.py`.

### C3. Stale Re-definitions in `warrior_engine_entry.py`

After Phase 2/3 extraction, the ORIGINAL function bodies were **kept** alongside `from ... import` re-exports:

```python
# Lines 28-34: re-imports from warrior_entry_helpers.py
from nexus2.domain.automation.warrior_entry_helpers import (
    check_volume_confirmed,
    check_active_market,
    check_volume_expansion,
    check_falling_knife,
    check_high_volume_red_candle,
)

# Lines 109-325: ORIGINAL BODIES STILL PRESENT (shadowed by import)
def check_volume_confirmed(candles, lookback=10): ...     # L109
def check_active_market(candles, min_bars=5, ...): ...    # L142
def check_volume_expansion(candles, ...): ...             # L210
def check_falling_knife(current_price, snapshot, ...): ...# L247
def check_high_volume_red_candle(candles, ...): ...       # L284
```

And for micro-pullback:
```python
# Line 45: import from patterns
from nexus2.domain.automation.warrior_entry_patterns import (
    check_micro_pullback_entry as _check_micro_pullback_pattern,
)

# Lines 682-831: ORIGINAL BODY STILL PRESENT
async def check_micro_pullback_entry(engine, watched, current_price):
    # 150 lines of duplicated code
```

> [!CAUTION]
> **These 6 duplicated functions are 380+ lines of dead code** that shadow the imports on lines 28-34 and 45. Python resolves to the LOCAL definition (not the import), so the imported versions from helpers are never actually used at runtime within this file. However, OTHER files that `from warrior_engine_entry import check_volume_confirmed` will get whichever binding resolves — which could be the local redefinition or the imported one depending on order.

**Verify** the shadowing:
```powershell
python -c "import ast; t=ast.parse(open('nexus2/domain/automation/warrior_engine_entry.py',encoding='utf-8').read()); defs=[n.name for n in ast.walk(t) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]; imps=[]; [imps.extend(a.name or a.asname for a in n.names) for n in ast.walk(t) if isinstance(n,ast.ImportFrom)]; overlap=set(defs)&set(imps); print(f'Shadowed: {overlap}')"
```

---

## D. Duplication Analysis

### D1. warrior_engine_entry.py ↔ warrior_entry_helpers.py (CRITICAL)

**6 exact-copy duplications** totaling ~380 lines:

| Function | `warrior_engine_entry.py` | `warrior_entry_helpers.py` | Lines |
|----------|------------------------:|-------------------------:|------:|
| `check_volume_confirmed` | L109-139 | L29-59 | 31 |
| `check_active_market` | L142-207 | L148-213 | 66 |
| `check_volume_expansion` | L210-244 | L62-96 | 35 |
| `check_falling_knife` | L247-281 | L216-250 | 35 |
| `check_high_volume_red_candle` | L284-325 | L99-140 | 42 |
| `check_micro_pullback_entry` | L682-831 | (in `warrior_entry_patterns.py` L613+) | 150 |

**Root cause**: Functions were extracted to helper modules but originals were never removed.

**Recommendation**: Delete lines 109-325 and 682-831 from `warrior_engine_entry.py` (380+ lines). The imports on L28-34 and L45 already bring in the canonical versions.

**Effort**: S (Small) — pure deletion, imports already correct.

### D2. VWAP Indicator Calculation Duplication

The VWAP status indicator (green/yellow/red) is duplicated verbatim:

**Location 1**: `indicator_service.py` L202-210 (in `compute_watchlist_indicators`)
```python
if vwap is None:
    vwap_ind = IndicatorValue("VWAP", "gray", 0, "VWAP: N/A")
elif current_price > vwap * 1.01:
    vwap_ind = IndicatorValue("VWAP", "green", vwap, f"VWAP: ${vwap:.2f} ✓")
elif current_price >= vwap * 0.99:
    vwap_ind = IndicatorValue("VWAP", "yellow", vwap, f"VWAP: ${vwap:.2f}")
else:
    vwap_ind = IndicatorValue("VWAP", "red", vwap, f"VWAP: ${vwap:.2f} ✗")
```

**Location 2**: `indicator_service.py` L301-309 (in `compute_position_health`)
```python
# Identical 8-line block
```

**Recommendation**: Extract to `_compute_vwap_indicator(current_price, vwap)` helper method.

**Effort**: S (Small)

---

## E. Layer Violations

| # | Violation | File | Line | Severity |
|---|-----------|------|-----:|----------|
| 1 | **Route model import** in domain | `services.py` | 27 | 🔴 High |
| 2 | Direct `db.commit()` in domain | `ai_catalyst_validator.py` | 844, 937 | 🟡 Medium |
| 3 | Direct `db.commit()` in domain | `trade_event_service.py` | 330 | 🟡 Medium |

### E1. Route Model Import (services.py L27)

```python
from nexus2.api.routes.scanner import run_scanner, ScannerRunRequest
```

Domain service is importing from the API layer. This is the `create_scanner_callback` function which is already marked `DEPRECATED` (L25). Dead code — should be removed entirely.

**Verify**:
```powershell
Select-String -Path "nexus2\domain\automation\services.py" -Pattern "from nexus2.api.routes"
```

### E2-E3. Direct DB Access

`ai_catalyst_validator.py` and `trade_event_service.py` perform `db.commit()` directly. These should go through a repository/adapter layer. Lower priority since they're established patterns.

---

## F. Consolidation Candidates

### F1. Files Below 100 Lines

Only `__init__.py` (36 lines) is below 100 lines. This is an appropriate size for a package init.

### F2. Potential Merges

| Merge Candidate | Current Lines | Rationale |
|----------------|-------------:|-----------|
| `warrior_types.py` (174) + `warrior_engine_types.py` (265) | 439 | Both define types/settings for warrior automation. `warrior_types` has monitor settings, `warrior_engine_types` has entry settings. Could unify into `warrior_types.py`. |
| `warrior_entry_sizing.py` (189) + `warrior_entry_scoring.py` (201) | 390 | Both are small, pure-function modules used only by `warrior_engine_entry.py`. Could merge into `warrior_entry_utils.py`. |

**Effort**: M (Medium) — requires import updates across multiple files.

> [!TIP]
> These merges are optional. The current split is defensible as it follows single-responsibility. Only merge if the team prefers fewer files over narrower files.

---

## G. Refactoring Recommendations (Prioritized)

| Priority | Issue | Files | Action | Effort |
|:--------:|-------|-------|--------|:------:|
| 1 | **D1**: 380+ lines of shadowed duplicates in `warrior_engine_entry.py` | `warrior_engine_entry.py` | Delete L109-325 and L682-831 | S |
| 2 | **C1**: 12 confirmed dead functions | 7 files | Delete 12 functions (~300 lines) | S |
| 3 | **E1**: Deprecated `create_scanner_callback` imports route model | `services.py` | Delete entire function (L19-49) | S |
| 4 | **C3**: Old `_enter_position` / `_check_orb_setup` on `warrior_engine.py` | `warrior_engine.py` | Delete dead methods, update tests | M |
| 5 | **D2**: VWAP indicator duplication | `indicator_service.py` | Extract helper method | S |
| 6 | **F2**: Type file consolidation | `warrior_types.py` + `warrior_engine_types.py` | Merge into single file | M |
| 7 | **E2-E3**: Direct DB commits in domain | `ai_catalyst_validator.py`, `trade_event_service.py` | Move to adapter layer | L |

> [!IMPORTANT]
> **Priority 1 (D1) is the highest-impact cleanup**: removing 380+ lines of exact duplicates that shadow their imported replacements. This is risk-free since the imports already exist.

---

## H. Verification Commands

All commands are PowerShell-compatible and can be run from the project root.

### Dead code verification (any function):
```powershell
python -c "import pathlib; f='FUNCTION_NAME'; [print(f'{p}:{i+1}: {l.strip()}') for p in pathlib.Path('nexus2').rglob('*.py') for i,l in enumerate(p.read_text(encoding='utf-8',errors='replace').splitlines()) if f in l]"
```

### Shadowed import verification:
```powershell
python -c "import ast; t=ast.parse(open('nexus2/domain/automation/warrior_engine_entry.py',encoding='utf-8').read()); defs=[n.name for n in ast.walk(t) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]; imps=[]; [imps.extend(a.name or a.asname for a in n.names) for n in ast.walk(t) if isinstance(n,ast.ImportFrom)]; overlap=set(defs)&set(imps); print(f'Shadowed: {overlap}')"
```

### Line count inventory:
```powershell
python -c "import pathlib; [print(f'{f.name}: {len(f.read_text(encoding=chr(117)+chr(116)+chr(102)+chr(45)+chr(56),errors=chr(114)+chr(101)+chr(112)+chr(108)+chr(97)+chr(99)+chr(101)).splitlines())} lines') for f in sorted(pathlib.Path('nexus2/domain/automation').glob('*.py'))]"
```

### Layer violation check:
```powershell
Select-String -Path "nexus2\domain\automation\services.py" -Pattern "from nexus2.api"
Select-String -Path "nexus2\domain\automation\*.py" -Pattern "db\.commit\(\)"
```
