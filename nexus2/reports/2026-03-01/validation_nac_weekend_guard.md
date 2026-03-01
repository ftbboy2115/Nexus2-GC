# Validation: NAC Weekend Scanning Research Claims

**Date:** 2026-03-01  
**Validator:** Audit Validator  
**Source Report:** [research_nac_weekend_scanning.md](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-03-01/research_nac_weekend_scanning.md)  
**Handoff:** [handoff_nac_weekend_guard.md](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-03-01/handoff_nac_weekend_guard.md)

---

## Claim Verification

### Claim 1: `_run_loop()` has no fast weekday pre-check

**Claim:** `scheduler.py:_run_loop()` (L194-263) goes straight to `self.is_market_hours` with no weekday check before it.  
**Verification:** `grep_search` for `weekday|weekend` in `scheduler.py` → **No results found.**  
Also viewed L194-263 via `view_file`. Line 201 goes straight to `if self.is_market_hours:` with zero weekday/weekend checks in `_run_loop()`.  
**Actual Code (L198-201):**
```python
now = now_et()
# Check if market hours (uses sim clock if sim_mode)
if self.is_market_hours:
```
**Result:** ✅ PASS  
**Notes:** The weekend check only exists deep inside `is_market_hours` → Alpaca fallback (L113-116), not as a fast pre-check in the loop itself.

---

### Claim 2: `force_scan` endpoint has NO market-day guard

**Claim:** `scheduler_routes.py:force_scheduler_scan()` at L404-575 has zero weekday/market-day checks.  
**Verification:** `grep_search` for `force_scan|weekday|weekend|market.*day` in `scheduler_routes.py` → **No results for weekday/weekend/market_day patterns.**  
Viewed L404-575 via `view_file`. The endpoint runs scans unconditionally — no calendar, no weekday, no market-hours check.  
**Actual Code (L404-418):**
```python
@router.post("/scheduler/force_scan", response_model=dict)
async def force_scheduler_scan(
    request: Request,
    engine: AutomationEngine = Depends(get_engine),
):
    """
    Force an immediate scan cycle regardless of market hours.
    
    This is useful for:
    - Simulation testing (when sim_clock is during market hours but real time isn't)
    - Manual testing outside market hours
    """
```
**Result:** ✅ PASS  
**Notes:** The docstring explicitly says "regardless of market hours" — this is intentional for sim/testing. However, this means a real `force_scan` call on Sunday will hit FMP with live API calls.

---

### Claim 3: `main.py` auto-resume is already guarded

**Claim:** The auto-resume logic in `main.py` at ~L268 checks `market_status.is_open` before resuming the scheduler.  
**Verification:** Viewed L257-306 via `view_file`.  
**Actual Code (L263-269):**
```python
try:
    # Check if market is actually open (NAC doesn't trade extended hours)
    calendar = get_market_calendar()
    market_status = calendar.get_market_status()
    
    if not market_status.is_open:
        print(f"[Startup] NAC scheduler not resuming - market is closed (reason: {market_status.reason})")
```
Additionally, L293-296 has a **second guard** after the 60s delay:
```python
# Re-check market is still open after delay
if not calendar.get_market_status().is_open:
    print("[Startup] NAC scheduler resume cancelled - market closed during delay")
    return
```
**Result:** ✅ PASS  
**Notes:** Auto-resume has a double guard — once before starting the 60s delay, and once after. This is robust.

---

### Claim 4: `is_market_hours` fallback correctly blocks weekends

**Claim:** `scheduler.py:is_market_hours` (L86-118) has a fallback that checks `weekday >= 5` and returns `False` on weekends.  
**Verification:** Viewed L86-118 via `view_file`.  
**Actual Code (L104-118):**
```python
# Real time: use Alpaca calendar
try:
    from nexus2.adapters.market_data.market_calendar import get_market_calendar
    calendar = get_market_calendar(paper=True)
    return calendar.is_market_open()
except Exception:
    # Fallback to basic time check
    now = now_et()
    current_time = now.time()
    weekday = now.weekday()
    
    if weekday >= 5:
        return False
    
    return self.market_open <= current_time <= self.market_close
```
**Result:** ✅ PASS  
**Notes:** The weekend check (L115-116) only runs on Alpaca API failure. If Alpaca is reachable and correctly reports Sunday as closed, the fallback never executes. The primary path delegates to `calendar.is_market_open()`.

---

### Claim 5: Warrior engine has a more robust guard pattern

**Claim:** `warrior_engine.py:487-498` uses `is_extended_hours_active()` with explicit weekend checks.  
**Verification:** Viewed L487-498 via `view_file`, then traced into `market_calendar.py:MarketCalendar.is_extended_hours_active()` at L273-328.  
**Actual Code (warrior_engine.py L487-498):**
```python
# Skip on non-market days (weekends, holidays) and outside extended hours
# BUT: bypass in sim_only mode for Mock Market testing anytime
if not self.config.sim_only:
    from nexus2.adapters.market_data.market_calendar import get_market_calendar
    calendar = get_market_calendar(paper=True)
    if not calendar.is_extended_hours_active():
        status = calendar.get_market_status()
        reason = status.reason or "off_hours"
        next_open = status.next_open.strftime('%Y-%m-%d %H:%M ET') if status.next_open else 'unknown'
        logger.info(f"[Warrior Scan] Market closed ({reason}) - next open: {next_open}")
        await asyncio.sleep(60)  # Check again in 1 minute
        continue
```
**`is_extended_hours_active()` (market_calendar.py L273-328) includes:**
```python
if weekday >= 5:
    return False
```
Plus holiday detection via `status.reason == "holiday"`.

**Result:** ✅ PASS  
**Notes:** The Warrior engine's guard is strictly more robust than the NAC scheduler's `is_market_hours`: it checks weekdays, holidays, and extended time windows. Same pattern also appears at L713-720 in `_watch_loop()`.

---

## Validation Report

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | `_run_loop()` no weekday pre-check | ✅ PASS | grep returned 0 hits; L201 goes to `is_market_hours` directly |
| 2 | `force_scan` no market-day guard | ✅ PASS | grep returned 0 hits; L404-575 has zero calendar checks |
| 3 | `main.py` auto-resume guarded | ✅ PASS | L268 checks `market_status.is_open`; L293-296 re-checks after delay |
| 4 | `is_market_hours` fallback blocks weekends | ✅ PASS | L115-116: `weekday >= 5 → False` (but only on Alpaca failure) |
| 5 | Warrior has robust guard pattern | ✅ PASS | L487-498 calls `is_extended_hours_active()` which has `weekday >= 5` + holiday checks |

### Overall Rating
- **HIGH**: All 5 claims verified. Research is accurate. Proceed to Backend Specialist for implementation.
