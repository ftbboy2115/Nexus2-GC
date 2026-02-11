# Phase 9 Round 2 Validation Report

**Validator**: Claude (Audit Validator Agent)  
**Date**: 2026-02-11  
**Scope**: Independent verification of RC1 (stats) and RC2 (blacklist) claims from Phase 9 Round 2 audit

---

## RC1 Validation (stats accumulation)

The auditor claims `entries_triggered`, `candidates_found`, and `_seen_candidates` accumulate across sequential cases, "affecting `top_x_picks` ranking logic" and "entry selectivity."

I traced **every read** of these fields in the codebase:

| Stats Field | Used in entry/exit decisions? | Evidence |
|-------------|------------------------------|----------|
| `entries_triggered` | **NO** | WRITE at `warrior_engine_entry.py:L1031` (increment), `L1046` (decrement). READ at `warrior_engine.py:L696` — **status dict display ONLY**. Never read by any guard, gate, or ranking logic. |
| `_seen_candidates` | **NO** | READ at `warrior_engine.py:L418` — gates `candidates_found` counter increment only. The counter itself is display-only at L695. Does NOT affect watchlist addition, entry decisions, or ranking. |
| `candidates_found` | **NO** | WRITE at `warrior_engine.py:L420` (increment). READ at `warrior_engine.py:L695` — **status dict display ONLY**. |
| `scans_run` | **NO** | WRITE at `warrior_engine.py:L409`. READ at `warrior_engine.py:L694` — **status dict display ONLY**. |
| `daily_pnl` | **GATED but disabled** | READ at `warrior_engine.py:L640`: `if self.stats.daily_pnl <= -self.config.max_daily_loss:` — **this IS a gate**. But `max_daily_loss = Decimal("999999")` (warrior_engine_types.py:L89), effectively disabled. Would require -$999,999 accumulated P&L to trigger. |
| `orders_submitted` | **NO** | WRITE at `warrior_engine_entry.py:L1155`. READ at `warrior_engine.py:L697` — **display only**. |
| `orders_filled` | **NO** | Display only in status dict. |

### Critical Debunk: `top_x_picks` Does NOT Use Stats

The auditor specifically claimed stats accumulation "affect[s] `top_x_picks` ranking logic." This is **FALSE**.

`top_x_picks` ranking at `warrior_entry_guards.py:L61-75` works as follows:
```python
# L61-68
if engine.config.top_x_picks > 0:
    all_watched = sorted(
        engine._watchlist.values(),
        key=lambda w: w.dynamic_score,  # <-- Uses dynamic_score, NOT stats
        reverse=True,
    )
    top_x_symbols = {w.candidate.symbol for w in all_watched[:engine.config.top_x_picks]}
```

`dynamic_score` (warrior_engine_types.py:L239-263) is calculated from:
- `candidate.quality_score` (static, set at scan time)
- VWAP/EMA trend bonuses (+3, +1, -2)

**It reads ZERO fields from `engine.stats`.** The auditor invented a connection that does not exist in the code.

### Monitor Stats (`checks_run`, `exits_triggered`)

Also verified these accumulate but are **logging/display only**:
- `warrior_monitor.py:L527`: `self.checks_run += 1` — increment per tick
- `warrior_monitor.py:L676-677`: used in status display only
- `warrior_monitor_exit.py:L897`: `monitor.exits_triggered += 1` — increment on exit
- **Never gate any entry/exit decision.**

**Verdict**: **RC1 DISPROVED as P&L divergence cause.** All stats fields are logging/telemetry only. None gate entry, exit, or ranking decisions. The auditor's narrative about "entry selectivity" and "top_x_picks ranking" was hand-waving without a code-level mechanism.

> [!CAUTION]
> Still worth resetting `engine.stats` for cleanliness between cases, but it is NOT the cause of P&L differences.

---

## RC2 Validation (blacklist)

The auditor claims `_blacklist` accumulates symbols rejected by the broker, blocking those symbols in subsequent cases.

