# Validation Report: Exit Logic P&L Leakage Audit

**Date:** 2026-02-16  
**Validator:** Audit Validator  
**Audit Under Review:** `nexus2/reports/2026-02-16/audit_exit_logic_leakage.md`  
**Auditor:** Code Auditor

---

## Claim Verification Table

| # | Claim | Result | Key Evidence |
|---|-------|--------|-------------|
| 1 | `session_exit_mode` defaults to `"base_hit"`, not in settings JSON | **PASS** | `warrior_types.py:119`, zero JSON results |
| 2 | Home run promotion requires ≥5x RVOL | **PASS** | `warrior_engine_entry.py:1144` |
| 3 | `_check_profit_target` is dead code | **PASS** | Only 1 grep hit: function definition at line 626 |
| 4 | Base hit exits 100% of shares | **PASS** | `warrior_monitor_exit.py:760`: `shares_to_exit=position.shares` |
| 5 | Candle trail activation fixed at +15¢ | **PASS** | `warrior_types.py:127`: `Decimal("15")` |
| 6 | Flat fallback is +18¢ | **PASS** | `warrior_types.py:122` + `warrior_monitor_exit.py:775` |
| 7 | Topping tail runs BEFORE mode-aware exit, exits all shares | **PASS** | `evaluate_position` lines 984-987 vs 989-1007; `shares_to_exit=position.shares` at line 617 |
| 8 | Scaling blocked when price past profit target | **PASS** | `warrior_engine_entry.py:898-913`: `price_past_target` guard |

---

## Detailed Verification

### Claim 1: `session_exit_mode` defaults to `"base_hit"` and is NOT in `warrior_settings.json`

**Claim:** `warrior_types.py:119` — `session_exit_mode: str = "base_hit"`  
**Verification:** `view_file` on `warrior_types.py` line 119; `grep_search` for `session_exit_mode` in `*.json` files  
**Actual Output:**
```python
# warrior_types.py line 119:
session_exit_mode: str = "base_hit"  # Default to safer base hit mode
```
JSON search: **No results found**  
**Result:** PASS  
**Notes:** Exactly as auditor stated. The default is hardcoded and never overridden by settings JSON.

---

### Claim 2: Home run promotion requires 5x+ RVOL

**Claim:** `warrior_engine_entry.py:1144-1150` — `elif entry_volume_ratio >= 5.0: selected_exit_mode = "home_run"`  
**Verification:** `view_file` on `warrior_engine_entry.py` lines 1144-1150  
**Actual Output:**
```python
# Line 1144-1150:
elif entry_volume_ratio >= 5.0:
    # Extreme volume explosion (5x+): override to home_run for potential runner
    selected_exit_mode = "home_run"
    logger.info(
        f"[Warrior Entry] {symbol}: exit_mode=home_run "
        f"(VOLUME EXPLOSION: {entry_volume_ratio:.1f}x, overriding session setting)"
    )
```
**Result:** PASS  
**Notes:** Line numbers and code match exactly. Re-entries are forced to `base_hit` at line 1139 as auditor noted.

---

### Claim 3: `_check_profit_target` is dead code (never called)

**Claim:** Function defined at `warrior_monitor_exit.py:626` but has zero callers  
**Verification:** `grep_search` for `_check_profit_target` across ALL `*.py` files in `nexus2/`  
**Actual Output:**
```
Single result:
  warrior_monitor_exit.py:626 — async def _check_profit_target(
```
**Result:** PASS  
**Notes:** Confirmed: function appears only at its definition (line 626). It is NOT called anywhere in `evaluate_position()` or anywhere else. Dead code.

---

### Claim 4: Base hit exits 100% of shares (no partial)

**Claim:** `warrior_monitor_exit.py:755-764` — `shares_to_exit=position.shares` (full position)  
**Verification:** `view_file` on `warrior_monitor_exit.py` lines 755-764  
**Actual Output:**
```python
# Lines 755-764:
return WarriorExitSignal(
    position_id=position.position_id,
    symbol=position.symbol,
    reason=WarriorExitReason.PROFIT_TARGET,
    exit_price=current_price,
    shares_to_exit=position.shares,  # FULL EXIT
    pnl_estimate=pnl,
    r_multiple=r_multiple,
    trigger_description=f"Candle trail stop hit (trail=${position.candle_trail_stop:.2f})",
)
```
**Result:** PASS  
**Notes:** Confirmed: `shares_to_exit=position.shares` — full position exit. The flat fallback path at lines 791-800 also uses `shares_to_exit=position.shares`. No partial mechanism in base_hit mode.

---

### Claim 5: Candle trail activation is fixed at +15¢

**Claim:** `warrior_types.py:127` — `base_hit_trail_activation_cents: Decimal = Decimal("15")`  
**Verification:** `view_file` on `warrior_types.py` line 127  
**Actual Output:**
```python
# Line 127:
base_hit_trail_activation_cents: Decimal = Decimal("15")  # Start trailing after +15¢ (was 10¢)
```
**Result:** PASS  
**Notes:** Exact match. The comment confirms this was recently changed from 10¢ to 15¢.

---

### Claim 6: Flat fallback is +18¢

