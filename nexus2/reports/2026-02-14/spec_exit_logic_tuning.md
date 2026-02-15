# Exit Logic Tuning Spec

**Date**: 2026-02-14  
**Author**: Backend Planner (AI)  
**Scope**: Research & parameter recommendations — NO implementation  
**Baseline**: VPS $7,408 / 29 cases / 17 profitable  
**Reference**: Prior audit `nexus2/reports/2026-02-13/audit_trade_management.md` (validated)

---

## 1. Current Exit Architecture

### 1.1 Exit Check Order (`evaluate_position`, L889-997)

| # | Check | Function | Active? | Key Settings |
|---|-------|----------|---------|--------------|
| 0 | After-Hours | `_check_after_hours_exit` | ✅ | `force_exit_time_et="19:30"` |
| 0.5 | Spread | `_check_spread_exit` | ✅ | `max_spread_percent=3.0` |
| 0.7 | Time Stop | `_check_time_stop` | ❌ | `enable_time_stop=False` |
| 1 | Stop Hit | `_check_stop_hit` | ✅ | Mental or technical stop |
| 2 | Candle-Under-Candle | `_check_candle_under_candle` | ✅ | 60s grace, 1.5x vol OR 5m red |
| 3 | Topping Tail | `_check_topping_tail` | ✅ | 120s grace, 60% wick ratio |
| 4a | Base Hit Target | `_check_base_hit_target` | ✅ (if base_hit) | Candle trail → flat +18¢ fallback |
| 4b | Home Run Exit | `_check_home_run_exit` | ✅ (if home_run) | Trail at 1.5R, partial at 2R |

### 1.2 Current Parameter Values

All values from [warrior_types.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_types.py):

#### Stop Parameters
| Parameter | Value | File:Line | Purpose |
|-----------|-------|-----------|---------|
| `mental_stop_cents` | 50¢ | `warrior_types.py:62` | Fallback stop (home_run mode) |
| `base_hit_stop_cents` | 15¢ | `warrior_types.py:118` | Mental stop for base_hit |
| `use_candle_low_stop` | `True` | `warrior_types.py:63` | Use candle low as primary stop |
| `technical_stop_buffer_cents` | 5¢ | `warrior_types.py:65` | Buffer below support level |

#### Base Hit Exit Parameters
| Parameter | Value | File:Line | Purpose |
|-----------|-------|-----------|---------|
| `session_exit_mode` | `"base_hit"` | `warrior_types.py:114` | Default exit mode |
| `base_hit_profit_cents` | 18¢ | `warrior_types.py:117` | Flat profit target (fallback) |
| `base_hit_candle_trail_enabled` | `True` | `warrior_types.py:121` | Enable candle-low trailing |
| `base_hit_trail_activation_cents` | 10¢ | `warrior_types.py:122` | Trail activates after +10¢ |

#### Home Run Exit Parameters
| Parameter | Value | File:Line | Purpose |
|-----------|-------|-----------|---------|
| `home_run_trail_after_r` | 1.5R | `warrior_types.py:126` | Start trailing after 1.5R |
| `home_run_trail_percent` | 20% | `warrior_types.py:127` | Trail 20% below high |
| `home_run_partial_at_r` | 2.0R | `warrior_types.py:125` | Take 50% partial at 2R |
| `home_run_move_to_be` | `True` | `warrior_types.py:128` | Move stop to BE after partial |

#### Pattern Exit Parameters
| Parameter | Value | File:Line | Purpose |
|-----------|-------|-----------|---------|
| `enable_candle_under_candle` | `True` | `warrior_types.py:76` | Candle-under-candle exit |
| `candle_exit_grace_seconds` | 60s | `warrior_types.py:77` | Grace period after entry |
| `candle_exit_volume_multiplier` | 1.5x | `warrior_types.py:78` | Volume confirmation threshold |
| `enable_topping_tail` | `True` | `warrior_types.py:79` | Topping tail exit |
| `topping_tail_threshold` | 0.6 | `warrior_types.py:80` | Wick > 60% of range |
| `topping_tail_grace_seconds` | _120s (implicit)_ | `exit.py:572` via `getattr` | Grace period (NOT in settings) |

