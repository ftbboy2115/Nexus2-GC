# Data Architecture: The Three-Layer Model

> Last updated: 2026-01-11

This document describes the foundational data architecture for position and trade management in Nexus 2.

## Overview

The system maintains three distinct layers of data to ensure reliability, auditability, and recovery:

| Layer | Table | Purpose | Mutability |
|-------|-------|---------|------------|
| **Active Positions** | `positions` | Current state of open holdings | Mutable |
| **Trade Management Log** | `trade_events` | Append-only audit trail | Immutable |
| **Trade Log** | (closed positions) | Historical archive | Immutable |

```
┌─────────────────────────────────────────────────────────────────┐
│                    TRADE MANAGEMENT LOG                         │
│                  (Immutable Event Stream)                       │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐            │
│  │ ENTRY   │→ │ ADD     │→ │ STOP    │→ │ PARTIAL │→ ...       │
│  │ +50@148 │  │ +50@152 │  │ MOVED   │  │ EXIT    │            │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                         (Derived)
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    ACTIVE POSITIONS                              │
│                   (Mutable Cache)                                │
│                                                                  │
│   AAPL: 75 shares @ $150.00 avg | Stop: $148.00 | Status: open  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Layer 1: Active Positions (`positions` table)

**Purpose:** Current state of open holdings — a high-performance cache of the "balance."

### Characteristics
- **Mutable**: Updated on every position event
- **Derived**: Can be fully reconstructed from the Trade Management Log
- **Fields**: `symbol`, `shares`, `avg_price`, `current_stop`, `status`, etc.

### Average Price Calculation
When scaling into a position (Warrior adds), the average price is **recalculated**:

```python
new_avg = (old_shares * old_avg + new_shares * fill_price) / total_shares

# Example:
# Entry: 50 shares @ $148.00
# Add:   50 shares @ $152.00
# Result: 100 shares @ $150.00 average
```

### Status Values
| Status | Meaning |
|--------|---------|
| `pending_fill` | Order submitted, awaiting fill |
| `open` | Position active |
| `scaling` | Add order pending (Warrior) |
| `partial` | Some shares exited |
| `closed` | Fully exited |
| `rejected` | Order rejected |

---

## Layer 2: Trade Management Log (`trade_events` table)

**Purpose:** Authoritative, append-only ledger of every incremental change.

### Characteristics
- **Strictly Immutable**: Events are never modified or deleted
- **Point-in-Time**: Records exact transaction values
- **Reconstructable**: The positions table can be derived from this log

### Event Types

| Event | Description | old_value | new_value |
|-------|-------------|-----------|-----------|
| `ENTRY` | Initial position open | — | `qty@price` |
| `ADD` | Scaling in (Warrior) | — | `qty@price` |
| `STOP_MOVED` | Stop adjustment | old stop | new stop |
| `BREAKEVEN` | Stop moved to entry | old stop | entry price |
| `PARTIAL_EXIT` | Partial scale out | — | `qty@price` |
| `FULL_EXIT` | Position closed | — | `qty@price` |

### Key Principle

> **The Trade Management Log never recalculates average price.**
> 
> Each event preserves the original transaction data. The `avg_price` in the positions table is merely a **derived view** of this ledger.

### Example Event Sequence

```
Event 1: ENTRY       | AAPL | +50 shares @ $148.00
Event 2: ADD         | AAPL | +50 shares @ $152.00
Event 3: STOP_MOVED  | AAPL | $145.00 → $148.00
Event 4: PARTIAL_EXIT| AAPL | -25 shares @ $155.00
Event 5: FULL_EXIT   | AAPL | -75 shares @ $160.00
```

After replaying:
- Total shares bought: 100
- Total shares sold: 100
- Weighted avg entry: $150.00
- Realized P&L: (25 × $5) + (75 × $10) = $875

---

## Layer 3: Trade Log (Historical Archive)

**Purpose:** Completed trades for long-term analytics and P&L reporting.

### Characteristics
- **Immutable** once position is closed
- **Captured** at the moment of `FULL_EXIT`
- **Summary**: Aggregated view for analytics dashboards

### Fields
- Entry date/price
- Exit date/price
- Total P&L (realized)
- Days held
- Setup type
- Scanner settings at entry (audit trail)

---

## Recovery & Reconstruction

The three-layer architecture enables robust recovery:

1. **Position State Recovery**: Replay all `trade_events` for a position to reconstruct current state
2. **Restart Resilience**: On app restart, positions can be validated against broker and TML
3. **Audit Trail**: Every management decision is preserved for post-trade analysis

```python
# Pseudocode: Reconstruct position from events
def reconstruct_position(position_id: str) -> Position:
    events = db.query(TradeEvent).filter(position_id=position_id).order_by(created_at)
    
    shares = 0
    total_cost = 0
    current_stop = None
    
    for event in events:
        if event.type == "ENTRY" or event.type == "ADD":
            qty, price = parse(event.new_value)
            shares += qty
            total_cost += qty * price
        elif event.type == "PARTIAL_EXIT" or event.type == "FULL_EXIT":
            qty, _ = parse(event.new_value)
            shares -= qty
        elif event.type == "STOP_MOVED":
            current_stop = event.new_value
    
    return Position(
        shares=shares,
        avg_price=total_cost / (shares if shares > 0 else 1),
        current_stop=current_stop
    )
```

---

## Strategy-Specific Behavior

### KK-Style (NAC) — Swing Trading
- **No scaling in**: Single entry, no `ADD` events
- **Stop moves**: LoD → Breakeven → Trailing MA
- **Partials**: Day 3-5 profit taking

### Warrior — Day Trading
- **Scaling in**: Multiple `ADD` events on pullbacks
- **Stop hierarchy**: Mental stop (15¢) → Technical (support)
- **Fast exits**: 2:1 R targets, character-based exits

---

## Related Documentation

- [Position State Machine](./position_state_machine.md) — State transitions and invariants
- [Order State Machine](../nexus2/domain/orders/state_machine.py) — Order lifecycle
- [Trade Event Service](../nexus2/db/models.py) — `TradeEventModel` schema