**Claim:** `warrior_types.py:122` — `base_hit_profit_cents: Decimal = Decimal("18")`; used at `warrior_monitor_exit.py:774-775`  
**Verification:** `view_file` on both locations  
**Actual Output:**
```python
# warrior_types.py line 122:
base_hit_profit_cents: Decimal = Decimal("18")  # Take profit at +18¢ (Ross's typical)

# warrior_monitor_exit.py lines 774-775:
# ---- FALLBACK: Flat +18¢ target (when trail disabled or no bars) ----
target_price = position.entry_price + s.base_hit_profit_cents / 100
```
**Result:** PASS  
**Notes:** Both locations confirmed. The +18¢ is used directly in the fallback path when candle trail can't activate.

---

### Claim 7: Topping tail runs BEFORE mode-aware exit and exits all shares

**Claim:** In `evaluate_position()`, topping tail (CHECK 3) runs before mode-aware (CHECK 4)  
**Verification:** `view_file` on `warrior_monitor_exit.py` lines 984-1007; and lines 612-617 for share count  
**Actual Output:**
```python
# Lines 984-987 (CHECK 3):
# CHECK 3: Topping Tail
signal = await _check_topping_tail(monitor, position, current_price, r_multiple)
if signal:
    return signal

# Lines 989-1007 (CHECK 4):
# CHECK 4: Mode-Aware Profit Target / Trailing Stop
exit_mode = get_effective_exit_mode(monitor, position)
...
```
Topping tail exit signal (lines 612-617):
```python
return WarriorExitSignal(
    ...
    shares_to_exit=position.shares,  # ALL SHARES
    ...
)
```
**Result:** PASS  
**Notes:** Confirmed: topping tail (CHECK 3) runs before mode-aware exit (CHECK 4) and exits `position.shares` (all shares). A 2-minute grace period exists at line 580.

---

### Claim 8: Scaling is blocked when price is past profit target

**Claim:** `warrior_engine_entry.py:898-913` blocks scale-ins via `price_past_target`  
**Verification:** `view_file` on `warrior_engine_entry.py` lines 898-913  
**Actual Output:**
```python
# Lines 898-913:
# Block if: (1) Current price >= profit target, OR (2) Unrealized P&L > 25%
profit_target = existing_position.profit_target or Decimal("0")
price_past_target = profit_target > 0 and current_price >= profit_target
pnl_above_threshold = unrealized_pnl_pct > 25  # 25% gain threshold

if price_past_target or pnl_above_threshold:
    reason = (
        f"past target ${profit_target:.2f}" if price_past_target
        else f"+{unrealized_pnl_pct:.1f}% unrealized"
    )
    logger.warning(
        f"[Warrior Entry] {symbol}: BLOCKING SCALE-IN - position already {reason}. "
        f"Take profit first per Ross Cameron methodology. "
        f"(entry=${existing_position.entry_price:.2f}, current=${current_price:.2f})"
    )
    return
```
**Result:** PASS  
**Notes:** Confirmed: scale-ins are blocked when either (1) price ≥ profit target, or (2) unrealized P&L > 25%. This is in `_scale_into_existing_position()`, not the monitor-level scaling path. The auditor's claim is accurate — the bot won't add to runners that have already passed target.

---

## Exit Flow Order — Complete Sequence Verification

**Auditor's Claimed Order:**
```
CHECK 0:   _check_after_hours_exit
CHECK 0.5: _check_spread_exit
CHECK 0.7: _check_time_stop (DISABLED)
CHECK 1:   _check_stop_hit
CHECK 2:   _check_candle_under_candle
CHECK 3:   _check_topping_tail
CHECK 4:   MODE-AWARE (_check_base_hit_target or _check_home_run_exit)
```

**Verification:** `view_file` on `warrior_monitor_exit.py` lines 959-1007  
**Actual Output (summarized from code):**
```python
# Line 959-960: CHECK 0 — _check_after_hours_exit
# Line 964-965: CHECK 0.5 — _check_spread_exit
# Line 969-970: CHECK 0.7 — _check_time_stop
# Line 974-975: CHECK 1 — _check_stop_hit
# Line 979-980: CHECK 2 — _check_candle_under_candle
# Line 984-985: CHECK 3 — _check_topping_tail
# Line 989-1007: CHECK 4 — mode-aware (base_hit or home_run)
```

**Result:** PASS  
**Notes:** Exact match. Time stop is controlled by `enable_time_stop` (default `False` per `warrior_types.py:85`), confirming the "(DISABLED)" annotation. All checks use early-return pattern — first triggered check wins.

---

## Overall Quality Rating

### **HIGH** ✅

All 8 claims verified. Line numbers match. Code snippets accurate. Exit flow order confirmed. The auditor's report is thorough, well-evidenced, and structurally sound.

No discrepancies found between the auditor's claims and the actual source code.

---

## Summary

The Code Auditor's exit logic leakage analysis is **accurate and trustworthy**. The root causes identified — base_hit default, 5x RVOL threshold, dead code, no partial-then-ride, topping tail killing runners, and scaling blocks — are all substantiated by the actual source code. The priority recommendations in the audit report are actionable and well-grounded.
