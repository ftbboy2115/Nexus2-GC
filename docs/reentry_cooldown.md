# Re-Entry Cooldown Logic

> **Created:** January 8, 2026  
> **Version:** v0.1.8 (pending)  
> **Status:** Implementing

---

## Problem Statement

On Jan 8, 2026, ACON was entered **6 times** in 3 hours, with each entry stopping out shortly after. The re-entry logic (designed to re-enter leaders after stop-outs) was working as intended, but on a stock that was in a clear downtrend.

**Result:** $145.50 in cumulative losses on a single symbol that never recovered.

---

## Design Decision

### The Hybrid Cooldown Rule

After a stop hit, block re-entry until **BOTH** conditions are met:

1. **Time Threshold:** 30 minutes since the stop hit
2. **Price Recovery:** Current price > entry price of the stopped trade

### Rationale

| Condition | Purpose |
|-----------|---------|
| **30 min wait** | Allows new consolidation/flag to form (per KK methodology) |
| **Price > stopped entry** | Confirms strength returned; avoids chasing weakness |

---

## Behavior Matrix

| Scenario | 30 min passed? | Price recovered? | Re-entry allowed? |
|----------|----------------|------------------|-------------------|
| Stock keeps falling | ✅ | ❌ | **No** |
| V-shaped reversal in 10 min | ❌ | ✅ | **No** |
| Slow recovery after 45 min | ✅ | ✅ | **Yes** |
| Sideways chop, never recovers | ✅ | ❌ | **No** |

---

## Data Model

The `recent_exits` tracker now stores:

```python
{
    "ACON": {
        "stopped_at": "2026-01-08T09:45:02Z",  # When stop hit
        "entry_price": 8.25,                   # Entry price of stopped trade
        "stop_price": 7.80,                    # Stop that was hit
    }
}
```

---

## Implementation Location

- **File:** `nexus2/api/routes/automation_state.py` (recent exits tracker)
- **File:** `nexus2/api/routes/execution_handler.py` (re-entry check)

---

## Re-Entry Check Pseudocode

```python
def can_reenter(symbol: str, current_price: float) -> bool:
    exit_info = get_recent_exit(symbol)
    if not exit_info:
        return True  # Never stopped out, allow entry
    
    stopped_at = exit_info["stopped_at"]
    entry_price = exit_info["entry_price"]
    
    # Check 1: Time cooldown (30 min)
    if (now - stopped_at) < timedelta(minutes=30):
        log(f"Cooldown active for {symbol} ({minutes_remaining} min left)")
        return False
    
    # Check 2: Price recovery
    if current_price < entry_price:
        log(f"Price {current_price} < stopped entry {entry_price}, blocking")
        return False
    
    # Both conditions met - allow re-entry
    clear_recent_exit(symbol)
    return True
```

---

## KK Methodology Alignment

From `qullamaggie_strategy_guide.md`:

> "Re-entering on subsequent flags is treated as a **new, independent trade** rather than 'adding' to a single massive position."

This cooldown ensures:
1. Sufficient time for a **new pattern** to form (flag, consolidation)
2. **Price confirmation** that the stock has regained strength
3. Prevents **chasing** a failing stock

---

## ACON Case Study (Jan 8, 2026)

With this logic in place, trades 4-6 would have been blocked:

| Trade | Stopped Entry | Would Price Recover? | Blocked? |
|-------|---------------|---------------------|----------|
| #4 | $8.25 | ❌ Never | **Yes** |
| #5 | $7.76 | ❌ Never | **Yes** |
| #6 | $7.73 | TBD (current) | - |

**Estimated savings:** $71.62

---

## Configuration

Currently hardcoded:
- `REENTRY_COOLDOWN_MINUTES = 30`

Future enhancement: Make configurable via scheduler settings.

---

## Related Documentation

- [Qullamaggie Strategy Guide](./strategies/qullamaggie/qullamaggie_strategy_guide.md)
- [Automation System Logic](./automation/implementation/system_logic.md)
