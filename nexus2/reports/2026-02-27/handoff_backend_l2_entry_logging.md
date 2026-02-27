# Handoff: Backend Specialist — L2 Entry Logging

## Task
Add `get_book_summary()` logging alongside every entry decision so we can correlate L2 conditions with trade outcomes. **This is LOGGING ONLY — do NOT use L2 data to block or affect entries.**

## Important: Search Path
Use `C:\Dev\Nexus` for search tools.

## Dependencies
- `nexus2/domain/market_data/l2_signals.py` — `get_book_summary()`, `L2Summary`  
- `nexus2/adapters/market_data/schwab_l2_streamer.py` — `get_snapshot(symbol)`
- The engine has `self._l2_streamer` (may be `None` if L2 disabled)

---

## What to Do

### Step 1: Find the entry decision point
The entry decision happens in `nexus2/domain/automation/warrior_engine_entry.py` around line 1328 (look for `"source": "entry_decision"`). There may also be an entry execution step in `warrior_entry_execution.py` around line 530.

**Investigate both files** to find the exact log line where an entry order is about to be submitted.

### Step 2: Add L2 snapshot logging at that point
Right before or after the entry log line, add something like:

```python
# L2 book context (logging only, does not affect entry decision)
if self._l2_streamer:
    from nexus2.domain.market_data.l2_signals import get_book_summary
    snapshot = self._l2_streamer.get_snapshot(symbol)
    if snapshot:
        summary = get_book_summary(snapshot)
        logger.info(f"[L2 Context] {symbol}: spread={summary.spread_quality.spread_bps:.1f}bps "
                    f"({summary.spread_quality.quality}), "
                    f"bid_wall={'$'+str(summary.bid_wall.price)+'x'+str(summary.bid_wall.volume) if summary.bid_wall else 'none'}, "
                    f"ask_wall={'$'+str(summary.ask_wall.price)+'x'+str(summary.ask_wall.volume) if summary.ask_wall else 'none'}, "
                    f"thin_ask={'yes' if summary.thin_ask else 'no'}, "
                    f"imbalance={summary.spread_quality.imbalance:+.2f}")
```

### Step 3: Access to `_l2_streamer`
The entry logic may not have direct access to `self._l2_streamer` — it depends on how the engine passes context. Options:
1. If entry logic has access to the engine instance → use `engine._l2_streamer`
2. If not → add `l2_streamer` to whatever context object is passed to entry functions
3. Alternatively, pass the snapshot as part of the candidate/watchlist data

**Investigate how the entry function receives its context** before implementing. Don't force-couple things.

---

## Constraints
- **LOGGING ONLY** — L2 MUST NOT affect entry decisions
- Guard everything behind `if self._l2_streamer:` — must work when L2 is disabled
- Use lazy import for `get_book_summary` inside the if block
- One clean log line per entry, not separate lines for each signal
- Don't modify entry logic flow at all

## Testable Claims
1. Entry decision logging works with `L2_ENABLED=false` (no change in behavior)
2. When L2 enabled, an `[L2 Context]` log line appears alongside entry decisions
3. The L2 log includes: spread_bps, quality, bid_wall, ask_wall, thin_ask, imbalance
4. No existing tests broken
