# Handoff: Backend Planner — Investigate Partial Exit Position Bug

## Problem Statement

Live ATOM trade on 2026-02-17: the bot entered 10 shares via `bull_flag`, then executed a "partial exit" that **sold all 10 shares**. However, the position **still shows as open with 10 shares**. The bot is now monitoring a phantom position.

## Verified Facts

### Fact 1: Position API still shows 10 shares after partial exit

**Verified with:** `curl -s 'http://localhost:8000/warrior/positions'`
**Output (key fields):**
```json
{
    "position_id": "8d5ee1c3-b08f-4a1a-8fa9-d86f5e35384d",
    "symbol": "ATOM",
    "shares": 10,
    "entry_price": 5.3,
    "current_stop": 5.3,
    "partial_taken": true
}
```
**Conclusion:** Position is still "open" with 10 shares despite partial exit selling 10.

---

### Fact 2: Partial exit sold ALL 10 shares (the entire position)

**Verified with:** `curl -s 'http://localhost:8000/data/trade-events?symbol=ATOM&limit=20'`
**Trade Events (position `8d5ee1c3`):**
```
12:20 PM - ENTRY: bull_flag, 10 shares @ $5.31
12:20 PM - FILL_CONFIRMED: 10 shares @ $5.30
12:31 PM - BREAKEVEN_SET: stop to breakeven after 2.1R
12:31 PM - PARTIAL_EXIT: 0.9R partial, 10 shares @ $5.41, P&L $1.10
12:31 PM - EXIT_FILL_CONFIRMED: $5.44 → $5.41, 10 shares confirmed
```
**Conclusion:** The partial sold 10 of 10 shares = 100% of position. This should either (a) not happen (partial should leave shares to "ride"), or (b) if it does sell all, should close the position.

---

### Fact 3: Risk was recently reduced to very small position sizes

Earlier this session, risk parameters were changed:
- `risk_per_trade`: $250 → $50
- `max_shares_per_trade`: 3,000 → 500
- `max_capital`: $5,000 → $1,000
- `max_positions`: 20 → 3

With $50 risk and stop at $5.14 (from entry metadata), position sizing = $50 / ($5.31 - $5.14) = ~294 shares. But max_shares caps at 500, and max_capital ($1,000) caps at ~188 shares. The final 10 shares suggests an additional constraint kicked in. At this small size, a "partial" of even 50% rounds to 5 shares — the partial selling ALL 10 means the calculation may not account for minimum remainder.

---

### Fact 4: There was a PREVIOUS ATOM trade that was exited via `candle_under_candle`

Position `2942f552` — earlier ATOM trade:
- Entry: 10 shares @ $4.75 (bull_flag)
- Exit: candle_under_candle @ $4.72, P&L -$0.60

**Conclusion:** The bot re-entered ATOM after a loss. This is relevant because the re-entry quality gate may not have blocked this (the first trade lost $0.60).

---

## Open Questions (For Planner Investigation)

### Q1: How does the partial exit calculate the number of shares to sell?
- **Starting point:** Look at `warrior_monitor_exit.py` for _partial_ or _base_hit_ or _partial_then_ride_ logic
- **Key question:** Is there a `math.ceil()` or rounding that causes small positions to sell 100%?
- **Key question:** Is there a minimum "remainder" check (e.g., don't partial if fewer than X shares would remain)?

### Q2: After a partial exit, what updates the position's share count?
- **Starting point:** After the partial sell order is placed, how does the position tracker learn that shares were sold?
- Does it rely on broker sync? On a callback? On the monitor loop?
- Is there a `position.shares -= shares_sold` anywhere?

### Q3: Why does the position remain "open" after selling all shares?
- **Starting point:** What triggers a position to be marked as "closed"?
- Is there a check like `if position.shares == 0: close_position()`?
- Or does it only close on full exit (stop hit, target hit, manual close)?

### Q4: Is this specific to the Partial-Then-Ride logic (Fix 1)?
- The trade events show `exit_mode: "base_hit"` — was the Partial-Then-Ride toggle enabled?
- Check `enable_partial_then_ride` in the current Warrior config on VPS
- Check `warrior_monitor_exit.py` for the partial-then-ride code path

### Q5: Does the broker (Alpaca) still hold ATOM shares?
- The position might be a phantom — bot thinks shares exist but broker sold them all
- If so, the next monitor cycle or sync should detect the discrepancy
- Check if there's a "position not found at broker" handling

## Output

Write findings to: `nexus2/reports/2026-02-17/planner_partial_exit_investigation.md`

Use the standard evidence format with file paths, line numbers, and code snippets for ALL findings.
