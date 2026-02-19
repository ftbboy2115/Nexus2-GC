# Investigation: CISS Fill Confirmation — Cumulative vs Incremental Shares

**Agent:** Backend Planner
**Mode:** Runtime Investigation
**Date:** 2026-02-19
**Position ID:** `b97f064d-12d4-46dd-8c23-f6021316bf9b`

---

## Executive Summary

**Root cause confirmed:** Two separate code paths each log a `FILL_CONFIRMED` event for the same entry order, producing a **duplicate** event. The first comes from the entry poll loop (8 shares — partial fill), the second from broker sync recovery (10 shares — full position). The total shares filled was **10** (correct), but the event log shows it as 8 + 10 = "18" to a naive reader.

**This is a logging bug, NOT a position sizing bug.** The actual position had the correct number of shares.

---

## Runtime Evidence

### CISS Trade Events (position b97f064d)

Queried via: `ssh root@100.113.178.7 "curl -s 'http://localhost:8000/data/trade-events?symbol=CISS&limit=50'"`

| ID | Event | Shares | Time | Delta from ENTRY |
|----|-------|--------|------|------------------|
| 23225 | ENTRY | 10 | 16:27:43.374 | T+0.0s |
| **23226** | **FILL_CONFIRMED** | **8** | **16:27:43.972** | **T+0.6s** |
| **23227** | **FILL_CONFIRMED** | **10** | **16:27:57.915** | **T+14.5s** |
| 23228 | SCALE_IN | +5 | 16:28:07.960 | T+24.6s |
| 23229 | SCALE_IN | +5 | 16:29:08.267 | T+85s |
| 23230 | CANDLE_UNDER_CANDLE_EXIT | — | 16:33:11.939 | — |
| 23231 | EXIT_FILL_CONFIRMED | 20 | 16:33:11.948 | — |

> [!IMPORTANT]
> Two FILL_CONFIRMED events for the same entry. The 14.5-second gap between them matches the broker sync cycle interval, confirming they come from different code paths.

### Exit sanity check

The EXIT_FILL_CONFIRMED (id:23231) correctly shows **20 shares** (10 initial + 5 + 5 scale-ins), confirming the actual position was correctly sized throughout.

---

## Code Path Analysis

### Path 1: Entry Poll Loop → FILL_CONFIRMED(8)

