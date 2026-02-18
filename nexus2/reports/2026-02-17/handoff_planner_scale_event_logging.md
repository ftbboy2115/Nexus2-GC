# Handoff: Backend Planner — Investigate Missing Scale Events in Trade Events Tab

## Problem Statement

The Data Explorer's Trade Events tab does **not** show scale-in events. This led to significant confusion when investigating the ATOM trade today — events showed "10 shares entered, 10 shares partial exited" which looked like 100% of the position was sold. In reality, the bot had scaled from 10 to 20 shares (10 + 5 + 5), making the 10-share partial exit exactly correct (50%).

**The scale-in events were completely invisible** in both the Trade Events UI and the `/data/trade-events` API response. They only appeared in the Alpaca order history.

## Verified Facts

### Fact 1: The ATOM trade had TWO scale-ins that are invisible in Trade Events

**Alpaca order history** (from planner investigation):
```
12:20:13 - BUY 10 @ $5.30  (Initial entry)
12:20:37 - BUY 5 @ $5.32   (Scale-in #1) ← NOT in Trade Events
12:21:37 - BUY 5 @ $5.35   (Scale-in #2) ← NOT in Trade Events
12:31:07 - SELL 10 @ $5.44  (Partial exit)
12:53:04 - SELL 10 @ $5.605 (Topping tail)
```

### Fact 2: Trade Events API returned only 5 events for this position

**Verified with:** `curl -s 'http://localhost:8000/data/trade-events?symbol=ATOM&limit=20'`
**Events shown for position `8d5ee1c3`:**
```
ID 22966 - ENTRY (10 shares)
ID 22967 - FILL_CONFIRMED (10 shares)
ID 22968 - BREAKEVEN_SET
ID 22969 - PARTIAL_EXIT (10 shares)
ID 22970 - EXIT_FILL_CONFIRMED (10 shares)
```

**No SCALE events** between IDs 22967 and 22968. The gap is suspicious — if scale events were logged, they should appear with IDs 22968+ (but BREAKEVEN_SET took 22968).

### Fact 3: The dashboard Open Positions also didn't reflect scaled share count

The `/warrior/positions` API returned `"shares": 10` even though the bot had scaled to 20 shares. The Alpaca broker showed 20 shares at that time.

### Fact 4: The Warrior Dashboard page has the SAME visibility gap

The main Warrior page (not just Data Explorer) also failed to show scale events:
- **Open Positions panel**: Showed "Shares: 10" — never updated to 20 after scaling
- **Trade Events Log panel**: Showed ENTRY (10 shares), FILL_CONFIRMED, etc. but NO scale-in events
- This means the problem is in the **backend event logging**, not the frontend display — both the Warrior Dashboard and Data Explorer read from the same trade events source

---

## Open Questions (For Planner Investigation)

### Q1: Does the scaling code log trade events at all?
- **Starting point:** `warrior_monitor_scale.py` — find the `check_scale_opportunity` function
- **Key question:** After a successful scale-in, does it call `log_trade_event()` or equivalent?
- Check for any `SCALE`, `SCALE_IN`, or `ADD` event types

### Q2: What event types are defined in the system?
- **Starting point:** Check `trade_event_service.py` or wherever event types are defined
- Is there a `SCALE` or `SCALE_IN` event type? If not, that's the root cause.

### Q3: After scaling, does `position.shares` get updated?
- The Open Positions API showed 10 shares when the bot had scaled to 20
- Does `check_scale_opportunity` update `position.shares` after a scale?
- Or does it rely on broker sync to update the count?

### Q4: Does the scaling code create a new trade or update the existing one?
- When the bot scales in, does it:
  - Submit a new buy order via Alpaca?
  - Update the existing `WarriorPosition`'s shares count?
  - Log anything to the `warrior_trades` DB?

### Q5: Where do trade events get logged?
- Map the full event logging flow: which function logs events, what DB/table do they go to?
- Check if scale-related events are logged to a DIFFERENT location (e.g., `server.log` only, not DB)

### Q6: Is the position share count in the UI dashboard (Open Positions) also stale?
- The planner found that the `/warrior/positions` endpoint reads in-memory `position.shares`
- If scaling happens via broker but the in-memory position isn't updated, the UI always shows the original entry size
- This would also mean stop and P&L calculations are wrong (using wrong share count)

## Additional Context

The planner's full investigation is at: `nexus2/reports/2026-02-17/planner_partial_exit_investigation.md`

It confirmed:
- Bot correctly scaled from 10 → 15 → 20 shares via Alpaca orders
- Partial exit of `int(20 * 0.5) = 10` shares was mathematically correct
- The "bug" was entirely a **visibility/logging gap**, not a position management issue

The defensive fixes proposed in the planner's spec (minimum-remainder guard, zero-shares check) are still good hardening, but the IMMEDIATE user-facing problem is: **why can't I see scale events in the Data Explorer?**

## Output

Write findings to: `nexus2/reports/2026-02-17/planner_scale_event_logging_investigation.md`

Use the standard evidence format with file paths, line numbers, and code snippets for ALL findings.