---

## 2. Diagnosis: Why Exits Are Losing Money

### 2.1 The Core Problem

The bot enters at approximately the same time as Ross, but captures a fraction of the move:

| Case | Ross P&L | Bot P&L | Ross Hold | Bot Likely Exit Reason |
|------|---------|---------|-----------|----------------------|
| MLEC | +$43,000 | -$412 | Long hold, adds | Stop hit or premature pattern exit |
| LCFY | +$10,500 | -$483 | Multiple trades | 3 entries, all stopped out |
| BATL 126 | ~$2,000 | -$176 | Scaled out | Candle trail or stop too tight |

Ross's methodology (from [warrior.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/strategies/warrior.md)):
- **Average winner = 18¢/share** — this is achieved across MANY shares (5K-50K) with scaling
- **Partial exits at structural levels** (whole/half dollars, resistance), NOT at fixed cents
- **Never stops with fixed % or fixed ¢** — uses technical levels (candle low, support)
- **Adds back after profit-taking** — the sell→add→sell cycle is his signature

### 2.2 Specific Failure Modes

#### Failure Mode A: Candle-Low Trail Too Sensitive

**`_check_base_hit_target`** (L678-788):
- Trail activates after +10¢ from entry
- Trail = low of last completed 1-min candle
- Exit when `current_price <= candle_trail_stop`

**Problem**: A normal 1-minute pullback within a winning trade triggers exit. Ross holds through these — he exits on multi-candle weakness, not single candle dips.

**Evidence**: The trail is set to the exact low of the prior candle. A 1¢ wick below that low triggers a full exit. Ross would trail with a wider reference (e.g., low of last 2-3 candles, or VWAP).

#### Failure Mode B: Base Hit Stop Too Tight (15¢)

**`_create_new_position`** (L370-464 in `warrior_monitor.py`):
```python
if exit_mode == "base_hit":
    mental_stop = entry_price - s.base_hit_stop_cents / 100  # -15¢
```

**Problem**: A 15¢ stop on a $5-10 stock is 1.5-3% — this is extremely tight. Normal intraday noise can trigger a stop.

**Strategy reference**: Ross says "mental stop at low of entry candle" which varies by stock. On a $10 stock, entry candle low might be $9.80 (20¢), on a $5 stock it might be $4.90 (10¢). The 15¢ fixed value is a poor proxy.

**Root cause**: When `use_candle_low_stop=True` and `technical_stop` is available (from the entry candle low), the technical stop is used. But if no support level is passed, the 15¢ mental stop kicks in as the effective stop — which may be too tight.

#### Failure Mode C: Candle-Under-Candle Exits Winners

**`_check_candle_under_candle`** (L411-549):
- Grace: 60 seconds
- Triggers when: current candle low < previous candle low AND current candle is red
- Confirmation: high volume (1.5x avg) OR synthetic 5m candle is red
- **Exits ALL shares** (full position exit)

**Problem**: A healthy pullback within a winning trend will often produce a red candle with a new low. The confirmation check helps, but:
1. Volume confirmation (1.5x avg) can trigger on normal pullback bars if volume is elevated (which it always is on high-RVOL stocks)
2. The 5m boundary check is an approximation that may trigger falsely

**Strategy reference**: Ross uses "break out or bail out" but with discretion — he gives stocks room if the overall trend is intact. The bot applies this rigidly.

#### Failure Mode D: No Structural Profit-Taking

Ross takes profits at **structural levels**:
- Whole dollars: $7, $8, $9, $10
- Half dollars: $7.50, $8.50
- Resistance: prior HoD, 200 MA
- After $1/share gain

The bot has **none of this**. It uses:
- Candle-low trail (exits on pullback, not at level)
- Flat +18¢ fallback (too small to capture meaningful moves)

This means the bot either:
- Trails out on the first pullback within a winning trade (capturing < 18¢)
- Rides to the flat target of +18¢ and exits everything

Neither captures the $1-3/share moves Ross regularly achieves.

#### Failure Mode E: No Re-Entry After Pattern Exit

