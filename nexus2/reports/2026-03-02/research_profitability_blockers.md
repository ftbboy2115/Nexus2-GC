# Research: Profitability Blockers

**Agent:** Backend Planner
**Date:** 2026-03-02
**Handoff:** `handoff_planner_profitability_blockers.md`

---

## Issue 1: Re-entry Cooldown — GAP IN LIVE MODE

### Current Behavior — Code Evidence

A comprehensive re-entry cooldown system already exists with **three layers of protection**:

#### Layer 1: Wall-Clock Cooldown (LIVE mode)

**Finding:** Live mode uses a 120-second (2-minute) wall-clock cooldown.
**File:** `warrior_entry_guards.py:152-160`
**Code:**
```python
# RE-ENTRY COOLDOWN (LIVE mode)
if not engine.monitor.sim_mode and symbol in engine.monitor._recently_exited:
    exit_time = engine.monitor._recently_exited[symbol]
    seconds_ago = (now_utc() - exit_time).total_seconds()
    cooldown = engine.monitor._recovery_cooldown_seconds
    if seconds_ago < cooldown:
        reason = f"Re-entry cooldown - exited {seconds_ago:.0f}s ago (waiting {cooldown}s)"
        tml.log_warrior_guard_block(symbol, "live_cooldown", reason, _trigger, _price, _btime)
        return False, reason
```
**Verified with:** `view_file` on `warrior_entry_guards.py`, lines 152-160
**Default value:** `_recovery_cooldown_seconds = 120` (line 98 of `warrior_monitor.py`)

#### Layer 2: Sim-Time Cooldown (SIM mode)

**Finding:** Sim mode uses a 10-minute sim-time cooldown.
**File:** `warrior_entry_guards.py:162-172`
**Code:**
```python
# SIM MODE COOLDOWN
if engine.monitor.sim_mode and symbol in engine.monitor._recently_exited_sim_time:
    exit_sim_time = engine.monitor._recently_exited_sim_time[symbol]
    if hasattr(engine.monitor, '_sim_clock') and engine.monitor._sim_clock:
        current_sim_time = engine.monitor._sim_clock.current_time
        minutes_since_exit = (current_sim_time - exit_sim_time).total_seconds() / 60
        cooldown_minutes = engine.monitor._reentry_cooldown_minutes
        if minutes_since_exit < cooldown_minutes:
            reason = f"SIM re-entry cooldown - exited {minutes_since_exit:.1f}m ago (waiting {cooldown_minutes}m)"
```
**Verified with:** `view_file` on `warrior_entry_guards.py`, lines 162-172
**Default value:** `_reentry_cooldown_minutes = 10` (line 105 of `warrior_monitor.py`)

#### Layer 3: Consecutive Loss Gate

**Finding:** After N consecutive losses on a symbol, re-entry is blocked.
**File:** `warrior_entry_guards.py:174-182`
**Code:**
```python
# RE-ENTRY QUALITY GATE: Block re-entry after consecutive losses (Ross: 3-5 trades max per symbol)
if watched.entry_attempt_count > 0 and engine.monitor.settings.block_reentry_after_loss:
    max_attempts = engine.monitor.settings.max_reentry_after_loss  # Default: 3
    consecutive_losses = watched.consecutive_loss_count
    if consecutive_losses >= max_attempts:
        reason = f"Re-entry BLOCKED after {consecutive_losses} consecutive losses..."
```
**Verified with:** `view_file` on `warrior_entry_guards.py`, lines 174-182
**Defaults:** `block_reentry_after_loss=True`, `max_reentry_after_loss=3` (warrior_types.py:153-154)

#### Layer 4: Max Re-entry Count

**Finding:** Total re-entries per symbol are capped at 3 (4 total entries).
**File:** `warrior_engine.py:252-258`
**Code:**
```python
max_reentries = self.monitor.settings.max_reentry_count
if watched.entry_attempt_count >= max_reentries:
    logger.info(
        f"[Warrior Engine] {symbol}: Re-entry BLOCKED - "
        f"attempt #{watched.entry_attempt_count + 1} exceeds max {max_reentries}"
    )
    return
```
**Verified with:** `view_file` on `warrior_engine.py`, lines 252-258
**Default:** `max_reentry_count = 3` (warrior_types.py:152)

