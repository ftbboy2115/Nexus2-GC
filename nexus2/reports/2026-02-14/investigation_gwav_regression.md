# Investigation: GWAV P&L Regression

**Date:** 2026-02-14  
**Agent:** Backend Planner  
**Reference:** [handoff_gwav_regression.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-02-14/handoff_gwav_regression.md)

---

## Root Cause: `entry_triggered=True` Restored on Guard Rejection

**File:** [warrior_engine_entry.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py#L997-L1000)  
**Commit range:** `3abf885..5def3a5`

### The Change

```diff
# warrior_engine_entry.py, enter_position(), line 997-999
  else:
      logger.info(f"[Warrior Entry] {symbol}: {block_reason}")
-     # NOTE: Do NOT set entry_triggered=True here. Guard rejections are often
-     # temporary (MACD negative, below VWAP, cooldown). Setting entry_triggered=True
-     # permanently blocks ALL patterns for the rest of the session, preventing
-     # later patterns (like HOD_BREAK) from ever firing even when conditions improve.
+     watched.entry_triggered = True
      return
```

**Impact:** When any entry guard (MACD, VWAP, EMA, spread, cooldown) rejects an entry attempt, `entry_triggered` is set to `True`, permanently blocking ALL subsequent pattern detection for that symbol.

---

## How This Affects GWAV

### GWAV Test Case Facts

| Property | Value | Source |
|----------|-------|--------|
| Setup type | `pmh` | [warrior_setups.yaml:526](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/tests/test_cases/warrior_setups.yaml#L526) |
| PMH | $3.00 | [warrior_setups.yaml:538](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/tests/test_cases/warrior_setups.yaml#L538) |
| Entry pattern | `whole_half_anticipatory` | Both runs (verified in handoff) |
| Entry price | $5.47 | Both runs |
| Exit mode | `home_run` | Both runs |
| Max shares held | 505 | Baseline VPS run |
| Baseline P&L | +$630.63 | VPS sequential (Feb 14 baseline) |
| Current P&L | +$215.91 | Current VPS run |
| Ross P&L | +$3,974.68 | [warrior_setups.yaml:535](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/tests/test_cases/warrior_setups.yaml#L535) |

### The Execution Chain

1. **Pattern detection:** GWAV's price sits below PMH ($3.00), price is near $5.47 — well above PMH. Wait — price $5.47 is above PMH $3.00, so GWAV enters the **above-PMH** branch at [line 544](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py#L544).

   Actually, re-reading the handoff: the entry is `whole_half_anticipatory` which fires in the **below-PMH** branch at [line 530-532](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py#L530-L532). This means at the initial entry time, GWAV's price WAS below PMH — and the PMH value in the test data ($3.00) is clearly an estimate. The actual effective PMH used during simulation must be higher than $5.47.

2. **`whole_half_anticipatory` config guard** at [warrior_entry_patterns.py:158](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py#L158):
   ```python
   if not (engine.config.whole_half_anticipatory_enabled and not watched.entry_triggered):
       return None
   ```
   **This is the blocking check.** Once `entry_triggered=True`, this pattern can never fire again.

3. **Critical scenario:**
   - Tick N: `whole_half_anticipatory` detects a valid pattern → calls `enter_position()`
   - `enter_position()` → `check_entry_guards()` → **MACD GATE rejects** (MACD negative at this bar)
   - **Baseline:** `entry_triggered` stays `False` → next tick, pattern can retry
   - **Current:** `entry_triggered = True` → pattern permanently blocked
   - Tick N+K: MACD turns positive, pattern would fire at a different price/time, but `entry_triggered=True` blocks it

### Why P&L Drops (Not Goes to Zero)

The P&L doesn't drop to zero — GWAV still trades. This means:
- **First entry succeeds** at some point (MACD is positive on the first valid tick)
- **Re-entry after profit exit is blocked** — the `_handle_profit_exit` callback resets `entry_triggered=False` at [warrior_engine.py:225](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine.py#L225), BUT the second entry attempt may hit a guard rejection, setting `entry_triggered=True` again permanently

**OR more likely:** The entry does happen (same trigger at $5.47), but the guard rejection on an EARLIER tick at a DIFFERENT price caused `entry_triggered=True`, delaying the actual entry. The later entry happens via the PMH crossover reset at [line 548-550](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py#L548-L550):
```python
if watched.entry_triggered and watched.last_below_pmh:
    watched.last_below_pmh = False
    watched.entry_triggered = False  # Reset to allow new entry attempt
```

This means the entry was DELAYED — entering later at the same $5.47 price but on a LATER bar, meaning:
- Less time in the trade before exit
- Different exit bar timing for `home_run` mode  
- Lower final P&L ($215.91 vs $630.63)

---

## Secondary Change: HOD_BREAK `entry_triggered` Exemption

**File:** [warrior_entry_patterns.py:1288-1293](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py#L1288-L1293)

```diff
-    if not (engine.config.hod_break_enabled and not watched.entry_triggered):
+    if not engine.config.hod_break_enabled:
```

**Impact on GWAV:** None. GWAV doesn't use HOD_BREAK (it uses `whole_half_anticipatory`). But this exemption was the REASON the `entry_triggered=True` was restored — to unblock HOD_BREAK from being permanently killed by earlier guard rejections.

> [!IMPORTANT]
> The intent was correct: HOD_BREAK should not be blocked by earlier guard rejections. But the fix restored `entry_triggered=True` globally, which broke OTHER patterns that depend on retrying after temporary guard rejections.

---

## Verified Facts

**Finding 1:** `entry_triggered=True` on guard rejection permanently blocks `whole_half_anticipatory`  
**File:** [warrior_entry_patterns.py:158](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py#L158)  
**Code:** `if not (engine.config.whole_half_anticipatory_enabled and not watched.entry_triggered):`  
**Verified with:** `view_file` line 158

**Finding 2:** Same blocking pattern affects ALL non-HOD_BREAK patterns  
**File:** [warrior_entry_patterns.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py)  
**Code:** Lines 68, 158, 297, 520, 889, 991, 1105, 1187 — all check `not watched.entry_triggered`  
**Verified with:** `grep_search "entry_triggered"` in automation directory

**Finding 3:** `validate_technicals` intentionally does NOT set `entry_triggered=True` for VWAP/EMA rejections  
**File:** [warrior_entry_guards.py:413-414](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py#L413-L414)  
**Code:** `# NOTE: Do NOT set entry_triggered=True here - VWAP is a temporary condition`  
**Verified with:** `view_file` lines 413-414, 424-425

**Finding 4:** Only 2 files changed between baseline and current  
**Verified with:** `git diff 3abf885..5def3a5 --stat` → 2 files, 19 insertions, 36 deletions

---

## Impact Assessment

### This commit affects ALL test cases, not just GWAV

Any test case where:
1. A pattern fires → calls `enter_position()`
2. Entry guard **temporarily** rejects (MACD negative, below VWAP, cooldown, etc.)
3. `entry_triggered = True` permanently blocks ALL patterns for that symbol

This explains why the handoff mentions GWAV specifically, but the effect is systematic.

### Guard rejections that cause permanent blocking

| Guard | Nature | Should Block Permanently? |
|-------|--------|--------------------------|
| MACD gate | **Temporary** — MACD oscillates | ❌ No |
| VWAP rejection | **Temporary** — price moves | ❌ No (already exempted in `validate_technicals`) |
| 9 EMA rejection | **Temporary** — price moves | ❌ No (already exempted) |
| Spread filter | **Temporary** — spread tightens | ❌ No |
| Cooldown | **Temporary** — timer expires | ❌ No |
| Blacklist | **Permanent** — won't change | ✅ Yes |
| Max fails | **Permanent** — won't reset intraday | ✅ Yes |
| Already holding | **Permanent** (until exit) | ✅ Yes (already handled separately) |

---

## Recommended Fix

> [!CAUTION]
> The original comment that was removed was **correct**: guard rejections are often temporary, and setting `entry_triggered=True` permanently blocks trades.

### Option A: Revert the `entry_triggered=True` restoration (simplest)

Remove `watched.entry_triggered = True` at line 999 (revert to baseline behavior). HOD_BREAK already has its own exemption via the config-only guard, so it doesn't need this.

```python
# warrior_engine_entry.py:997-1000
else:
    logger.info(f"[Warrior Entry] {symbol}: {block_reason}")
    # Do NOT set entry_triggered=True — guard rejections are temporary
    return
```

**Risk:** With `entry_triggered` staying False after guard rejection, patterns may fire repeatedly, causing log spam. But this is the BASELINE behavior that produced $630.63.

### Option B: Selective blocking by guard type (more nuanced)

Only set `entry_triggered=True` for permanent rejections (blacklist, max fails). Keep it False for temporary rejections (MACD, VWAP, spread, cooldown).

```python
# warrior_engine_entry.py:997-1000
else:
    logger.info(f"[Warrior Entry] {symbol}: {block_reason}")
    # Only permanently block for non-recoverable rejections
    permanent_blocks = {"Blacklisted", "Max fails hit"}
    if any(pb in block_reason for pb in permanent_blocks):
        watched.entry_triggered = True
    return
```

**Risk:** Requires careful enumeration of permanent vs temporary guard reasons. More fragile.

### Option C: Per-guard `entry_triggered` management (cleanest, most work)

Move `entry_triggered` management INTO each guard function, letting each guard decide whether its rejection is permanent or temporary. This is already partially done for VWAP/EMA in `validate_technicals`.

**Risk:** More code changes, higher implementation effort.

### Recommendation: **Option A** (revert)

The baseline behavior was correct. The HOD_BREAK exemption already handles its specific need. Reverting the one line at 999 restores GWAV's P&L and matches the philosophy expressed in `validate_technicals` comments.

---

## Verification Plan

After applying the fix:

1. **Run GWAV individually on VPS:**
   ```powershell
   # On VPS via SSH:
   curl -s -X POST http://localhost:8000/warrior/sim/run -H "Content-Type: application/json" -d '{"case_id":"ross_gwav_20260116"}' | python3 -m json.tool
   ```
   Expected: P&L ≈ +$630.63

2. **Run full batch on VPS:**
   Verify no regressions across all 29 cases. Total P&L should be ≈$3,945.

3. **Verify HOD_BREAK still works independently:**
   HOD_BREAK has its own `entry_triggered` exemption at [warrior_entry_patterns.py:1293](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py#L1293). Confirm MLEC test case behavior is unchanged.