When candle-under-candle or topping tail causes a full exit, `_handle_profit_exit` only enables re-entry for `PROFIT_TARGET` exits (L1144-1147):

```python
profit_reasons = {WarriorExitReason.PROFIT_TARGET}
if signal.reason in profit_reasons and monitor._on_profit_exit:
```

Pattern exits (candle_under_candle, topping_tail) do NOT enable re-entry. So if the bot exits on a normal pullback, it can't get back in when the stock recovers.

---

## 3. Tuning Recommendations

### Priority Order (Highest P&L Impact First)

---

### 🔴 FIX 1: Widen Candle Trail to 2-Bar Low (HIGH IMPACT)

**Current**: Trail = low of last 1 completed candle  
**Proposed**: Trail = lowest low of last 2 completed candles

| Parameter | Current | Proposed | Location |
|-----------|---------|----------|----------|
| _New: `candle_trail_lookback_bars`_ | 1 (implicit) | 2 | `warrior_types.py` (new field) |

**Rationale**: A single-candle low is noise. Trailing with the 2-bar low allows normal intraday pullbacks without exiting. Ross would never exit because of a single red candle's wick if the trade is still working.

**Implementation**: In `_check_base_hit_target` L708 and L727, change:
```python
# Current: prev_candle_low = Decimal(str(candles[-2].low))
# Proposed: prev_candle_low = min(candle.low for candle in candles[-3:-1])  # 2-bar low
```

**Expected impact**: MEDIUM-HIGH. Prevents premature exits on normal single-bar pullbacks. Could improve BATL 126, TNMG, and other cases where the trade works but exits too early.

**Risk**: May hold slightly longer into genuine reversals. Acceptable tradeoff — Ross gives room.

---

### 🔴 FIX 2: Structural Profit Targets (HIGH IMPACT)

**Current**: No structural-level profit taking  
**Proposed**: Add partial exits at whole/half-dollar levels

This is the **most important missing feature** vs Ross's methodology. Ross sells partial at $7, $7.50, $8, etc.

| Parameter | Current | Proposed | Location |
|-----------|---------|----------|----------|
| _New: `enable_structural_partials`_ | N/A | `True` | `warrior_types.py` (new field) |
| _New: `structural_partial_fraction`_ | N/A | 0.25 (25%) | `warrior_types.py` (new field) |
| _New: `structural_level_granularity`_ | N/A | `"half"` ($0.50) | `warrior_types.py` (new field) |

**Behavior**: When price crosses a whole/half-dollar level above entry, sell 25% of remaining shares. Move stop to breakeven after first structural partial.

**Implementation**: New function `_check_structural_partial` inserted before Check 4 in `evaluate_position`. Uses `WarriorExitReason.PARTIAL_EXIT`.

**Expected impact**: HIGH. This is the primary mechanism Ross uses to lock in profits on winning trades. Without it, the bot either exits too early (candle trail) or holds to the stop.

**Risk**: Requires careful interaction with existing partial-taken logic. Must handle multiple partials (one per level).

> [!IMPORTANT]
> This is the single highest-impact change. Ross's signature pattern is "sell at $7, add back at $7.05, sell at $7.50" — the bot has zero structural awareness.

---

### 🟡 FIX 3: Candle-Under-Candle Context Gate (MEDIUM IMPACT)

**Current**: Exits if candle-under-candle detected after 60s + volume/5m confirmation  
**Proposed**: Skip candle-under-candle exit when position is profitable (above entry)

| Parameter | Current | Proposed | Location |
|-----------|---------|----------|----------|
| _New: `candle_exit_only_when_red`_ | N/A | `True` | `warrior_types.py` (new field) |

**Rationale**: Ross uses "break out or bail out" for entries that aren't working. If the position is green (current_price > entry_price), a pullback candle is normal — the candle trail handles the exit. Candle-under-candle should only exit when the trade is failing.

**Implementation**: In `_check_candle_under_candle`, after L438, add:
```python
if s.candle_exit_only_when_red and current_price > position.entry_price:
    return None  # Position is green — let candle trail manage exit
```

**Expected impact**: MEDIUM. Prevents premature full exits on winning trades. The candle trail already protects downside when position is green.

