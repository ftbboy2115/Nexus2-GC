# Research: NAC Scanners Running on Weekends

**Date:** 2026-03-01 (Sunday)  
**Investigator:** Backend Planner  
**Issue:** Breakout Scanner and HTF Scanner making FMP API calls on Sunday (non-market day)

---

## Evidence

VPS logs on 2026-03-01 (Sunday):
- `"🔄 [Breakout Scanner] Processing 100/200 (50%)..."`
- `"[FMP] Rate limit approaching (49 remaining), waiting 5s..."`  
- `"🔄 [HTF Scanner] Processing 13/50 (25%)..."`

---

## Architecture: How NAC Scanning is Scheduled

```
main.py lifespan startup
  └─ Check market_status.is_open (L268)
  └─ If open + scheduler_running=true → resume_scheduler() (L289-302)
       └─ start_scheduler() → scheduler.start() → _run_loop()

AutomationScheduler._run_loop (scheduler.py:194-263)
  └─ Loop: check is_market_hours
       ├─ if True → _run_cycle() → scan_callback → unified_scanner.scan()
       └─ if False → _smart_wait_for_market_open() (1 hour cap on weekends)
```

### The `is_market_hours` guard (scheduler.py:86-118)

```python
@property
def is_market_hours(self) -> bool:
    # Real time: use Alpaca calendar
    try:
        calendar = get_market_calendar(paper=True)
        return calendar.is_market_open()  # Calls Alpaca /v2/clock API
    except Exception:
        # Fallback to basic time check
        now = now_et()
        weekday = now.weekday()
        if weekday >= 5:
            return False  # ← Correctly blocks weekends
        return self.market_open <= now.time() <= self.market_close
```

**This guard SHOULD prevent Sunday scanning.** Both the Alpaca API path and the fallback correctly return `False` on weekends.

---

## Root Cause Analysis

### The `_smart_wait_for_market_open` Problem (scheduler.py:265-337)

When `is_market_hours` returns `False`, the scheduler calls `_smart_wait_for_market_open()`:

```python
# Weekend handling (L278-293)
if weekday >= 5:
    sleep_seconds = min(3600, ...)  # Cap at 1 HOUR
    await asyncio.sleep(sleep_seconds)
    return
```

**The scheduler wakes up every 1 hour on weekends and re-checks `is_market_hours`.** This is correct — it should just keep sleeping.

### So Why Are Scans Running?

There are **two hypotheses**:

#### Hypothesis A: Alpaca API returning `is_open=true` on Sunday (unlikely)
If the Alpaca clock API returns `is_open: true` on a Sunday, the guard would pass. This is very unlikely but would explain the behavior.

#### Hypothesis B: The scan was triggered via `force_scan` API (more likely)
The `force_scan` endpoint at `scheduler_routes.py:404` **explicitly states:**

```python
"""Force an immediate scan cycle regardless of market hours."""
```

It has **NO market-day guard** at all. If something (cron job, monitoring script, or UI button press) hit `/automation/scheduler/force_scan`, it would run the full Breakout + HTF scan regardless of day.

#### Hypothesis C: Stale scheduler from Friday still running 
If the VPS didn't restart and the auto-shutdown at 4:02 PM failed on Friday, the scheduler loop would still be running. On Saturday/Sunday, the `is_market_hours` guard should block it — but if Alpaca API throws an error AND the fallback somehow fails, it could fall through.

---

## Comparison: Warrior Engine Market-Day Guard ✅ 

The Warrior engine has a **more robust** market-day guard at [warrior_engine.py:487-498](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine.py#L487-L498):

```python
# Skip on non-market days (weekends, holidays) and outside extended hours
if not self.config.sim_only:
    calendar = get_market_calendar(paper=True)
    if not calendar.is_extended_hours_active():
        status = calendar.get_market_status()
        reason = status.reason or "off_hours"
        logger.info(f"[Warrior Scan] Market closed ({reason})...")
        await asyncio.sleep(60)
        continue
```

Key differences from NAC:
1. Uses `is_extended_hours_active()` which has **explicit weekend check** (`weekday >= 5 → return False`)
2. Logs the reason clearly
3. Runs on a 1-minute re-check instead of 1-hour

---

## Files That Need Changes

### 1. [scheduler.py](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/scheduler.py) — **PRIMARY FIX**

**Location:** `_run_loop()` method (L194-263)

**Fix:** Add an explicit market-day check before the `is_market_hours` check, similar to Warrior's guard. The current code relies solely on `is_market_hours` → Alpaca API, but should have a fast weekday check first:

```python
# FAST CHECK: Skip weekends immediately (no API call needed)
if now.weekday() >= 5:
    logger.debug("Weekend - skipping scan cycle")
    await self._smart_wait_for_market_open(now)
    continue
```

### 2. [scheduler_routes.py](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/scheduler_routes.py) — **FORCE SCAN GUARD**

**Location:** `force_scheduler_scan()` (L404-575)

**Fix:** Add a market-day check to `force_scan` in NON-sim mode. Currently it says "regardless of market hours" — this is fine for sim mode, but for live mode on non-market days it wastes FMP API calls:

```python
# Guard: In non-sim mode, warn but still allow (manual testing use case)
# OR: block entirely on non-market days
if not sim_mode:
    calendar = get_market_calendar()
    status = calendar.get_market_status()
    if not status.is_open and status.reason in ("weekend", "holiday"):
        return {
            "status": "blocked",
            "reason": f"Market closed ({status.reason}) - scan skipped to avoid FMP API waste",
        }
```

### 3. [main.py](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/main.py) — **ALREADY GUARDED ✅**

The auto-resume at L268 already checks `market_status.is_open`:
```python
if not market_status.is_open:
    print(f"[Startup] NAC scheduler not resuming - market is closed (reason: {market_status.reason})")
```

This is correct — no changes needed here.

---

## Recommended Fix Priority

| Priority | File | Change | Effort |
|----------|------|--------|--------|
| **P0** | `scheduler.py` | Add fast weekday check in `_run_loop()` before `is_market_hours` | 5 min |
| **P1** | `scheduler_routes.py` | Add market-day guard to `force_scan` (non-sim mode) | 5 min |
| **P2** | `scheduler.py` | Log the reason when `is_market_hours` returns False (observability) | 2 min |

---

## Open Questions

1. **Was something hitting the `force_scan` API on Sunday?** Check VPS logs for `[ForceScan]` entries.
2. **Did the Friday auto-shutdown succeed?** Check VPS logs for `[AutoShutdown]` entries from Friday.
3. **Was the VPS restarted recently?** If `scheduler_running=true` in DB from Friday and VPS restarted Sunday, `main.py` should have blocked resume — but worth confirming with logs.

---

## Verification Plan

After implementing the fix:
1. Run `pytest` — all tests should pass
2. On VPS, check scheduler status: `GET /automation/scheduler/status` should show `is_market_hours: false` on weekends
3. Confirm FMP API calls stop on non-market days by checking `[FMP]` log entries
