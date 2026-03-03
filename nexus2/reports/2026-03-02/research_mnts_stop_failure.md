# MNTS Stop Failure Investigation

**Case:** `ross_mnts_20260209` | **Date:** 2026-02-09 | **Bot P&L:** -$15,502.64 | **Ross P&L:** +$9,000

## Root Cause

The `max_stop_pct` (10%) cap applied inside `calculate_stop_price()` is **completely bypassed** by the `technical_stop` path in `_create_new_position()`.

### The Data Trail

MNTS exploded from $6.28 → $9.22 in a single bar at 08:00 (bar 12). The 5-bar consolidation low at entry includes sparse premarket bars:

| Bar | Time | O | H | L | C | V |
|-----|------|-------|------|------|------|---------|
| 8 | 06:49 | 6.02 | 6.02 | 6.02 | 6.02 | 200 |
| 9 | 07:00 | 6.12 | 6.12 | 6.12 | 6.12 | 127 |
| 10 | 07:23 | 6.12 | 6.12 | 6.12 | 6.12 | 352 |
| 11 | 07:57 | 6.18 | 6.18 | 6.18 | 6.18 | 442 |
| **12** | **08:00** | **6.28** | **9.22** | **6.28** | **8.73** | **318,149** |

- **5-bar consolidation low** = min(6.02, 6.12, 6.12, 6.18, 6.28) = **$6.02**
- Entry price ≈ $8.73

After the 08:01 HOD ($9.35), price reversed hard: $7.96 → $7.46 → $7.14 → consolidated $7.00-$7.80 → faded to $6.15 at EOD.

### The Code Flow (Stop Bypass)

```
calculate_stop_price()                     ← warrior_entry_sizing.py:31
├── consolidation_low = $6.02              ← min of 5 bars
├── mental_stop = $6.02 - $0.02 = $6.00
├── stop_distance_pct = ($8.73 - $6.00) / $8.73 = 31.3%
├── 31.3% > max_stop_pct (10%)            ← CAPPED
├── mental_stop = $8.73 * 0.90 = $7.86    ← capped value returned
└── RETURNS: mental_stop=$7.86, calculated_candle_low=$6.02  ← RAW value

enter_position()                           ← warrior_engine_entry.py:1250
└── support_level = calculated_candle_low = $6.02  ← RAW, UNCAPPED

_create_new_position()                     ← warrior_monitor.py:374
├── mental_stop = $8.73 - $0.50 = $8.23   ← fallback (50¢), IGNORED
├── technical_stop = $6.02 - $0.05 = $5.97 ← support_level - 5¢ buffer
├── use_candle_low_stop = True
└── current_stop = technical_stop = $5.97  ← THE ACTUAL STOP USED
```

> [!CAUTION]
> **`current_stop` = $5.97** — a **32% stop** from entry at $8.73.
> The 10% cap was applied to `mental_stop` but the raw `calculated_candle_low` bypassed it entirely via `support_level → technical_stop → current_stop`.

### Why the Stop Never Fired

| Check | Value | Price Reached? |
|-------|-------|---------------|
| `current_stop` | $5.97 | ❌ EOD low = $6.02 (never breached) |
| 10%-capped stop (not used) | $7.86 | ✅ Breached at 08:03 (low $7.80) |
| After-hours force exit | 19:30 ET | ✅ Triggered at $6.15 |

The position bled from ~$8.73 to $6.15 over **11.5 hours**, finally exiting only at the after-hours force exit.

### P&L Math

With `position_size` shares at entry ~$8.73, exit ~$6.15:
- Per-share loss: $2.58
- With ~6,000 shares: **-$15,502.64**

## The Bug

**File:** [warrior_engine_entry.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py#L1249-L1250)

```python
# Line 1249-1250: Raw candle low passed as support_level
if calculated_candle_low:
    support_level = calculated_candle_low  # ← RAW, UNCAPPED
```

**File:** [warrior_monitor.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor.py#L419-L426)

```python
# Line 419-426: technical_stop computed from raw support_level, used as current_stop
if support_level and s.use_technical_stop:
    technical_stop = support_level - s.technical_stop_buffer_cents / 100  # $6.02 - $0.05 = $5.97

if technical_stop and s.use_candle_low_stop:
    current_stop = technical_stop  # $5.97 — bypasses the 10% cap entirely
```

## Proposed Fix

The `support_level` passed to `add_position` should use the **capped** `mental_stop` from `calculate_stop_price()`, not the raw `calculated_candle_low`:

```diff
# warrior_engine_entry.py, line 1249-1253
 if calculated_candle_low:
-    support_level = calculated_candle_low
+    support_level = Decimal(str(mental_stop)) + Decimal("0.02")  # Reverse the -2¢ buffer
 else:
     support_level_raw = watched.orb_low or ...
```

Or apply the same `max_stop_pct` cap inside `_create_new_position` on the `technical_stop`:

```diff
# warrior_monitor.py, after line 420
 if support_level and s.use_technical_stop:
     technical_stop = support_level - s.technical_stop_buffer_cents / 100
+    # Cap technical stop to max 10% distance (same as calculate_stop_price)
+    if entry_price > 0:
+        max_distance = entry_price * Decimal("0.10")
+        if (entry_price - technical_stop) > max_distance:
+            technical_stop = entry_price - max_distance
```

## Impact Assessment

This bug affects **every case where the 5-bar consolidation low is far from entry** (common with premarket gappers). The 10% cap in `calculate_stop_price()` provides a false sense of safety — the actual `current_stop` used by the monitor bypasses it entirely.