**Risk**: Low. The stop and candle trail still protect if the trade reverses.

---

### 🟡 FIX 4: Raise Trail Activation to +15¢ (MEDIUM IMPACT)

**Current**: `base_hit_trail_activation_cents = 10`  
**Proposed**: `base_hit_trail_activation_cents = 15`

**Rationale**: Activating the trail at +10¢ means the trail starts very close to entry. On volatile stocks, a normal bounce can trigger the trail activation and then immediately hit the trail stop. Waiting until +15¢ gives the trade more room to develop.

**Strategy reference**: Ross's average winner is 18¢/share. If trail activates at 10¢ and the trail stop is 5¢ above entry, the bot captures only 5¢ on a normal exit. At 15¢ activation, the trail stop is likely 10-12¢ above entry — closer to Ross's average.

| Parameter | Current | Proposed | Location |
|-----------|---------|----------|----------|
| `base_hit_trail_activation_cents` | 10 | 15 | `warrior_types.py:122` |

**Expected impact**: MEDIUM. Lets winners develop before trailing. Prevents the "activate trail at +10¢, immediately hit trail stop at +5¢" scenario.

**Risk**: May exit slightly later on reversals. Net positive given Ross's average winner is 18¢.

---

### 🟡 FIX 5: Enable Re-Entry After Pattern Exits (MEDIUM IMPACT)

**Current**: Re-entry only enabled after `PROFIT_TARGET` exits  
**Proposed**: Also enable after `CANDLE_UNDER_CANDLE` and `TOPPING_TAIL` exits when profitable

| Parameter | Current | Proposed | Location |
|-----------|---------|----------|----------|
| Logic change in `handle_exit` | `profit_reasons = {PROFIT_TARGET}` | Add CUC and TT when green | `warrior_monitor_exit.py:1144` |

**Rationale**: Ross frequently exits a stock on weakness, then re-enters when it proves itself again. The bot currently "gives up" after a pattern exit.

**Implementation**: In `handle_exit` L1144-1147, expand `profit_reasons` to include pattern exits when the exit P&L was positive.

**Expected impact**: MEDIUM. Enables the sell→re-enter cycle on pattern exits. Important for stocks that have volatile pullbacks but keep trending up.

**Risk**: Must maintain the 2-strike rule for stop-based exits. Only re-enable on GREEN pattern exits.

---

### 🟢 FIX 6: Topping Tail R-Threshold Gate (LOW-MEDIUM IMPACT)

**Current**: Topping tail exits at any profit level after 120s  
**Proposed**: Only exit on topping tail when position is < 1R profitable

| Parameter | Current | Proposed | Location |
|-----------|---------|----------|----------|
| _New: `topping_tail_max_r_for_exit`_ | N/A | 1.0 | `warrior_types.py` (new field) |

**Rationale**: At high R multiples, a topping tail is just normal price action near highs. Ross would sell partial at the level, not exit completely. The candle trail is a better exit mechanism at high R.

**Implementation**: In `_check_topping_tail`, add:
```python
max_r = getattr(s, 'topping_tail_max_r_for_exit', 1.0)
if r_multiple > max_r:
    return None  # Let candle trail handle at high R
```

**Expected impact**: LOW-MEDIUM. Prevents premature full exits on stocks that are working well.

---

### 🟢 FIX 7: Time Stop for Losing Trades Only (LOW IMPACT — EVALUATION)

**Current**: `enable_time_stop = False` (disabled — "kills winners NPT -$1740")  
**Previous issue**: Time stop killed profitable trades near breakeven  
**Proposed**: Re-evaluate with a more targeted condition

| Parameter | Current | Proposed | Location |
|-----------|---------|----------|----------|
| `enable_time_stop` | `False` | `True` (re-evaluate) | `warrior_types.py:83` |
| `time_stop_seconds` | 600 (10 bars) | 900 (15 bars) | `warrior_types.py:84` |

**Current behavior** (`_check_time_stop` L319-372):
- After N bars, if `current_price < entry_price` → full exit
- Simple check: is stock below entry? If yes after N bars → exit

