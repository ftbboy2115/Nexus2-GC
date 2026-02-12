# Phase 11 Audit Validation Report

**Validator**: Audit Validator Agent  
**Date**: 2026-02-12  
**Scope**: Validate all 8 claims (C1-C5, A1-A3) from `phase11_audit_report.md`  
**Context**: [implementation_plan.md](file:///C:/Users/ftbbo/.gemini/antigravity/brain/e56e9f8f-208c-46dc-8c63-d13dcafec674/implementation_plan.md)

---

## Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| C1 | `_pending_entries_file` None crash | **PASS** | `sim_context.py:62` sets `None`, `warrior_engine.py:191` calls `.parent.mkdir()` with no guard |
| C2 | `_recently_exited_file` None crash | **PASS** | `sim_context.py:42` sets `None`, `warrior_monitor.py:138` calls `.parent.mkdir()` with no guard |
| C3 | `_get_quote_with_spread` float/dict mismatch | **PASS** | `sim_context.py:370` and `warrior_sim_routes.py:981` both wire `sim_get_price` (returns float); 3 downstream callers use `.get()` |
| C4 | Missing TML event for re-entry | **PASS** | `trade_event_service.py` has no `reentry` / `re_entry` method; `warrior_engine.py:232-235` only uses `logger.info` |
| C5 | PSM re-entry flow integrity | **PASS** | `CLOSED` is terminal (line 55: `set()`), re-entry creates new `position_id` via `WatchedCandidate` reset |
| A1 | Fail-closed violation in spread filter | **PASS** | `warrior_entry_guards.py:302-306` logs "proceeding with caution", line 307-308 catches exception and proceeds |
| A2 | C3 affects entry guards | **PASS** | `warrior_entry_guards.py:283` calls `spread_data.get("bid", 0)` — crashes on float, caught by except at line 307 → `return True` |
| A3 | Crash ordering in `handle_exit` | **PASS** | `warrior_monitor_exit.py:1004` runs `_save_recently_exited()` before `remove_position()` at line 1037 |

---

## Detailed Evidence

### C1: `_pending_entries_file` None Crash — PASS

**Auditor claims**: `sim_context.py:62` sets `engine._pending_entries_file = None`, and `warrior_engine.py:191` calls `.parent.mkdir()` on it.

**Verified**:
- [sim_context.py:62](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L62): `engine._pending_entries_file = None` ✅
- [warrior_engine.py:191](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine.py#L191): `self._pending_entries_file.parent.mkdir(parents=True, exist_ok=True)` — no None guard ✅
- Exception caught at line 194 — produces console warning, does not crash ✅
- Auditor's analysis of `_load_pending_entries` ordering is correct — default path is valid at `__init__` time ✅

### C2: `_recently_exited_file` None Crash — PASS

**Auditor claims**: `sim_context.py:42` sets `monitor._recently_exited_file = None`, and `warrior_monitor.py:138` calls `.parent.mkdir()` on it.

**Verified**:
- [sim_context.py:42](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L42): `monitor._recently_exited_file = None` ✅
- [warrior_monitor.py:138](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor.py#L138): `self._recently_exited_file.parent.mkdir(parents=True, exist_ok=True)` — no None guard ✅
- Exception caught at line 141 — produces console warning ✅
- Auditor's caller table (handle_exit at L1004, warrior_positions at L371) confirmed at `warrior_monitor_exit.py:1004` ✅

### C3: `_get_quote_with_spread` Float/Dict Mismatch — PASS (HIGH SEVERITY)

**Auditor claims**: Both runners wire `sim_get_price` (returns float) but downstream callers expect dict with `.get()`.

**Verified**:

Wiring sites:
- [sim_context.py:370](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L370): `get_quote_with_spread=sim_get_price,` ✅
- [warrior_sim_routes.py:981](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L981): `get_quote_with_spread=sim_get_price,` ✅

`sim_get_price` definition (sim_context.py:281-283):
```python
async def sim_get_price(symbol: str, _broker=ctx.broker):
    price = _broker.get_price(symbol)
    return price if price is not None else None  # Returns float!
```

Downstream callers that use `.get()` on the result:
- [warrior_monitor_exit.py:273](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py#L273): `spread_data.get("liquidity_status", "unknown")` ✅
- [warrior_monitor_scale.py:180](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_scale.py#L180): `spread_data.get("ask")` ✅
- [warrior_entry_guards.py:283](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py#L283): `spread_data.get("bid", 0)` ✅

**Impact confirmed**: All three `.get()` calls will raise `AttributeError: 'float' object has no attribute 'get'`, caught by surrounding `try/except`, silently disabling three safety mechanisms in sim mode. ✅

### C4: Missing TML Event for Re-Entry — PASS

**Verified**:
- Searched `trade_event_service.py` for `reentry|re_entry|re.entry` — **zero matches** ✅
- [warrior_engine.py:232-235](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine.py#L232-L235) uses only `logger.info` for re-entry notification ✅
- Auditor's list of existing TML methods matches (checked: `log_warrior_entry`, `log_warrior_exit`, `log_warrior_scale_in`, `log_warrior_stop_moved`, `log_warrior_guard_block` all exist) ✅

### C5: PSM Re-Entry Flow Integrity — PASS (SOUND)

**Verified**:
- [position_state_machine.py:55](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/positions/position_state_machine.py#L55): `PositionStatus.CLOSED: set()` — terminal, no transitions out ✅
- [warrior_engine.py:222-224](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine.py#L222-L224): Re-entry resets `entry_triggered` and `position_opened` on `WatchedCandidate`, not the PSM position ✅
- [warrior_entry_guards.py:120-137](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py#L120-L137): Both live and sim cooldown mechanisms verified ✅
- [warrior_monitor_exit.py:1002-1037](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py#L1002-L1037): Ordering confirmed: cooldown set → save → re-entry enable → position remove ✅

### A1: Fail-Closed Violation in Entry Spread Filter — PASS

**Verified**:
- [warrior_entry_guards.py:302-306](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py#L302-L306):
  ```python
  elif bid <= 0 or ask <= 0:
      logger.warning(
          f"[Warrior Entry] {symbol}: No valid bid/ask data "
          f"(bid=${bid}, ask=${ask}) - proceeding with caution"  # ← VIOLATION
      )
  ```
  Falls through to `return True, "", current_ask` at line 310 ✅

- [warrior_entry_guards.py:307-308](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py#L307-L308):
  ```python
  except Exception as e:
      logger.warning(f"[Warrior Entry] {symbol}: Spread check failed: {e} - proceeding")
  ```
  Also falls through to `return True` ✅

**Both violate the fail-closed mandate** ("Better to not trade than trade blind") ✅

### A2: C3 Affects Entry Guards — PASS (HIGH SEVERITY)

**Verified**: Extension of C3. In sim mode, `engine._get_quote_with_spread` is `sim_get_price` which returns a float. At [warrior_entry_guards.py:281-283](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py#L281-L283):

```python
spread_data = await engine._get_quote_with_spread(symbol)
if spread_data:  # float is truthy → True
    bid = spread_data.get("bid", 0)  # ← AttributeError: 'float' has no .get()
```

This crashes, caught by except at line 307, which then **proceeds** (A1 violation). Combined effect: **spread filter is completely bypassed in sim** via two independent paths. ✅

### A3: Crash Ordering in `handle_exit` — PASS (THEORETICAL)

**Verified**:
- [warrior_monitor_exit.py:1003-1004](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py#L1003-L1004): `_recently_exited` set, then `_save_recently_exited()` called
- [warrior_monitor_exit.py:1037](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py#L1037): `remove_position()` called later
- [warrior_monitor.py:132-142](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor.py#L132-L142): `_save_recently_exited` has `try/except` ✅

**Auditor's assessment confirmed**: Currently mitigated by the `try/except`, but ordering is fragile. The crash from C2 (None path) IS caught, so `remove_position()` at line 1037 does execute. No actual bug today. ✅

---

## Quality Rating

**HIGH** — All 8 claims verified with exact line-level evidence. The auditor's analysis is accurate, severity ratings are appropriate, and the fix priority ordering is sound.

> [!NOTE]
> The auditor's proposed fix for C3 (replace `sim_get_price` with `sim_get_quote_with_spread` returning dict) is correct and aligns with the implementation plan's approach.

---

## Summary

- **8/8 claims verified** — zero discrepancies
- **Severity assessments match** code evidence
- **No missed issues** detected during validation
- **Recommended fix priority** (C3+A2 first) is confirmed correct — these silently disable three safety mechanisms in sim mode
