# Trade Decision Logging — Gap Analysis & Implementation Plan

## Problem Statement

The Warrior bot currently has **no queryable persistence for rejected trade decisions**. When the bot chooses NOT to enter a trade, the rejection reason is:

- Written to a TML flat file (`log_warrior_guard_block` at [trade_event_service.py:976](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/trade_event_service.py#L976-L998))
- Logged via `logger.info` / `logger.warning` — ephemeral, not queryable

This means we **cannot systematically analyze why trades were NOT taken**, which is critical for understanding profitability gaps between the bot and Ross Cameron's actual trades.

---

## Current State Summary

| Decision Point | Where | Persisted? | Queryable? |
|---|---|---|---|
| Guard blocks (MACD, blacklist, spread, cooldown, etc.) | `warrior_entry_guards.py` | TML file only | ❌ |
| Pattern competition losers (score too low) | `warrior_engine_entry.py` | `logger.info` only | ❌ |
| Technical validation failures (VWAP/EMA) | `warrior_entry_guards.py` | `logger.warning` only | ❌ |
| Successful entries | `warrior_db.py` + `trade_event_service.py` | DB (SQLite) | ✅ |
| Trade management events (stops, partials, exits) | `trade_event_service.py` | DB (SQLite) | ✅ |
| Entry validation audit | `warrior_db.py` (`EntryValidationLogModel`) | DB (SQLite) | ✅ |

### Guard Block Categories (from [warrior_entry_guards.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py))

| Guard | Line | Already calls `tml.log_warrior_guard_block()`? |
|---|---|---|
| `top_x_picks` | 64-81 | ✅ Yes |
| `min_score` | 84-87 | ✅ Yes |
| `blacklist` | 90-92 | ✅ Yes |
| `fail_limit` | 95-99 | ✅ Yes |
| `macd` | 103-106 | ✅ Yes |
| `position` | 109-112 | ✅ Yes |
| `pending_entry` | 115-117 | ✅ Yes |
| `live_cooldown` | 120-125 | ❌ No (logger only) |
| `sim_cooldown` | 128-137 | ✅ Yes |
| `reentry_loss` | 141-154 | ✅ Yes |
| `spread` | 159-164 | ✅ Yes |
| `validate_technicals` (VWAP/EMA) | Called from `enter_position` | ❌ Not in guards flow |

---

## User Review Required

> [!IMPORTANT]
> **Scope Decision**: There are two possible approaches, from lightweight to comprehensive. Please choose which direction you'd like.

### Option A: Lightweight — Promote Guard Blocks to DB (Recommended)

**What changes**: Modify `log_warrior_guard_block()` to write to the `trade_events` table (same as other events) instead of TML-file-only. Add a new event type `WARRIOR_GUARD_BLOCK`.

**Pros**:
- Minimal code change (~20 lines)
- All 10+ guard categories immediately become queryable via the existing Data Explorer Trade Events tab
- No new tables, no schema migration
- Batch runner results can include rejection counts

**Cons**:
- Guard blocks fire frequently — could add noise to the events table
- No separate UI/filtering yet (but Data Explorer can filter by event_type)

### Option B: Comprehensive — New `TradeDecisionLog` Table + Batch Integration

**What changes**: Create a new `TradeDecisionLogModel` in `warrior_db.py` with specific columns for rejection analysis (symbol, guard_name, reason, trigger_type, price, sim_time, case_id). Wire it into the batch runner so each concurrent case collects its rejection data and returns it in the result dict.

**Pros**:
- Clean separation from trade events (no noise)
- Can track per-case rejection counts in batch results
- Enables dedicated analysis queries (e.g., "which guard blocks the most?")

**Cons**:
- More code (new model, new service calls, schema migration)
- Requires updating `_run_single_case_async` result format
- Requires frontend work to display

---

## Proposed Changes (Option A — Recommended)

### Trade Event Service

#### [MODIFY] [trade_event_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/trade_event_service.py)

- Change `log_warrior_guard_block()` (line 976) from TML-file-only to **also write to DB** via `_log_event()`
- Add `WARRIOR_GUARD_BLOCK = "WARRIOR_GUARD_BLOCK"` to the event type constants
- Use `position_id="GUARD_BLOCK"` (no real position for rejected trades)
- Include guard_name, trigger_type, and price in metadata

```diff
     def log_warrior_guard_block(
         self,
         symbol: str,
         guard_name: str,
         reason: str,
         trigger_type: str = "unknown",
         price: float = None,
     ) -> None:
-        """
-        Log when an entry guard blocks a trade attempt.
-        
-        This is TML file-only (no DB write) to avoid noise in the events table.
-        Guard blocks happen frequently and are primarily for forensic review.
-        """
+        """Log when an entry guard blocks a trade attempt to DB + TML file."""
         price_str = f"${price:.2f}" if price else "N/A"
         details = f"guard={guard_name} | trigger={trigger_type} | price={price_str} | {reason}"
         
         self._log_to_file(
             strategy="WARRIOR",
             symbol=symbol,
             event_type=self.WARRIOR_GUARD_BLOCK,
             details=details,
         )
+        
+        self._log_event(
+            strategy="WARRIOR",
+            position_id="GUARD_BLOCK",
+            symbol=symbol,
+            event_type=self.WARRIOR_GUARD_BLOCK,
+            new_value=guard_name,
+            reason=reason,
+            metadata={
+                "guard_name": guard_name,
+                "trigger_type": trigger_type,
+                "price": price,
+            },
+        )
```

---

### Missing Guard Block Coverage

#### [MODIFY] [warrior_entry_guards.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py)

- Add `tml.log_warrior_guard_block()` call for the **live cooldown** path (line 120-125) which currently only logs to logger

---

### Batch Runner — Rejection Count in Results

#### [MODIFY] [sim_context.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/simulation/sim_context.py)

- In `_run_single_case_async()`, after stepping through the day, query the in-memory DB for `WARRIOR_GUARD_BLOCK` events and include a `guard_blocks` count + summary in the result dict
- This gives batch results visibility into rejection reasons per case

---

## Verification Plan

### Automated Tests

**Run existing test suite** to confirm no regressions:
```powershell
cd "c:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus"
python -m pytest nexus2/tests/ -x -q
```

**Run single batch test case** to verify guard blocks appear in results:
```powershell
python -c "import requests; r=requests.post('http://localhost:8000/warrior/sim/run_batch_concurrent', json={'case_ids': ['ross_batl_20260126']}); print(r.json())"
```

> [!NOTE]
> `ross_batl_20260126` is a good test — BATL never had a viable PMH breakout, so the bot should generate guard blocks but no entry. This validates that rejections are now captured.

### Manual Verification

1. After implementation, run the batch test above
2. Check the Data Explorer → Trade Events tab for `WARRIOR_GUARD_BLOCK` events
3. Verify the events show the guard_name, trigger_type, and price in metadata

> [!TIP]
> Clay — do you have a preferred way to verify the Trade Events data in the Data Explorer? I can adapt the verification to match your usual workflow.