### Analysis of 2026-03-02 Live Trades

The handoff reports:
- **BATL**: Lost $1,742 on trade #1 (entry 09:16 UTC, exit 09:19 UTC). Re-entered at 10:19 UTC, lost $2,166 more.
  - **Gap = 60 minutes** — far exceeds the 120s (2-min) live cooldown → **cooldown expired, gap is NOT the issue**
  - The 120-second cooldown is designed to prevent **order fill race conditions**, NOT to prevent revenge trading.

- **CISS**: Lost $1,923 on trade #1 (entry 09:57, exit 10:08). Re-entered at 10:10.
  - **Gap = 2 minutes** — this may have been within the 120s window, depending on seconds.

### Root Cause

> [!CAUTION]
> The live cooldown (120 seconds) is NOT a re-entry protection mechanism — it's a **fill race condition guard**. It prevents the engine from trying to re-enter a symbol while a sell order is still filling.

The **real** re-entry protection mechanisms are:
1. **Consecutive loss gate** (`block_reentry_after_loss=True`, `max_reentry_after_loss=3`) — BUT this requires `watched.entry_attempt_count > 0`. For a brand-new entry triggered by a fresh scan, `entry_attempt_count` starts at 0, so the first re-entry is NEVER blocked by this gate.
2. **The `_handle_exit_pnl` callback** tracks P&L and increments `consecutive_loss_count` — but only if the `watched` symbol is still in the `_watchlist`. If the symbol was removed from the watchlist between exit and re-entry (possible if a new scan ran), the loss tracking is lost.

**The real gap:** In live mode, there is NO time-based re-entry cooldown for revenge trading protection. The 120s cooldown is too short (race-condition guard), and the sim-mode 10-minute cooldown **only applies in sim mode**. The consecutive loss gate exists but is bypassed on first re-entry.

### Is It a Bug?

**Yes** — the sim mode has a proper 10-minute cooldown (Layer 2), but live mode relies only on the 120s race-condition guard plus the consecutive loss gate.

### Proposed Fix

Add a **live-mode re-entry cooldown** similar to the sim-mode cooldown. This should:
1. Use wall-clock time (since live mode has no sim clock)
2. Default to 10 minutes (matching the sim default)
3. Be configurable via `WarriorMonitorSettings`
4. Apply REGARDLESS of whether the last exit was a loss or profit (prevent overtrading)

**Change Surface:**

| # | File | Change | Location |
|---|------|--------|----------|
| 1 | `warrior_monitor.py` | Add `_live_reentry_cooldown_minutes` attribute | `__init__`, ~line 105 |
| 2 | `warrior_types.py` | Add `live_reentry_cooldown_minutes: int = 10` | `WarriorMonitorSettings`, ~line 155 |
| 3 | `warrior_entry_guards.py` | Change `_recovery_cooldown_seconds` check to also enforce minimum 10-minute cooldown from `_recently_exited` timestamps | Lines 152-160 |

### Ross Methodology Alignment

From `.agent/strategies/warrior.md`, §4:

> **4.3 Re-Entry Limits:**
> - Typically 3-5 trades on same stock per session
> - After 2+ failed re-entries: "gave up on this one"
> - If stock goes below VWAP with MACD negative: "I guess it's done"

The bot's `max_reentry_count=3` and `max_reentry_after_loss=3` align with Ross. The missing piece is a **minimum time gap** between exits and re-entries. Ross doesn't re-enter immediately after a loss — he waits for "a fresh setup" (pullback, new catalyst). A 10-minute cooldown approximates this.

### Batch Test Impact

The sim-mode cooldown (10 minutes) is already active in batch tests. Adding a live-mode cooldown **would not change batch test results**, only live trading behavior. However, it could be validated by checking whether the BATL and CISS live trades would have been blocked.

---

