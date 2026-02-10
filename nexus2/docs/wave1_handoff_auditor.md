# Wave 1 Code Auditor Handoff: Verify Phases 1-2

> **Run AFTER:** Backend specialist completes Phases 1-2
> **Architecture Doc:** [concurrent_batch_runner_architecture.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/docs/concurrent_batch_runner_architecture.md)
> **Mode:** READ-ONLY verification. Do NOT modify any code.

---

## Why This Audit Exists

Backend agents have previously claimed work was done that wasn't. Phases 3-5 build directly on Phases 1-2. If the ContextVar isn't wired correctly, the entire concurrent runner will fail silently (all tasks sharing one clock → wrong P&L for every test case). This audit catches that before we build on a broken foundation.

---

## Claims to Verify (8 total)

### C1: SimulationClock ContextVar exists
- **File:** `nexus2/adapters/simulation/sim_clock.py`
- **Grep:** `_sim_clock_ctx` — should find `ContextVar` definition
- **Check:** `get_simulation_clock()` checks `_sim_clock_ctx.get()` BEFORE the global singleton
- **Check:** `set_simulation_clock_ctx()` function exists

### C2: `set_simulation_clock_ctx` is exported
- **File:** `nexus2/adapters/simulation/__init__.py`
- **Grep:** `set_simulation_clock_ctx` — should appear in both `from ... import` and `__all__`

### C3: MockBroker accepts `clock` param
- **File:** `nexus2/adapters/simulation/mock_broker.py`
- **Check:** `__init__` signature includes `clock` parameter
- **Check:** `self._clock = clock` is stored

### C4: MockBroker `sell_position()` uses injected clock
- **File:** `nexus2/adapters/simulation/mock_broker.py`
- **Check:** `sell_position()` checks `self._clock` before falling back to `get_simulation_clock()`
- **Red flag:** If `sell_position()` ONLY uses `get_simulation_clock()` without checking `self._clock`, the fix was not applied

### C5: `is_sim_mode()` function exists in trade_event_service
- **File:** `nexus2/domain/automation/trade_event_service.py`
- **Grep:** `def is_sim_mode` — should find function definition
- **Grep:** `_is_sim_mode` ContextVar definition
- **Grep:** `def set_sim_mode_ctx` — should find setter function

### C6: All 5 `get_warrior_sim_broker()` sites replaced
- **File:** `nexus2/domain/automation/trade_event_service.py`
- **Grep:** `get_warrior_sim_broker() is not None` — should return **0 results** (all replaced)
- **Grep:** `is_sim_mode()` — should return **5 results** (replacements)
- **Critical:** If `get_warrior_sim_broker() is not None` still appears, the migration is incomplete

### C7: `sim_only` guard in WarriorEngine (if needed)
- **File:** `nexus2/domain/automation/warrior_engine.py`
- **Check:** Does `apply_settings_to_config()` overwrite `sim_only`?
- **File:** `nexus2/db/warrior_settings.py` — view `apply_settings_to_config()` to see if it touches `sim_only` field
- **If yes:** A guard must exist in `warrior_engine.py` after L84 to preserve `sim_only=True`

### C8: No unintended changes
- **Run:** `git diff --stat` — only the files listed in the handoff should be modified:
  - `adapters/simulation/sim_clock.py`
  - `adapters/simulation/__init__.py`
  - `adapters/simulation/mock_broker.py`
  - `domain/automation/trade_event_service.py`
  - Possibly `domain/automation/warrior_engine.py`
- **Red flag:** Any changes to `warrior_monitor.py`, `warrior_sim_routes.py`, or `warrior_engine_entry.py` are OUT OF SCOPE

---

## Output Format

Write report to: `nexus2/wave1_audit_report.md`

```markdown
# Wave 1 Audit Report: Phases 1-2

| # | Claim | Result | Evidence |
|---|-------|:------:|----------|
| C1 | ContextVar in sim_clock.py | PASS/FAIL | [details] |
| C2 | Export in __init__.py | PASS/FAIL | [details] |
| C3 | MockBroker clock param | PASS/FAIL | [details] |
| C4 | sell_position uses injected clock | PASS/FAIL | [details] |
| C5 | is_sim_mode() exists | PASS/FAIL | [details] |
| C6 | All 5 sites replaced | PASS/FAIL | [details] |
| C7 | sim_only guard | PASS/FAIL/N/A | [details] |
| C8 | No unintended changes | PASS/FAIL | [git diff output] |

## Verdict
- ALL PASS: Ready for testing specialist
- ANY FAIL: Return to backend specialist with specific failures
```
