# Backend Agent Handoff: Fix Missing SCALE_IN Events

## Task

Add SCALE_IN trade event logging and weighted-average entry price calculation to `execute_scale_in()` in `warrior_monitor_scale.py`. This is a **single-file, additive fix** following an existing pattern.

## Background

Scale-in events via the monitor loop are invisible in Trade Events. The function imports `trade_event_service` but never calls `log_warrior_scale_in()`. Entry price is also never recalculated after scaling, causing stale risk/target calculations.

## Investigation Report

Full evidence: `nexus2/reports/2026-02-17/planner_scale_event_logging_investigation.md`

---

## Verified Facts

### Fact 1: Root cause location
**File:** `nexus2/domain/automation/warrior_monitor_scale.py`
**Function:** `execute_scale_in()` (lines 163–333)
**Issue:** After updating `position.shares` at L282 and calling `complete_scaling()` at L286, no SCALE_IN event is logged and no weighted-average entry price is computed.

### Fact 2: Working template exists
**File:** `nexus2/domain/automation/warrior_monitor.py`
**Function:** `_consolidate_existing_position()` (lines 290–372)
**Pattern:** This function correctly does ALL of the following:
- Weighted avg entry price (L325-328)
- Updates `position.entry_price` (L332)
- Recalculates `risk_per_share` (L340)
- Recalculates `profit_target` with `profit_target_cents` vs `profit_target_r` branching (L343-346)
- Calls `trade_event_service.log_warrior_scale_in()` (L354-359)
- Passes `new_avg_price` to `complete_scaling()` (L364-368)

### Fact 3: `log_warrior_scale_in` signature
**File:** `nexus2/domain/automation/trade_event_service.py:786`
```python
def log_warrior_scale_in(
    self,
    position_id: str,
    symbol: str,
    add_price: Decimal,
    shares_added: int,
) -> Optional[int]:
```

### Fact 4: `complete_scaling` already accepts `new_avg_price`
**File:** `nexus2/db/warrior_db.py`
```python
def complete_scaling(trade_id: str, new_quantity: int, new_avg_price: float = None):
```

### Fact 5: Variables already in scope
At the insertion point (after L282), these variables exist:
- `position.position_id` — position ID
- `symbol` — symbol string (L195)
- `price` — Decimal scale price (L197: `Decimal(str(scale_signal["price"]))`)
- `add_shares` — int shares added (L196)
- `old_shares` — int original share count (L279)
- `old_entry` — Decimal original entry price (L280)
- `new_total_shares` — int new total shares (L283)
- `monitor.settings` — settings object with `profit_target_cents` and `profit_target_r`
- `trade_event_service` — already imported at L179

---

## Changes Required

All changes in **one file**: `nexus2/domain/automation/warrior_monitor_scale.py`

### Change 1: Add weighted-average entry price + risk/target recalc (after L283)

Insert after `new_total_shares = position.shares` (L283):

```python
        # Calculate weighted-average entry price (matches _consolidate_existing_position pattern)
        old_cost = old_entry * old_shares
        new_cost = price * add_shares
        new_avg_entry = (old_cost + new_cost) / new_total_shares
        
        # Update position entry price to weighted average
        position.entry_price = new_avg_entry
        
        # Recalculate risk and target based on new average entry
        risk_per_share = new_avg_entry - position.current_stop
        position.risk_per_share = risk_per_share
        
        s = monitor.settings
        if s.profit_target_cents > 0:
            position.profit_target = new_avg_entry + s.profit_target_cents / 100
        else:
            position.profit_target = new_avg_entry + (risk_per_share * Decimal(str(s.profit_target_r)))
```

### Change 2: Pass `new_avg_price` to `complete_scaling()` (L286)

Change:
```python
        complete_scaling(position.position_id, new_total_shares)
```
To:
```python
        complete_scaling(position.position_id, new_total_shares, new_avg_price=float(new_avg_entry))
```

### Change 3: Add SCALE_IN event logging (after `complete_scaling()`)

Insert after the `complete_scaling()` call:

```python
        # Log scale event (Trade Events tab visibility)
        trade_event_service.log_warrior_scale_in(
            position_id=position.position_id,
            symbol=symbol,
            add_price=price,
            shares_added=add_shares,
        )
```

### Change 4: Update trace log to show new weighted avg (L315)

Change:
```python
        f"entry_price was ${old_entry:.2f} (may change via consolidate), "
```
To:
```python
        f"entry_price ${old_entry:.2f} → ${position.entry_price:.2f} (weighted avg), "
```

---

## Verification

1. **Build check**: Confirm `uvicorn` reloads without errors
2. **Unit tests**: `pytest nexus2/tests/unit/automation/ -x -q` — confirm no regressions
3. **Sim test**: Run ATOM test case, query `/data/trade-events?symbol=ATOM&limit=30` — verify SCALE_IN events appear
4. **Share count check**: During sim, query `/warrior/positions` — verify `shares` reflects post-scale total

## Output

Write your status report to: `nexus2/reports/2026-02-17/status_scale_event_logging_fix.md`