**Modified proposal**: Only time-stop if stock is more than 5¢ below entry (avoid killing trades near breakeven that might recover):
```python
if current_price >= position.entry_price - Decimal("0.05"):
    return None  # Near breakeven — give it time
```

**Expected impact**: LOW. Reduces max loss on hopeless trades (LCFY, VERO type) without killing near-breakeven positions. Needs A/B testing.

**Risk**: Was previously NPT -$1740 when enabled. The 5¢ buffer + 15-bar delay should fix that. **Requires careful batch testing before deployment.**

---

## 4. Implementation Priority Matrix

| # | Fix | Effort | Risk | Expected Δ P&L | Priority |
|---|-----|--------|------|-----------------|----------|
| 2 | Structural profit targets | L (new function) | MED | +$2,000-4,000 | **P0 — Do first** |
| 1 | Widen candle trail to 2-bar | S (2 line change) | LOW | +$500-1,000 | **P1** |
| 3 | CUC context gate | S (3 line change) | LOW | +$300-700 | **P1** |
| 4 | Raise trail activation to 15¢ | S (1 line change) | LOW | +$200-500 | **P2** |
| 5 | Re-entry after pattern exits | S (5 line change) | LOW | +$300-800 | **P2** |
| 6 | Topping tail R gate | S (3 line change) | LOW | +$100-300 | **P3** |
| 7 | Time stop re-evaluation | M (logic change) | MED | +$200-600 | **P3 — needs A/B test** |

**Estimated cumulative impact**: +$3,600–$7,900 on top of $7,408 baseline

---

## 5. Recommended Implementation Sequence

### Batch 1 (Quick Wins — P1+P2, minimal risk)

1. **Fix 4**: `base_hit_trail_activation_cents` = 15 (1-line settings change)
2. **Fix 1**: Widen candle trail to 2-bar low (2-line logic change)
3. **Fix 3**: CUC context gate — skip when profitable (3-line guard)

**Run batch test after Batch 1 to measure impact.**

### Batch 2 (Structural — P0, largest impact)

4. **Fix 2**: Structural profit targets (new function + wiring)

This is the most complex change but highest impact. Should be done after Batch 1 validates the trail improvements.

**Run batch test after Batch 2.**

### Batch 3 (Re-entry + Polish — P2+P3)

5. **Fix 5**: Re-entry after pattern exits (logic expansion)
6. **Fix 6**: Topping tail R gate (guard addition)
7. **Fix 7**: Time stop re-evaluation (A/B test)

**Run batch test after Batch 3.**

---

## 6. Verification Plan

Each batch change should be verified by running the VPS batch test suite:

```powershell
# On VPS (ssh root@100.113.178.7):
cd /root/nexus
python -m nexus2.tools.batch_runner --mode sequential
```

**Success criteria per batch**:
- Total P&L ≥ previous baseline (no regression)
- Profitable cases ≥ previous count
- No new $0-P&L cases (no broken entries)
- Specific case improvements: MLEC, LCFY, BATL 126 should show improvement

**Per-case comparison**: Save before/after P&L per case for regression analysis.

---

## 7. Settings Not Covered (For Reference)

These settings are correctly configured and should NOT be changed:
- `session_exit_mode = "base_hit"` → Correct for the batch test baseline
- `mental_stop_cents = 50` → Fallback only, rarely used
- `enable_after_hours_exit = True` → Necessary for close of day
- `enable_spread_exit = True` → Safety feature
- `enable_scaling = True` → Already working
- `partial_exit_fraction = 0.5` → Will need adjustment for structural partials (multiple levels)

---

## 8. Open Questions for Clay

1. **Structural partial size**: Should the bot sell 25% or 33% at each whole/half-dollar level? Ross varies this — sometimes 50%, sometimes 25%.

2. **Trail lookback**: 2-bar low is the minimum improvement. Should we test 3-bar low as well? More bars = more room but slower reaction.

3. **Time stop**: Previous testing showed NPT -$1740. Should we A/B test with the 5¢ buffer in Batch 3, or skip entirely?

4. **Home run mode**: Currently unused in batch testing (all cases use base_hit). Should any high-quality setups (quality_score ≥ 9) auto-select home_run mode?
