# Spec: Reentry Loss Guard Tuning

**Date:** 2026-02-23
**Status:** Pending Clay Approval
**Priority:** P1 — $44K impact on BATL alone

---

## Problem Statement

The `reentry_loss` guard permanently blocks re-entry on a symbol after **any** losing exit. This directly contradicts Ross Cameron's documented methodology:

> **Ross Strategy (Section 4.1-4.3):** Re-enters the same stock 3–5 times per session. After a failed first attempt, he re-enters with smaller size. He only "gives up" after 2+ consecutive failures.

### Evidence: A/B Batch Test Results (2026-02-23)

| Metric | Guards ON | Guards OFF | Delta |
|--------|-----------|------------|-------|
| Bot P&L | $136,993 | $151,170 | **+$14,176** |
| Capture | 31.6% | 34.9% | +3.3% |

Guard was the single largest cost contributor at **3,296 blocks** (35% of all blocks).

**BATL impact alone:** -$44,665 across 2 test cases (3,241 blocks each day).

### Guard Accuracy (from counterfactual analysis)

| Guard | Blocks | Accuracy | Net Impact |
|-------|--------|----------|------------|
| reentry_loss | 3,296 | 65.8% | -$712 net savings |
| macd | 4,945 | 65.0% | -$549 net savings |
| position | 1,166 | 62.2% | -$34 net savings |

The `reentry_loss` guard is 66% accurate — meaning 34% of the time it blocks a profitable re-entry.

---

## Root Cause

**Current behavior** (`warrior_entry_guards.py:151-166`):
```python
if watched.entry_attempt_count > 0 and engine.monitor.settings.block_reentry_after_loss:
    last_pnl = watched.last_trade_pnl
    if last_pnl is not None and last_pnl < 0:
        return False, "Re-entry BLOCKED after loss - no revenge trading"
```

This is a **binary, permanent block**:
- One loss → blocked forever for the rest of the session
- No time decay, no cooldown, no max-attempts limit
- Does not consider whether the loss was $5 or $5,000
- Does not consider whether a new setup has formed

---

## Proposed Fix: Graduated Re-Entry Policy

Replace the binary block with a policy matching Ross's actual behavior.

### Option A: Max Attempts Per Symbol (Recommended)

Add `max_reentry_attempts` setting (default: 3). Allow re-entry up to N times on the same symbol, blocking only after N consecutive losing attempts.

```python
# warrior_entry_guards.py — MODIFIED reentry_loss guard
if watched.entry_attempt_count > 0 and engine.monitor.settings.block_reentry_after_loss:
    max_attempts = engine.monitor.settings.max_reentry_attempts  # default: 3
    consecutive_losses = watched.consecutive_loss_count  # NEW field

    if consecutive_losses >= max_attempts:
        reason = f"Re-entry BLOCKED after {consecutive_losses} consecutive losses (max={max_attempts})"
        tml.log_warrior_guard_block(symbol, "reentry_loss", reason, _trigger, _price, _btime)
        return False, reason
```

**Changes required:**

| File | Change |
|------|--------|
| `warrior_types.py` | Add `max_reentry_attempts: int = 3` to `WarriorMonitorSettings` |
| `warrior_engine_types.py` | Add `consecutive_loss_count: int = 0` to `WatchedCandidate` |
| `warrior_engine.py` | In `_handle_exit_pnl`: increment `consecutive_loss_count` on loss, **reset to 0 on win** |
| `warrior_entry_guards.py` | Replace binary block with max-attempts check |
| `warrior_monitor_settings.py` | Serialize/deserialize `max_reentry_attempts` |

### Option B: Cooldown After Loss (Alternative)

Instead of permanent block, add a cooldown (e.g., 5 minutes) after a loss before allowing re-entry. Similar to the existing `sim_cooldown` guard but triggered by loss.

```python
if last_pnl < 0:
    minutes_since_exit = ...
    cooldown = engine.monitor.settings.reentry_loss_cooldown_minutes  # default: 5
    if minutes_since_exit < cooldown:
        return False, f"Re-entry cooldown after loss ({minutes_since_exit:.1f}m < {cooldown}m)"
```

### Option C: Combine Both (Belt + Suspenders)

Use max attempts AND cooldown: allow up to 3 re-entries, but enforce a 5-minute cooldown between each. Most closely matches Ross's pattern of "getting cautious after failures but still trying."

---

## Recommendation

**Option A (Max Attempts)** is simplest and most directly aligned with Ross:

- Ross: "Typically 3-5 trades on same stock per session"
- Ross: "After 2+ failed re-entries: gave up on this one"
- Default `max_reentry_attempts = 3` captures this behavior

Option C is ideal but adds complexity. Save for Phase 2 if Option A proves insufficient.

---

## Verification Plan

1. Run batch with `max_reentry_attempts = 3` (new default)
2. Compare against:
   - Baseline (guards ON, current behavior): $136,993
   - Guards OFF: $151,170
3. Expected: P&L between $140K–$150K (guards still protecting but allowing productive re-entries)
4. Specifically check BATL cases — should see significant improvement

### A/B Sensitivity Test

Run with `max_reentry_attempts` = 1, 2, 3, 5 to find optimal value.

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Too many re-entries on losers | `max_reentry_attempts` caps exposure |
| Revenge trading | Ross's pattern ISN'T revenge — it's structured re-entry on new setups |
| Regression on currently profitable cases | Cases where guards help (VERO, ROLR) are blocked by `macd` and `position` guards, not `reentry_loss` |

> [!IMPORTANT]
> The `reentry_loss` guard label "no revenge trading" was an **interpretation**, not a documented Ross rule. Ross re-enters the same stock 3-5 times per session. The guard was well-intentioned but overly conservative.