## Issue 2: Stop Adherence — NO BUG FOUND

### Current Behavior — Code Evidence

**Finding:** The `evaluate_position` function checks exits in strict priority order. Stop hit is CHECK 1, candle-under-candle is CHECK 2.
**File:** `warrior_monitor_exit.py:1298-1321`
**Code:**
```python
# CHECK 0: After-Hours Exit
signal = await _check_after_hours_exit(monitor, position, current_price, r_multiple)
if signal:
    return signal

# CHECK 0.5: Spread Exit
signal = await _check_spread_exit(monitor, position, current_price, r_multiple)
if signal:
    return signal

# CHECK 0.7: Time Stop (no momentum)
signal = await _check_time_stop(monitor, position, current_price, r_multiple)
if signal:
    return signal

# CHECK 1: Stop Hit
signal = _check_stop_hit(position, current_price, r_multiple)
if signal:
    return signal

# CHECK 2: Candle-Under-Candle
signal = await _check_candle_under_candle(monitor, position, current_price, r_multiple)
if signal:
    return signal
```
**Verified with:** `view_file` on `warrior_monitor_exit.py`, lines 1298-1321

**Finding:** `_check_stop_hit` fires when `current_price <= position.current_stop` (line 408).
**File:** `warrior_monitor_exit.py:402-435`
**Code:**
```python
def _check_stop_hit(
    position: WarriorPosition,
    current_price: Decimal,
    r_multiple: float,
) -> Optional[WarriorExitSignal]:
    """Check if stop has been hit."""
    if current_price > position.current_stop:
        return None
    # ... exit signal generated
```

**Finding:** `_check_candle_under_candle` has a guard that SKIPS when position is profitable.
**File:** `warrior_monitor_exit.py:473-479`
**Code:**
```python
# GUARD 2: Skip when position is profitable (green) — let candle trail manage exit
if getattr(s, 'candle_exit_only_when_red', True) and current_price > position.entry_price:
    logger.debug(
        f"[Warrior] {position.symbol}: Candle-under-candle skipped "
        f"(position is green: ${current_price:.2f} > entry ${position.entry_price:.2f})"
    )
    return None
```

### Analysis

The handoff asked: "Does `candle_under_candle` respect the stop price?"

**Answer: The stop ALWAYS fires first.** Here's why:

1. The `evaluate_position` function checks `_check_stop_hit` (CHECK 1) BEFORE `_check_candle_under_candle` (CHECK 2).
2. If `current_price <= current_stop`, the stop fires and the function returns immediately. CUC never gets checked.
3. CUC can only fire when `current_price > current_stop` (stop not hit) AND `current_price < entry_price` (position is red, because `candle_exit_only_when_red=True`).
4. Therefore, CUC exits are always **between the stop and the entry price** — they exit at a BETTER price than the stop would.

**The handoff observation about BATL #1:**
> Stop was set at $9.71 (consolidation_low). Trade exited via candle_under_candle at $10.00.

This is **correct behavior**: CUC exited at $10.00 while the stop was at $9.71. The CUC exit was $0.29 above the stop — a BETTER exit. CUC acts as a "tighter than stop" early exit for dying trades, which is exactly Ross Cameron's "break out or bail out" philosophy.

### Is It a Bug?

**No.** The exit priority ordering correctly ensures:
- Stop ALWAYS fires first if price breaches it
- CUC fires as an **early warning** exit when the trade is red but hasn't hit the stop yet
- CUC can NEVER exit below the stop — the stop would fire first

### Ross Methodology Alignment

From `.agent/strategies/warrior.md`, §9.2:
> **9.2 Stop Behavior**
> - **No fixed stop-loss percentage** — uses technical levels
> - **Mental stop** at entry candle low or support level
> - **Hard stop** = account loss limit for the day

The current implementation correctly:
1. Uses candle low as technical stop (primary)
2. Falls back to mental stop (15¢ for base_hit, 50¢ for home_run) when no candle data
3. Never allows exits below the stop price

---

## Issue 3: Entry Quality Analysis — INFRASTRUCTURE EXISTS