| Question | Answer | Evidence |
|----------|--------|----------|
| Can MockBroker trigger `_blacklist.add()`? | **NO** | `_blacklist.add()` fires at `warrior_engine_entry.py:L1145-1146` ONLY when `isinstance(order_result, dict) and order_result.get("blacklist")`. MockBroker's `submit_bracket_order` returns `BrokerOrderResult` **dataclass objects**, not dicts. `isinstance(BrokerOrderResult(...), dict)` is always `False`. |
| Would BATL be blacklisted after D1? | **NO** | Since MockBroker can't trigger `_blacklist.add()`, BATL would never enter the blacklist during sim mode. |
| Does `_blacklist` explain D3-D9 (unique symbols)? | **NO** | Even if blacklisting could occur (it can't), D3-D9 are all unique symbols appearing only once — blacklisting by definition can't affect them. |

### Verification Details

**`_blacklist.add()` trigger path** (warrior_engine_entry.py:L1144-1146):
```python
# Check for blacklist response from broker
if isinstance(order_result, dict) and order_result.get("blacklist"):
    engine._blacklist.add(symbol)
```

**MockBroker returns** (mock_broker.py:L212-215, L277, L311, L563):
- `BrokerOrderResult` dataclass with `status=BrokerOrderStatus.REJECTED`
- This is a **dataclass object**, not a dict
- The `isinstance(order_result, dict)` guard will ALWAYS be `False`

**`_blacklist` IS checked in entry guards** (warrior_entry_guards.py:L84-86):
```python
# BLACKLIST CHECK
if symbol in engine.config.static_blacklist or symbol in engine._blacklist:
    return False, "Blacklisted"
```
This check exists BUT `_blacklist` is always EMPTY in sim mode, so it never blocks anything.

**Verdict**: **RC2 DISPROVED as P&L divergence cause.** MockBroker cannot populate `_blacklist` because it returns dataclass objects, not dicts. The blacklist remains empty throughout the entire batch run in both runners.

---

## Config Differences (H5)

The auditor's state inventory shows `config` is "❌ Retained from `__init__`" in sequential vs "✅ Fresh `WarriorEngineConfig(sim_only=True)`" in concurrent.

| Runner | `apply_settings_to_config` called? | Config values |
|--------|-----------------------------------|---------------|
| Sequential | **YES** — at `warrior_engine.py:L80-86` in `WarriorEngine.__init__()` | Loads from `data/warrior_settings.json` |
| Concurrent | **YES** — at `warrior_engine.py:L80-86` in `WarriorEngine.__init__()` (same code path) | Loads from **same** `data/warrior_settings.json` |

Both `WarriorEngine()` and `WarriorEngine(config=WarriorEngineConfig(sim_only=True))` execute the same `__init__` code at L80-86:
```python
try:
    from nexus2.db.warrior_settings import load_warrior_settings, apply_settings_to_config
    saved = load_warrior_settings()
    if saved:
        apply_settings_to_config(self.config, saved)
except Exception as e:
    print(f"[Warrior] Failed to load saved settings: {e}")
```

Both load and apply the identical `warrior_settings.json`:
```json
{
  "max_positions": 10,
  "max_daily_loss": 999999.0,
  "risk_per_trade": 100.0,
  "max_capital": 5000.0,
  "max_candidates": 5,
  "scanner_interval_minutes": 3,
  "max_shares_per_trade": 1
}
```

The `sim_only=True` in the concurrent path only sets `config.sim_only = True` — the sequential engine's config also has sim_only configured through the startup flow.

**Verdict**: **Config difference DISPROVED as divergence source.** Both engines load identical settings from the same JSON file during `__init__`.

---

## Per-Case Validation

| Case | Auditor's Claimed Cause | Validated? | Actual Cause |
|------|------------------------|------------|--------------|
| D1 (BATL, Δ=$1,555) | RC1: "stats cause more selective entries" | **NO** — no code path reads `entries_triggered` for selectivity | Unknown — see "Actual Root Cause" below |
| D5 (TNMG, Δ=$324) | RC1: "entries_triggered counter is significantly elevated causing more selective entries" | **NO** — `entries_triggered` is never read by entry logic | Unknown — see "Actual Root Cause" below |

The auditor said "concurrent runner takes more aggressive entry attempts" (D1) and "entries_triggered counter causes more selective entries" (D5). **Both claims require a code path where `entries_triggered` changes entry behavior.** No such code path exists. The auditor was generating plausible-sounding narratives without verifying the actual code.

---

## Actual Root Cause: P&L SOURCE MISMATCH

> [!IMPORTANT]
> RC1 and RC2 are both disproved. The divergence has a **different root cause** not identified by the auditor.

### The P&L Calculation Paths Are Different

| Aspect | Sequential Runner | Concurrent Runner |
|--------|-------------------|-------------------|
| **P&L source** | `get_all_warrior_trades()` from `warrior_db` (L1469-1502) | `ctx.broker.get_account()` (sim_context.py:L531-534) |
| **What it reads** | SQLite `warrior_trades` table — `realized_pnl` from logged entries/exits | MockBroker internal `_realized_pnl` from actual fills |
| **DB isolation** | Shared `warrior.db` file with `purge_sim_trades()` between cases (L1387-1392) | Per-process in-memory SQLite (sim_context.py:L455-458) |

**Sequential runner** (warrior_sim_routes.py:L1469-1502):
```python
# Query completed trades from warrior_db (populated by Layer 1 fixes)
from nexus2.db.warrior_db import get_all_warrior_trades
warrior_result = get_all_warrior_trades(limit=100, status_filter="closed")
# ...
account = broker.get_account()
realized_pnl = round(account.get("realized_pnl", 0), 2)
total_pnl = round(realized_pnl + unrealized_pnl, 2)
```

The sequential runner reads P&L from `broker.get_account()` for the FINAL number, but the trade **detail rows** come from `warrior_db`. The `purge_sim_trades()` at L1387-1392 attempts to clear between cases but depends on timing and correct `is_sim` filtering.

**Concurrent runner** (sim_context.py:L531-534):
```python
account = ctx.broker.get_account()
realized = round(account.get("realized_pnl", 0), 2)
unrealized = round(account.get("unrealized_pnl", 0), 2)
total_pnl = round(realized + unrealized, 2)
```

Pure MockBroker account — completely isolated.

### Key Differences Between Runners NOT Addressed by RC1/RC2

| Unresolved State | Sequential | Concurrent | Could Affect P&L? |
|------------------|-----------|------------|-------------------|
| `monitor.settings` (exit params) | ❌ Retained from startup/UI changes | ✅ Fresh `WarriorMonitorSettings()` defaults | **YES** — `mental_stop_cents`, `max_loss_cents`, exit thresholds directly control exits |
| `monitor._pnl_date` | ❌ Retained | ✅ Fresh `None` | **MAYBE** — could affect `realized_pnl_today` reset timing |
| `engine.state` transition | Set by prior `engine.start()` / historical replay flow | Explicitly set to `RUNNING` at L430 | **MAYBE** — if state isn't `RUNNING`/`PREMARKET`, entry checks skip |
| `warrior_db` trade logging | Shared SQLite (trade contamination vectors) | Per-process in-memory SQLite | **YES** — if `purge_sim_trades()` is incomplete, `log_warrior_entry` duplicate checking could block entries |

### Most Likely Actual Root Cause

**`monitor.settings`** is the strongest candidate. If the user changed monitor exit parameters via the UI (e.g., `mental_stop_cents`, `base_hit_pct`, `max_loss_cents`), those changes persist in the sequential runner's singleton monitor but are NOT applied to the concurrent runner's fresh `WarriorMonitor()`. Different exit parameters = different exit timing = different P&L.

This would explain:
- Why divergence is NOT monotonic (different cases have different sensitivity to exit parameters)
- Why some cases show sequential HIGHER and others LOWER (tighter stops help some trades, hurt others)
- Why the fix for `_positions` and `_recently_exited` resolved SOME cases (FLYE, RVSN) but not all

---

## Overall Rating

**LOW — Root causes not proven, hand-waving detected.**

The auditor identified two plausible-sounding root causes (RC1: stats, RC2: blacklist) but provided **zero runtime evidence** and **failed to trace the actual code paths**. Independent verification shows:

1. **RC1 is FALSE** — `entries_triggered` and `_seen_candidates` are logging-only; the claimed "top_x_picks ranking" connection does not exist in the code
2. **RC2 is FALSE** — MockBroker cannot populate `_blacklist` (returns dataclass, not dict); blacklist is always empty in sim mode
3. **H5 is FALSE** — both engines load the same settings from `warrior_settings.json`
4. **Per-case narratives (D1-D9) have no mechanism** — they read like plausible stories built on a false premise

The auditor's state inventory table (Section 2) was accurate and valuable. The ROOT CAUSE ANALYSIS (Section 3) was fiction built on unverified assumptions.

### Recommendation

Before implementing fixes for `engine.stats` and `engine._blacklist` (which are still good hygiene), investigate:

1. **`monitor.settings`** differences — compare `WarriorMonitorSettings` defaults vs the singleton's actual values
2. **`warrior_db` trade contamination** — verify that `purge_sim_trades()` completely clears between sequential cases
3. **Add P&L source debug logging** — print both MockBroker P&L AND warrior_db P&L for each sequential case to identify the divergence source

---

## Files Analyzed

| File | Evidence Gathered |
|------|-------------------|
| [warrior_engine_types.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_types.py) | `WarriorEngineStats` fields (L138-150), `WarriorEngineConfig` defaults (L53-136), `dynamic_score` (L239-263) |
| [warrior_engine.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine.py) | `__init__` settings loading (L80-86), `_can_open_position` (L628-644), `_run_scan` stats usage (L407-420) |
| [warrior_engine_entry.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py) | `entries_triggered` writes (L1031, L1046), `_blacklist.add` trigger (L1145-1146), `orders_submitted` (L1155) |
| [warrior_entry_guards.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py) | `top_x_picks` ranking (L61-75), `min_entry_score` (L81), `_blacklist` check (L85), `_symbol_fails` (L89) |
| [mock_broker.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/mock_broker.py) | Return types (L212-215, L277, L311, L563) — `BrokerOrderResult` dataclass, not dict |
| [warrior_sim_routes.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py) | `load_historical_test_case` (L690-1097), `run_batch_tests` (L1306-1571), `sim_submit_order_historical` (L1016-1049) |
| [sim_context.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py) | `SimContext.create` (L32-62), `load_case_into_context` (L140-437), P&L collection (L531-534) |
| [warrior_settings.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/db/warrior_settings.py) | `apply_settings_to_config` (L157-187) |
| [warrior_monitor.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor.py) | `checks_run`/`exits_triggered` (L81-82, L525-527, L676-677) |
| [warrior_settings.json](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/data/warrior_settings.json) | Actual settings on disk |
