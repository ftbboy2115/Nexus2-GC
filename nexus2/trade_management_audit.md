# Trade Management Audit Report

**Audit Depth**: Level 2 — Cross-file trace analysis  
**Files Audited**: 5 files, ~2,877 lines total  
**Date**: 2026-02-11

---

## 1. File Inventory

| File | Lines | Key Functions | Role |
|------|------:|---------------|------|
| [warrior_monitor_exit.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py) | 1046 | 10 functions | All exit checks + execution |
| [warrior_monitor_scale.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_scale.py) | 285 | 2 functions | Scale-in detection + execution |
| [warrior_monitor.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor.py) | 721 | 21 methods | Orchestrator, position management |
| [warrior_types.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_types.py) | ~170 | 4 dataclasses | Settings, Position, ExitSignal, ExitReason |
| [warrior_engine.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine.py) | ~800 | (re-entry path) | `_on_profit_exit` callback consumer |

---

## 2. Exit Paths Inventory

### Evaluation Order (in `evaluate_position`, L768-868)

Every 2 seconds, `_check_all_positions` iterates monitored positions and calls `evaluate_position`. The **first** check that returns a signal wins — later checks are never reached.

| Priority | Check | Function | Full/Partial | Condition |
|:--------:|-------|----------|:------------:|-----------|
| 0 | After-hours exit | `_check_after_hours_exit` | Full | Time ≥ `force_exit_time_et` (default **19:30 ET**) |
| 0 | After-hours tighten | (same function) | Stop move | Time ≥ `tighten_stop_time_et` (default **18:00 ET**), price > entry, stop < entry |
| 0.5 | Spread exit | `_check_spread_exit` | Full | Spread % > `max_spread_percent` (default **3.0%**), after 60s grace |
| 1 | Stop hit | `_check_stop_hit` | Full | Price ≤ `current_stop` (mental or technical) |
| 2 | Candle-under-candle | `_check_candle_under_candle` | Full | New low + red candle + (high volume OR 5m red), after 60s grace |
| 3 | Topping tail | `_check_topping_tail` | Full | Wick ≥ 60% of range + near high (0.5% of MFE), after 120s grace |
| 4a | Base hit target | `_check_base_hit_target` | **Full** | Price ≥ entry + `base_hit_profit_cents` (default **+18¢**) |
| 4b | Home run partial | `_check_home_run_exit` | **50% partial** | R ≥ `home_run_partial_at_r` (default **2.0R**), partial not yet taken |
| 4b | Home run trail | `_check_home_run_exit` | Full (remainder) | R ≥ 1.5R: trail at 20% below MFE. Exit when price ≤ trail stop |
| — | R-based profit (generic) | `_check_profit_target` | 50% partial | Price ≥ `profit_target` (2:1 R by default) — **DEAD PATH** (see Red Flag #1) |

> [!IMPORTANT]
> The generic `_check_profit_target` (L562-614) is **never called** from `evaluate_position`. It exists in the file but is unreachable. Both base_hit and home_run modes have their own profit target logic.

---

## 3. Stop Logic Details

### A. Stop Calculation at Entry ([_create_new_position](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor.py#L370-L455))

| Stop Type | Formula | Default |
|-----------|---------|---------|
| Mental stop (fallback) | `entry_price - mental_stop_cents / 100` | **-50¢** (set high to rarely trigger) |
| Technical stop | `support_level - technical_stop_buffer_cents / 100` | support - **5¢** |
| **Active stop** | Technical if available, else mental | Candle low is primary per Ross |

**Risk per share** = `entry_price - current_stop`  
**Profit target** = `entry_price + profit_target_cents/100` if fixed, else `entry_price + (risk_per_share × profit_target_r)`

### B. Stop Trailing Behavior

| Condition | Stop Movement | Code Location |
|-----------|--------------|---------------|
| Home run, R ≥ 1.5 | Trail at `high_since_entry × (1 - 0.20)` | [L689-700](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py#L689-L700) |
| Home run, partial taken | Stop → breakeven (`entry_price`) | [L736-744](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py#L736-L744) |
| After-hours, time ≥ 18:00 | Stop → breakeven (if profitable) | [L231-238](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py#L231-L238) |
| Scale-in (if enabled) | Stop → breakeven | [L252-271](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_scale.py#L252-L271) |
| Base hit mode | **Stop never trails** | — |

> [!WARNING]
> **In base_hit mode, the stop NEVER moves.** There is no trailing, no tightening, no B/E move. A trade that runs +17¢ and reverses to -50¢ stop will be a full loss. This is the biggest structural gap for profitability.

### C. Hardcoded Thresholds Summary

| Parameter | Default Value | Setting Key |
|-----------|:------------:|-------------|
| Mental stop | 50¢ | `mental_stop_cents` |
| Technical stop buffer | 5¢ | `technical_stop_buffer_cents` |
| Base hit target | +18¢ | `base_hit_profit_cents` |
| Base hit stop | 15¢ | `base_hit_stop_cents` (⚠️ **unused!** — see Red Flag #2) |
| Home run partial | 2.0R | `home_run_partial_at_r` |
| Home run trail start | 1.5R | `home_run_trail_after_r` |
| Home run trail percent | 20% | `home_run_trail_percent` |
| Topping tail wick threshold | 60% | `topping_tail_threshold` |
| Candle-under-candle grace | 60s | `candle_exit_grace_seconds` |
| Topping tail grace | 120s | `topping_tail_grace_seconds` |
| Candle volume multiplier | 1.5× | `candle_exit_volume_multiplier` |
| Partial exit fraction | 50% | `partial_exit_fraction` |
| Spread exit max | 3.0% | `max_spread_percent` |
| Force exit time | 19:30 ET | `force_exit_time_et` |
| Tighten stop time | 18:00 ET | `tighten_stop_time_et` |
| Re-entry cooldown | 10 min (sim) | `_reentry_cooldown_minutes` |
| Scale max count | 2 | `max_scale_count` |
| Scale size | 50% of original | `scale_size_pct` |

---

## 4. Audit Answers (A–G)

### A. Exit Mode Selection

**How is base_hit vs home_run chosen?**
1. **Session default**: `session_exit_mode` setting — defaults to `"base_hit"` ([warrior_types.py L115](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_types.py#L115))
2. **Per-position override**: `exit_mode_override` passed at entry from quality score auto-selection
3. Resolution in [get_effective_exit_mode](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py#L39-L54): position override wins, session is fallback

**Can the mode switch mid-trade?** No. Once set, `exit_mode_override` is never modified during the life of the position. Session mode can be changed by the user, but existing positions already locked in their mode.

**What % of test cases use each mode?** Unknown from code alone — depends on what quality score the engine assigns. Default is base_hit, so unless the engine explicitly overrides, all trades are base_hit.

### B. Stop Logic

- **Mental stop**: `entry - 50¢` (fallback only). Despite `base_hit_stop_cents = 15` being defined, it is **never used** in stop calculation — see Red Flag #2.
- **Technical stop**: `support - 5¢` (Ross's candle low method)
- **Trailing**: Only in home run mode (20% below MFE, starts at 1.5R). **Never in base_hit mode.**
- **R-multiples for stop movement**: 1.5R starts trail (home_run), 2.0R partial + B/E (home_run)

### C. Profit Taking

- **Base hit**: Full exit at entry + 18¢ (no partial, no trailing)
- **Home run**: 50% partial at 2.0R, stop → breakeven after partial
- **After partial**: Remaining 50% rides with 20% trailing stop
- Generic `_check_profit_target` exists (2:1 R, 50% partial) but is **unreachable**

### D. Pattern Exits

**Candle-under-candle** (L355-493):
- Requires: new 1m low + red candle + (volume > 1.5× avg OR synthetic 5m is red)
- Grace period: 60 seconds
- **Full exit** (all shares)
- 5m bucket logic uses `datetime.now()` (⚠️ wall clock, not sim clock — may misbehave in Mock Market)

**Topping tail** (L496-559):
- Requires: wick ≥ 60% of range + price near MFE (within 0.5%)
- Grace period: 120 seconds
- **Full exit** (all shares)

**Are they too aggressive?** The topping tail check fires on any candle with a big wick near highs, including healthy consolidation candles. The 120s grace helps but a strong stock could form a topping tail 3 minutes after entry and get sold. The candle-under-candle requires volume confirmation which is good, but the "OR 5m red" fallback is quite permissive.

### E. Trailing Stop

- Only in home_run mode
- Trail = `high_since_entry × (1 - 0.20)` = **20% below MFE**
- Starts at R ≥ 1.5
- Trail only moves UP, never down
- Uses `high_since_entry` (absolute high), not candle lows

### F. Time-Based Exits

- **Tighten at 18:00 ET**: Move stop to breakeven if profitable
- **Force exit at 19:30 ET**: Full exit with escalating offset (2% base, +2% every 2 min, max 10%)
- `enable_time_stop` exists in settings (120s, 50% breakout hold) but **no code implements it** — another dead setting (see Red Flag #3)
- In sim mode without sim clock: after-hours check is **completely skipped**

### G. Scale-In

- **Trigger**: Price above support, at or below entry price, RVOL not checked (despite setting `min_rvol_for_scale`)
- **Safety guards**: pending exit check, 1% stop buffer, 60s cooldown, 10s recovery grace
- **Post-scale**: Stop → breakeven only if `move_stop_to_breakeven_after_scale` (default **False**)
- **R-multiple recalculation**: Yes — `risk_per_share` and `profit_target` recalculated from new avg entry

> [!WARNING]
> The `min_rvol_for_scale` setting (default 2.0) exists but is **never checked** in `check_scale_opportunity`. Volume confirmation for scaling is entirely bypassed.

---

## 5. Red Flags

### 🔴 RF-1: Dead Code — `_check_profit_target` Never Called

**Location**: [warrior_monitor_exit.py L562-614](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py#L562-L614)  
**Impact**: Low (not a bug, but confusing)  
**Detail**: The generic R-based partial exit function exists but `evaluate_position` never calls it. Both base_hit and home_run have their own logic. This function also mutates `position.partial_taken` and `position.shares` in-place, which would cause issues if it were called.

### 🔴 RF-2: `base_hit_stop_cents` Setting Exists But Is Never Used

**Location**: [warrior_types.py L119](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_types.py#L119)  
**Impact**: Medium — the 15¢ stop concept is defined but the actual stop uses `mental_stop_cents` (50¢) or technical stop. Base hit trades have a 50¢ fallback stop with an 18¢ target — that's a **negative risk/reward ratio** (0.36:1) when technical stop is missing.

### 🔴 RF-3: `enable_time_stop` / `time_stop_seconds` Settings — No Implementation

**Location**: [warrior_types.py L88-90](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_types.py#L88-L90)  
**Impact**: Medium — Time stop (exit if no momentum after 2 minutes) is a key Ross Cameron rule. The settings exist but **no function in the codebase checks them**. Dead settings.

### 🔴 RF-4: `min_rvol_for_scale` Setting — Never Checked

**Location**: [warrior_types.py L103](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_types.py#L103)  
**Impact**: Medium — Volume confirmation for scaling is supposed to be 2× RVOL, but `check_scale_opportunity` never references this setting. Scales can happen in dry volume.

### 🔴 RF-5: Candle-Under-Candle Uses Wall Clock for 5m Bucket

**Location**: [warrior_monitor_exit.py L427](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py#L427)  
**Impact**: Low (sim only) — Uses `datetime.now()` instead of sim clock for 5m boundary alignment. In Mock Market replay, the 5m bucket will be wrong. The fallback rolling-5m mitigates this somewhat.

### 🔴 RF-6: Base Hit Mode — No Stop Protection After Partial Run

**Impact**: **HIGH** — In base_hit mode, there is zero trailing or tightening. A stock can run +15¢ (1¢ from target), reverse, and hit the -50¢ mental stop. The bot has no mechanism to protect unrealized gains below +18¢. This is the #1 reason winners are being sold too early (at +18¢ flat) or turning into losers.

### 🔴 RF-7: Home Run Trail at 20% Is Very Wide

**Impact**: Medium — For a $5 stock at +$1 (i.e., $6 high), the trail is $6 × 0.80 = $4.80, which is **$1.20 below the high** — that's below entry! The 20% percent-based trail makes no risk-adjusted sense for low-priced stocks. Ross uses candle lows, not a flat percentage.

### 🔴 RF-8: Re-Entry Only Triggers on PROFIT_TARGET Exit

**Location**: [warrior_monitor_exit.py L1013-1015](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py#L1013-L1015)  
**Impact**: Medium — The `profit_reasons` set only contains `PROFIT_TARGET`. This means re-entry is enabled after home_run trailing stop exits (which use `PROFIT_TARGET` reason) and base_hit exits, but **not** after `PARTIAL_EXIT`. This is correct behavior, but note that a candle-under-candle or topping-tail profitable exit does NOT enable re-entry, even if P&L was positive.

---

## 6. Profitability Levers

Ranked by expected impact on P&L capture:

### 🥇 Lever 1: Implement Candle-Low Trailing for Base Hit (HIGH IMPACT)

**Current**: Base hit exits at a flat +18¢ with no trailing.  
**Ross Cameron**: In reality, Ross trails with **the low of the previous 1-minute candle** even on base hits. He doesn't set a flat cents target — he lets it run and exits when the pattern breaks.

**Proposal**: After the position reaches +10¢ (or some R threshold like 0.5R), start trailing the stop at the **low of the prior completed 1m candle**. This single change would let winners run past 18¢ while protecting profit.

**Expected Impact**: ⭐⭐⭐⭐⭐ — This is the biggest gap. ROLR captured $1,539 vs Ross's $85k. Without trailing, wins are capped at 18¢ regardless of how far the stock runs.

---

### 🥈 Lever 2: Replace Percentage Trail with Candle-Low Trail in Home Run (HIGH IMPACT)

**Current**: Home run trails at 20% below MFE (a flat percentage).  
**Ross Cameron**: Trails using **the low of the prior 1-minute candle** (same as base hit, just held longer).

**Proposal**: After the 2R partial, trail the remaining shares at the low of the last completed green candle (or the lower of the last two candles). This is much tighter than 20% and matches Ross's actual methodology.

**Expected Impact**: ⭐⭐⭐⭐ — The 20% trail gives back too much profit. Ross's candle-low trail would capture significantly more of the move.

---

### 🥉 Lever 3: Add Time Stop (No Momentum Exit) (MEDIUM IMPACT)

**Current**: Settings exist (`time_stop_seconds = 120`, `breakout_hold_threshold = 0.5`) but no code implements them.  
**Ross Cameron**: "If it's not working in the first 2 minutes, get out." He exits if the stock doesn't move above his entry + 50% of the breakout quickly.

**Proposal**: Implement the time stop: if after 120 seconds the stock hasn't reached 0.5× the breakout range above entry, exit at market. This prevents slow bleed-outs that turn into stop-outs.

**Expected Impact**: ⭐⭐⭐ — Would convert some -50¢ losses into -5¢ to -10¢ scratches.

---

### Lever 4: Wire `base_hit_stop_cents` to Stop Calculation (MEDIUM IMPACT)

**Current**: `base_hit_stop_cents = 15` exists but is never used. Base hit trades use the same 50¢ mental stop as home run trades.  
**Proposal**: In `_create_new_position`, when exit mode is base_hit, use `base_hit_stop_cents` (15¢) as the mental stop instead of the global 50¢. This gives a proper 18¢:15¢ risk/reward (1.2:1) instead of 18¢:50¢ (0.36:1).

**Expected Impact**: ⭐⭐⭐ — Would significantly reduce average loss per base hit trade. Tighter stops = smaller losses = better overall P&L.

---

### Lever 5: Make Topping Tail Context-Aware (LOW-MEDIUM IMPACT)

**Current**: Fires on any candle with wick ≥ 60% near highs, full exit. No regard for trade profitability or trend.  
**Proposal**: Only fire topping tail as **full exit** if the trade is at < 1R. Above 1R, convert it to a **partial exit** (50%) and tighten trailing stop to candle low.

**Expected Impact**: ⭐⭐ — Prevents premature full exits on winners that show a brief topping tail during consolidation.

---

### Lever 6: Add RVOL Check to Scale-In (LOW IMPACT)

**Current**: `min_rvol_for_scale = 2.0` setting exists but is never checked.  
**Proposal**: Wire this setting into `check_scale_opportunity` — only scale when RVOL confirms continued interest.

**Expected Impact**: ⭐ — Prevents adding shares in dying volume, reduces risk of scaling into a reversal.

---

### Lever 7: Enable Profitable Pattern Exit Re-Entry (LOW IMPACT)

**Current**: Re-entry only triggers on `PROFIT_TARGET`. A candle-under-candle exit at +25¢ doesn't enable re-entry.  
**Proposal**: Enable re-entry for any full exit with positive P&L, not just profit target exits.

**Expected Impact**: ⭐ — Allows catching the second wave after pattern exits that were profitable.

---

## 7. Improvement Recommendations (Ranked)

| # | Change | Files Affected | Effort | Impact |
|---|--------|---------------|:------:|:------:|
| 1 | Candle-low trailing for base_hit | `warrior_monitor_exit.py` | M | ⭐⭐⭐⭐⭐ |
| 2 | Candle-low trailing for home_run | `warrior_monitor_exit.py` | M | ⭐⭐⭐⭐ |
| 3 | Implement time stop | `warrior_monitor_exit.py` | S | ⭐⭐⭐ |
| 4 | Wire `base_hit_stop_cents` | `warrior_monitor.py`, `warrior_types.py` | S | ⭐⭐⭐ |
| 5 | Context-aware topping tail | `warrior_monitor_exit.py` | S | ⭐⭐ |
| 6 | Wire RVOL to scale check | `warrior_monitor_scale.py` | S | ⭐ |
| 7 | Profitable pattern exit re-entry | `warrior_monitor_exit.py` | S | ⭐ |
| 8 | Remove dead `_check_profit_target` | `warrior_monitor_exit.py` | S | — (cleanup) |
| 9 | Remove dead time_stop settings (or implement) | `warrior_types.py` | S | — (cleanup) |

---

## 8. Dependency Graph

```
warrior_monitor.py (orchestrator)
  ├── imports: warrior_types.py (settings, position, exit types)
  ├── delegates to: warrior_monitor_exit.py (evaluate_position, handle_exit)
  ├── delegates to: warrior_monitor_scale.py (check_scale_opportunity, execute_scale_in)
  ├── delegates to: warrior_monitor_sync.py (sync_with_broker)
  └── imported by: warrior_engine.py (creates/uses monitor)

warrior_monitor_exit.py
  ├── imports: warrior_types.py (WarriorExitReason, WarriorExitSignal, WarriorPosition)
  ├── imports: trade_event_service.py (TML logging)
  ├── imports: warrior_db.py (persistence)
  ├── imports: schwab_adapter.py, fmp_adapter.py (price fallbacks)
  └── TYPE_CHECKING: warrior_monitor.py

warrior_monitor_scale.py
  ├── imports: warrior_types.py (WarriorPosition)
  ├── imports: warrior_db.py (PSM transitions)
  ├── imports: trade_event_service.py (TML logging)
  └── TYPE_CHECKING: warrior_monitor.py
```

---

## 9. Verification Commands

```powershell
# RF-1: Confirm _check_profit_target is never called from evaluate_position
Select-String -Path "nexus2\domain\automation\warrior_monitor_exit.py" -Pattern "_check_profit_target"

# RF-2: Confirm base_hit_stop_cents is never referenced outside warrior_types.py
Select-String -Path "nexus2\domain\automation\*" -Pattern "base_hit_stop_cents" -Recurse

# RF-3: Confirm time_stop has no implementation
Select-String -Path "nexus2\domain\automation\*" -Pattern "time_stop_seconds|breakout_hold_threshold|enable_time_stop" -Recurse

# RF-4: Confirm min_rvol_for_scale is never checked in scale logic
Select-String -Path "nexus2\domain\automation\warrior_monitor_scale.py" -Pattern "min_rvol_for_scale|rvol"

# RF-5: Confirm wall clock usage in candle-under-candle
Select-String -Path "nexus2\domain\automation\warrior_monitor_exit.py" -Pattern "datetime.now"

# RF-6: Confirm no trailing logic in base_hit path
Select-String -Path "nexus2\domain\automation\warrior_monitor_exit.py" -Pattern "base_hit.*trail|trail.*base_hit"

# RF-8: Confirm re-entry only on PROFIT_TARGET
Select-String -Path "nexus2\domain\automation\warrior_monitor_exit.py" -Pattern "profit_reasons"
```
