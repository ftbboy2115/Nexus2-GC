# Exit Logic Batch 1 — Status Report

**Date**: 2026-02-14  
**Reference**: [spec_exit_logic_tuning.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/reports/2026-02-14/spec_exit_logic_tuning.md)  
**Status**: ✅ IMPLEMENTED — Ready for batch test

---

## Changes Made

### Fix 4: Trail Activation → 15¢ (was 10¢)

**File**: [warrior_types.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_types.py)  
**Line**: ~122

```diff
-    base_hit_trail_activation_cents: Decimal = Decimal("10")  # Start trailing after +10¢
+    base_hit_trail_activation_cents: Decimal = Decimal("15")  # Start trailing after +15¢ (was 10¢)
```

**Rationale**: At +10¢ activation, the trail stop would be ~5¢ above entry, capturing only 5¢ on normal exits. At +15¢, the trail stop is 10-12¢ above entry — closer to Ross's 18¢ average winner.

---

### Fix 1: 2-Bar Low Candle Trail (was 1-bar)

**Files Modified**:
- [warrior_types.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_types.py) — New field `candle_trail_lookback_bars: int = 2`
- [warrior_monitor_exit.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py) — `_check_base_hit_target` (Step 1 + Step 2)

**Logic Change**:
```diff
-# Trail = low of last 1 completed candle
-prev_candle_low = Decimal(str(candles[-2].low))
+# Trail = lowest low of last N completed candles (default N=2)
+lookback = getattr(s, 'candle_trail_lookback_bars', 2)
+completed = candles[-(lookback + 1):-1]
+prev_candle_low = min(Decimal(str(c.low)) for c in completed)
```

**Rationale**: A single-candle low is noise. Using the 2-bar low allows normal intraday pullbacks without exiting. Ross holds through individual red candles if the trade is still working.

---

### Fix 3: Skip CUC Exit When Position Is Green

**Files Modified**:
- [warrior_types.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_types.py) — New field `candle_exit_only_when_red: bool = True`
- [warrior_monitor_exit.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_monitor_exit.py) — `_check_candle_under_candle` (new guard after grace period)

**Logic Change**:
```python
# GUARD 2: Skip when position is profitable (green) — let candle trail manage exit
if getattr(s, 'candle_exit_only_when_red', True) and current_price > position.entry_price:
    return None  # Position is green — let candle trail manage exit
```

**Rationale**: Ross uses "break out or bail out" for entries that aren't working. If the position is green, a pullback candle is normal — the candle trail handles exit. CUC should only fire when the trade is actually failing.

---

## Verification Plan

Run batch test on VPS to compare against $7,408 baseline:

```powershell
# On VPS (ssh root@100.113.178.7):
cd /root/nexus
python -m nexus2.tools.batch_runner --mode sequential
```

**Expected impact**: +$1,000–$2,200 from these three changes combined.

**Success criteria**:
- Total P&L ≥ $7,408 (no regression)
- Profitable cases ≥ 17
- No new $0-P&L cases
