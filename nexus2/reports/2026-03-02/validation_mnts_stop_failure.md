# Validation Report: MNTS Stop Failure Investigation

**Source:** `nexus2/reports/2026-03-02/research_mnts_stop_failure.md`
**Validator:** Audit Validator
**Date:** 2026-03-03

---

## Claim Verification Table

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | `calculate_stop_price()` returns raw `calculated_candle_low` alongside capped `mental_stop` | **PASS** | Line 88 returns `(mental_stop, stop_method, calculated_candle_low)` |
| 2 | `warrior_engine_entry.py` line 1249 passes `calculated_candle_low` as `support_level` | **PASS** | Lines 1249-1250: `if calculated_candle_low: support_level = calculated_candle_low` |
| 3 | `_create_new_position` sets `current_stop = technical_stop` when `use_candle_low_stop=True` | **PASS** | Lines 425-426: `if technical_stop and s.use_candle_low_stop: current_stop = technical_stop` |
| 4 | `max_stop_pct` config value is `0.10` (10%) in `warrior_types.py` | **PASS (location corrected)** | Found in `warrior_engine_types.py:92`, not `warrior_types.py` |

---

## Detailed Evidence

### Claim 1: `calculate_stop_price()` returns raw candle low

**Claim:** `calculate_stop_price()` returns raw `calculated_candle_low` ($6.02) alongside the capped `mental_stop` ($7.86).

**Verification:** `view_file warrior_entry_sizing.py` lines 31-88

**Actual Output (line 88):**
```python
return mental_stop, stop_method, calculated_candle_low
```

The function at line 66 sets `calculated_candle_low = consolidation_low` (raw min of 5 bars), then at lines 73-75 caps only `mental_stop` when `stop_distance_pct > max_pct`. The raw `calculated_candle_low` is never capped.

**Result:** PASS

---

### Claim 2: `support_level = calculated_candle_low` (raw, uncapped)

**Claim:** `warrior_engine_entry.py` line 1249 passes `calculated_candle_low` as `support_level` (not the capped `mental_stop`).

**Verification:** `view_file warrior_engine_entry.py` lines 1247-1253

**Actual Output (lines 1249-1250):**
```python
if calculated_candle_low:
    support_level = calculated_candle_low  # Use calculated low for correct stop
```

The comment even says "Use calculated low for correct stop" — the raw, uncapped consolidation low is passed directly as `support_level` to `add_position()` at line 1512.

**Result:** PASS

---

### Claim 3: `current_stop = technical_stop` bypasses 10% cap

**Claim:** `_create_new_position` in `warrior_monitor.py` sets `current_stop = technical_stop` (from `support_level - 5¢`) when `use_candle_low_stop=True`, bypassing the 10% cap.

**Verification:** `view_file warrior_monitor.py` lines 417-428

**Actual Output (lines 419-428):**
```python
# Technical stop: Support/ORB low - buffer (Ross's actual method: low of entry candle)
technical_stop = None
if support_level and s.use_technical_stop:
    technical_stop = support_level - s.technical_stop_buffer_cents / 100

# Current stop: Use CANDLE LOW (technical) as PRIMARY for ALL modes
# Ross's rule: "Max loss per trade = Low of entry candle"
# The mental_stop (base_hit: 15¢, home_run: 50¢) is FALLBACK only when no candle data
if technical_stop and s.use_candle_low_stop:
    current_stop = technical_stop  # Ross's actual method
```

> [!IMPORTANT]
> The report claimed lines 419-428. Actual code is at lines 418-428 (1 line offset). The logic is exactly as described: `technical_stop = support_level - buffer`, then `current_stop = technical_stop` with no cap applied. The 10% cap from `calculate_stop_price()` only applies to `mental_stop`, which is the fallback path.

**Result:** PASS

---

### Claim 4: `max_stop_pct` is 0.10 (10%)

**Claim:** The `max_stop_pct` config value is `0.10` (10%) — verify in `warrior_types.py` or `warrior_engine config`.

**Verification Command:** `grep_search` for `max_stop_pct` in `nexus2/domain/automation/`

**Actual Output:**
```
warrior_engine_types.py:92:    max_stop_pct: float = 0.10  # Max stop distance as % of entry price (10% = conservative; sweep showed 5%=$354K, 10%=$233K, 25%=$160K)
warrior_entry_sizing.py:70:    # Cap stop distance if it exceeds max_stop_pct
warrior_entry_sizing.py:72:    max_pct = Decimal(str(engine.config.max_stop_pct))
```

> [!NOTE]
> The claim suggested checking `warrior_types.py`. The actual location is `warrior_engine_types.py:92`. The value is confirmed as `0.10` (10%). This is a minor location discrepancy — the config class and value are correct.

**Result:** PASS (location corrected: `warrior_engine_types.py`, not `warrior_types.py`)

---

## Overall Quality Rating

**HIGH** — All 4 claims verified, one minor file name discrepancy (claim 4 referenced `warrior_types.py` but config is in `warrior_engine_types.py`). The root cause analysis in the research report is accurate: the 10% `max_stop_pct` cap is applied only to `mental_stop` inside `calculate_stop_price()`, but `calculated_candle_low` (raw, uncapped) is passed as `support_level` → `technical_stop` → `current_stop`, completely bypassing the cap.

### Bug Confirmation

The bypass path is confirmed:
```
calculate_stop_price() → mental_stop capped, calculated_candle_low NOT capped
    ↓
enter_position() → support_level = calculated_candle_low (uncapped)
    ↓
_create_new_position() → technical_stop = support_level - 5¢ (no cap)
    ↓
current_stop = technical_stop (bypasses 10% cap entirely)
```