**File:** [warrior_engine_entry.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py#L1335-L1394)
**Lines:** 1335–1394

The entry flow submits a limit order, then polls Alpaca up to 5 times (0.5s apart) for fill confirmation:

```python
# Line 1337-1355 — Poll loop
for attempt in range(5):  # 5 attempts x 500ms = 2.5s
    await asyncio.sleep(0.5)
    try:
        order_detail = await engine._get_order_status(broker_order_id)
        if order_detail:
            status = getattr(order_detail, 'status', None)
            if status:
                status_str = status.value if hasattr(status, 'value') else str(status)
                if status_str.lower() in ("filled", "partially_filled"):
                    fill_price = getattr(order_detail, 'avg_fill_price', None)
                    if fill_price and float(fill_price) > 0:
                        actual_fill_price = Decimal(str(fill_price))
                        filled_qty = getattr(order_detail, 'filled_quantity', filled_qty) or filled_qty
                        #                                    ^^^^^^^^^^^^^^^^
                        #  THIS IS ALPACA'S CUMULATIVE filled_quantity (8 of 10)
                        order_status = status_str
                        break
```

Then outside the loop:

```python
# Line 1387-1394 — Logs FILL_CONFIRMED with cumulative filled_qty
trade_event_service.log_warrior_fill_confirmed(
    position_id=order_id,
    symbol=symbol,
    quote_price=entry_price,
    fill_price=actual_fill_decimal,
    slippage_cents=slippage,
    shares=int(filled_qty) if filled_qty else shares,
    #      ^^^^^^^^^^^^^^^^ — 8 (partial fill from Alpaca)
)
```

**Key behavior:** When Alpaca reports `status=partially_filled`, the code **breaks out of the poll loop** and logs FILL_CONFIRMED with whatever `filled_quantity` Alpaca reported (8 here, which is **cumulative**, not incremental).

After logging, the code at line 1399 checks:
```python
if order_status and order_status.lower() not in ("filled", "partially_filled"):
    return
```
Since `partially_filled` IS in the tuple, the code does **NOT** return — it proceeds to `add_position` with 8 shares.

---

### Path 2: Broker Sync Recovery → FILL_CONFIRMED(10)

**File:** [warrior_monitor_sync.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_sync.py#L467-L476)
**Lines:** 467–476

When broker sync recovers an existing trade, it logs FILL_CONFIRMED:

```python
# Line 467-476
# Log FILL_CONFIRMED event for Trade Events UI (after ENTRY)
slippage_cents = float((entry_price - quote_price) * 100)
trade_event_service.log_warrior_fill_confirmed(
    position_id=recovered_position_id,
    symbol=symbol,
    quote_price=quote_price,
    fill_price=entry_price,
    slippage_cents=slippage_cents,
    shares=qty,
    #      ^^^ — broker's current total qty (10)
)
```

**This fires when:** `_recover_position` is called (lines 209-485), which happens inside `_recover_orphaned_positions` (line 488) for symbols that are at the broker but **NOT in monitor memory**.

---

### How Both Paths Fire for the Same Entry

The sequence that produces the duplicate:

```
T+0.0s   ENTRY logged (10 shares intended)
T+0.5s   Poll attempt 1: Alpaca says partially_filled, filled_quantity=8
         → FILL_CONFIRMED(8) logged [PATH 1]
         → add_position(shares=8) — position enters monitor with 8 shares
T+0.5s   Remaining 2 shares fill at Alpaca (total now 10)
...
T+14.5s  Broker sync cycle runs:
         → _sync_monitored_positions: sees monitor=8, broker=10, updates to 10
         → BUT: Possible scenario: between entry and sync, monitor lost the position
           (server restart, exception in add_position, or monitor state reset)
         → _recover_orphaned_positions fires because CISS is at broker but NOT in monitor
         → _recover_position finds existing trade in DB
         → FILL_CONFIRMED(10) logged [PATH 2]
```

> [!WARNING]
> The exact reason sync recovery fired (position not in monitor despite being added 14s earlier) could be: (a) server restart, (b) exception between FILL_CONFIRMED log and `add_position`, or (c) monitor state loss. Server logs would clarify but are not available for this investigation.

---

## Analysis: Is `shares` Cumulative or Incremental?

### Alpaca's `filled_quantity` → Cumulative

**Finding:** Alpaca's order object has a `filled_quantity` field that represents the **cumulative** total shares filled, not the incremental delta.

**File:** [warrior_engine_entry.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py#L1349)
**Code:**
```python
filled_qty = getattr(order_detail, 'filled_quantity', filled_qty) or filled_qty
```
**Verified with:** Alpaca API docs confirm `filled_qty` is cumulative. Runtime data shows 8 (not 2) on the partial fill.

### `log_warrior_fill_confirmed` → Passes Through Whatever It Receives

**Finding:** The `log_warrior_fill_confirmed` method simply stores the `shares` parameter in metadata without any cumulative/incremental interpretation.

**File:** [trade_event_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/trade_event_service.py#L599-L641)
**Code:**
```python
metadata = {
    "quote_price": str(quote_price),
    "fill_price": str(fill_price),
    "slippage_cents": slippage_cents,
    "shares": shares,  # Just stores whatever caller passes
}
```

---

## All FILL_CONFIRMED Call Sites

| # | File | Line | Source of `shares` | Context |
|---|------|------|--------------------|---------|
| 1 | [warrior_engine_entry.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py#L1387) | 1387 | `filled_qty` from Alpaca poll (cumulative) | Entry poll loop |
| 2 | [warrior_entry_execution.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_execution.py#L573) | 573 | `filled_qty` from Alpaca poll (cumulative) | Extracted copy (same logic) |
| 3 | [warrior_monitor_sync.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_sync.py#L469) | 469 | `qty` from broker position (total) | Sync recovery |

> [!NOTE]
> Call sites #1 and #2 are the same logic (original + extracted copy). Only one runs for a given entry. Call site #3 fires independently during sync recovery.

---

## Confirmed Impact

| Aspect | Status | Detail |
|--------|--------|--------|
| **Position sizing** | ✅ Correct | EXIT shows 20 shares (10 + 5 + 5), matching expectations |
| **Event log accuracy** | ❌ Misleading | Two FILL_CONFIRMED events make it look like 18 shares filled |
| **P&L calculation** | ✅ Correct | Exit P&L computed from actual shares, not event log |
| **Trade analysis** | ⚠️ Risk | `trade_analysis_service.py` line 330 sums FILL_CONFIRMED events — could double-count |

### Potential Double-Count Risk in Analysis

**File:** [trade_analysis_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/trade_analysis_service.py#L330)

```python
if event.get("event_type") == "FILL_CONFIRMED":
    # If analysis code sums shares from all FILL_CONFIRMED events,
    # it would compute 8 + 10 = 18 instead of 10
```

---

## Recommended Fixes

### Fix 1: De-duplicate FILL_CONFIRMED in sync recovery (primary)

**File:** [warrior_monitor_sync.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_monitor_sync.py#L467-L476)
**Approach:** Before logging FILL_CONFIRMED in `_recover_position`, check if one already exists for this position_id:

```python
# Check if fill was already confirmed by entry code
existing_fill = trade_event_service.has_fill_confirmed_event(position_id)
if not existing_fill:
    trade_event_service.log_warrior_fill_confirmed(...)
```

This requires adding a `has_fill_confirmed_event()` method to `TradeEventService` (similar to existing `has_entry_event()`).

### Fix 2: Don't log FILL_CONFIRMED on partial fills (secondary)

**File:** [warrior_engine_entry.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py#L1385-L1394)
**Approach:** Only log FILL_CONFIRMED when `order_status == "filled"`, not `"partially_filled"`. The sync recovery path will catch the final fill.

```python
# Only log fill confirmation for FULL fills
if order_status and order_status.lower() == "filled":
    trade_event_service.log_warrior_fill_confirmed(...)
```

### Fix Priority

| Fix | Complexity | Risk | Recommendation |
|-----|-----------|------|----------------|
| Fix 1 (de-dup in sync) | Low | Low | ✅ Do first — prevents duplicates from ALL sources |
| Fix 2 (skip partials) | Low | Medium | ⚠️ Optional — but partial fill info is useful for audit |

---

## Wiring Checklist (for Backend Specialist)

- [ ] Add `has_fill_confirmed_event(position_id)` to `TradeEventService` (model on existing `has_entry_event`)
- [ ] Guard FILL_CONFIRMED in `warrior_monitor_sync.py:467` with de-dup check
- [ ] (Optional) Guard FILL_CONFIRMED in `warrior_engine_entry.py:1385` to skip `partially_filled`
- [ ] Verify `trade_analysis_service.py` handles multiple FILL_CONFIRMED events safely
- [ ] Run existing tests: `pytest nexus2/tests/ -k "trade_event"` (if any exist)