### How to Compare Bot vs Ross

**Finding:** `gc_quick_test.py` supports `--trades` flag for per-trade output.
**File:** `scripts/gc_quick_test.py:293`
**Code:**
```python
parser.add_argument("--trades", action="store_true", help="Include per-trade details")
```
**Verified with:** `view_file` on `gc_quick_test.py`, line 293

**Usage:** `python scripts/gc_quick_test.py --all --trades --json` will output per-trade details including `entry_time`, `exit_time`, and `direction` for each case.

### Available Data Points per Case

From the batch test output format (line 124-145 and 357-374):
- `case_id`, `symbol`, `date`
- `bot_pnl` (total P&L)
- `ross_pnl` (Ross's actual P&L)
- `delta` (bot - ross)
- `entry_time`, `exit_time`
- `direction`
- `guard_blocks` (entries that were blocked by guards)

### Recommended Approach for Entry Quality Analysis

The handoff requests analysis of the top 5 worst-delta cases. This is a **runtime investigation**, not a code change.

**Step 1:** Run batch test with per-trade details:
```powershell
python scripts/gc_quick_test.py MLEC ROLR HIND MNTS --trades --json > /tmp/worst_cases.json
```

**Step 2:** For each case, compare:
- Bot entry time vs Ross's known entry time (from test case metadata in `gravity-claw/data/cases/`)
- Bot entry price vs Ross's entry price
- Bot exit reason vs what Ross did

**Step 3:** Categorize losses:
- **Ross also lost** → Setup didn't work (not our fault)
- **Ross profited, we lost** → Our entry/exit timing was wrong
- **Ross didn't trade** → We entered something he wouldn't have

### Test Case Metadata Location

**Finding:** Test cases are stored with Ross's actual trade data.
**Search:** `find_by_name` for test case directories confirms cases are in `gravity-claw/data/cases/`

Each case includes Ross's entry/exit times, prices, and P&L — enabling direct comparison with bot behavior.

### Deliverable Gap

This investigation requires **running batch tests and analyzing output** — which is outside the Backend Planner's scope (read-only research). The recommended next step is:

1. **Backend Specialist** runs `gc_quick_test.py` with `--trades --json` on the worst cases
2. Compare bot trade details against Ross's trade metadata from the test case files
3. Document findings per the handoff template (bot entry time/price vs Ross, exit reason, objective quality assessment)

---

## Summary of Findings

| Issue | Is Bug? | Severity | Proposed Action |
|-------|---------|----------|-----------------|
| #1: Re-entry cooldown | **YES** — live mode lacks meaningful cooldown | HIGH | Add 10-minute live re-entry cooldown (3 lines, 3 files) |
| #2: Stop adherence | **NO** — working correctly | N/A | No action needed |
| #3: Entry quality | **Investigation needed** | MEDIUM | Run `--trades` batch test on worst cases, compare with Ross metadata |

### Wiring Checklist (Issue 1 — Re-entry Cooldown Fix)

- [ ] Add `live_reentry_cooldown_minutes: int = 10` to `WarriorMonitorSettings` in `warrior_types.py`
- [ ] Replace `_recovery_cooldown_seconds` check in `warrior_entry_guards.py` with a check against `live_reentry_cooldown_minutes`
- [ ] Add `live_reentry_cooldown_minutes` to `warrior_monitor_settings.py` load/save functions
- [ ] Expose via `/warrior/monitor/settings` API endpoint for tunability
- [ ] Test: verify live mode re-entry is blocked for 10 minutes after exit

### Risk Assessment

**Issue 1 fix risks:**
- LOW risk — only affects live mode re-entry timing, not batch tests
- Could potentially block legitimate re-entries on strong stocks
- Mitigated by making the cooldown configurable (API-tunable)
- Ross's methodology supports re-entry after "fresh setup" — 10 minutes is a reasonable approximation

**Issue 3 investigation risks:**
- No code changes involved — purely analytical
- May reveal that the bot's entry logic needs fundamental improvement (scanner timing, PMH detection)
