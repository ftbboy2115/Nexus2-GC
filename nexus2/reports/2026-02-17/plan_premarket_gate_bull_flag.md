# Add 6 AM Premarket Gate — Upstream in Entry Dispatcher

**Problem:** FRGT `bull_flag` entry fired at 5:30 AM ET. The premarket gate exists only in `detect_dip_for_level` (L319), but no other patterns have it. Duplicating it per-pattern is code smell.

**Solution:** Add a single time gate at the **top of `check_entry_triggers()`** — the upstream dispatcher that loops through all watched candidates. This blocks ALL entries before 6 AM ET with one check.

---

## Proposed Changes

### [MODIFY] [warrior_engine_entry.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py)

**Add premarket gate inside the `for symbol, watched` loop, before any pattern evaluation (after line 356):**

```python
# TIME GATE: Block ALL entries before 6 AM ET (live only)
# Ross Cameron's active window starts at 6 AM (per warrior.md)
# Skipped in sim mode — historical replays use bar timestamps, not wall clock
is_sim = getattr(engine.config, 'sim_only', False)
if not is_sim:
    et_now = engine._get_eastern_time()
    if et_now.hour < 6:
        continue  # Skip this candidate entirely
```

---

### [MODIFY] [warrior_entry_patterns.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py)

**Remove the per-pattern time gate from `detect_dip_for_level` (lines 304-324)** — it's now redundant since the upstream gate blocks everything.

---

## Verification Plan

### Automated Tests

1. **Existing test suite (regression check):**
```powershell
cd "c:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus"
python -m pytest nexus2/tests/unit/automation/ -v --tb=short
python -m pytest nexus2/tests/integration/test_warrior_integration.py -v --tb=short
```

2. **Batch simulation (verify no regression — patterns still fire after 6 AM):**
```powershell
python nexus2/scripts/run_batch.py
```
Compare results to previous batch run — P&L should not change.

### Manual Verification

After next trading session, check VPS logs:
```bash
grep "BULL FLAG" ~/Nexus2/data/server.log | head -5
```
Verify no entries appear before 06:00 ET timestamp.
