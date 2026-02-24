# Audit Validator Handoff: Premarket Entry Fix

## Instructions

Read `@.agent/rules/agent-audit-validator.md` for your role and constraints.

Verify the claims in [backend_status_premarket_fix.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-02-23/backend_status_premarket_fix.md).

Write your validation report to: `nexus2/reports/2026-02-23/validation_premarket_fix.md`

---

## Claims to Verify

All changes are in: `nexus2/domain/automation/warrior_entry_patterns.py`

### Claim 1: PMH Break — Relaxed `check_active_market` Thresholds Before 9:30 AM

**What to verify:**
- An `is_premarket` flag is computed from sim clock (or wall clock) checking `hour < 9 or (hour == 9 and minute < 30)`
- When `is_premarket=True`, `check_active_market()` is called with `min_bars=3, min_volume_per_bar=500, max_time_gap_minutes=30`
- When `is_premarket=False`, the ORIGINAL thresholds are still used (1min: `min_bars=5, min_volume_per_bar=1000, max_time_gap_minutes=15`; 10s: `min_bars=18, min_volume_per_bar=200, max_time_gap_minutes=5`)
- **Start looking near line 586**

### Claim 2: PMH Break — Skip Candle-Over-Candle in Premarket

**What to verify:**
- Before 9:30 AM, `detect_pmh_break()` returns `EntryTriggerType.PMH_BREAK` immediately when price > PMH, WITHOUT waiting for a second candle
- After 9:30 AM, the original candle-over-candle logic (control candle → wait → second candle breaks) is UNCHANGED
- **Start looking near line 652**

### Claim 3: DFL — Same Relaxed Thresholds

**What to verify:**
- `detect_dip_for_level()` also has a `dfl_is_premarket` flag with the same `hour < 9 or (hour == 9 and minute < 30)` check
- When premarket, `check_active_market()` uses the SAME relaxed params: `min_bars=3, min_volume_per_bar=500, max_time_gap_minutes=30`
- When NOT premarket, original thresholds unchanged
- **Start looking near line 392**

### Claim 4: Investigation Step 0 — 10s Timeframe Default Would NOT Work

**What to verify:**
- Check `HistoricalBarLoader.get_bars_up_to()` — does it handle `"10s"` timeframe? Or does it fall through to 1-min bars?
- The claim is that changing `entry_bar_timeframe` default to `"10s"` would NOT work because the history loader doesn't support it
- **File:** Look in `nexus2/adapters/simulation/` for `HistoricalBarLoader` or similar

### Claim 5: No Regression — Market Hours Logic Unchanged

**What to verify:**
- Confirm that ALL premarket-relaxed paths are gated behind `is_premarket`/`dfl_is_premarket` checks
- When `is_premarket=False`, code flows through the EXACT original paths (no changes)
- No new parameters or thresholds affect market-hours behavior

### Claim 6: Batch Test — 35 Cases Run Without Errors

**What to verify:**
- Run `pytest nexus2/tests/` to confirm test suite passes
- (Batch test results already captured in status report — no need to re-run)

---

## Output Format

Use the standard validation report format from the Audit Validator rules:

```markdown
## Validation Report: Premarket Entry Fix

### Claims Verified
| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | ... | PASS/FAIL | [command + output] |

### Overall Rating
- HIGH / MEDIUM / LOW

### Failures (if any)
```
