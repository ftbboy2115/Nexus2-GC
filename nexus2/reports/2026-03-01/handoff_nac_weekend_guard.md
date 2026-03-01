# Handoff: NAC Weekend Scanning Guard

**Date:** 2026-03-01  
**From:** Coordinator  
**To:** Backend Specialist  
**Priority:** P0 — FMP API waste on weekends  
**Reference:** [research_nac_weekend_scanning.md](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-03-01/research_nac_weekend_scanning.md)

---

## Problem

NAC scanners (Breakout + HTF) ran on Sunday 2026-03-01, consuming FMP API calls on a non-market day. The `force_scan` endpoint has zero market-day guards for non-sim mode.

## Verified Facts

**Fact 1:** `scheduler.py:_run_loop()` (L194-263) has no fast weekday pre-check before calling `is_market_hours` (which hits Alpaca API).  
**Verified with:** `view_file scheduler.py L194-263` — confirmed the loop goes straight to `self.is_market_hours` at L201.

**Fact 2:** `scheduler_routes.py:force_scheduler_scan()` at L404-575 has NO market-day guard — docstring says "regardless of market hours."  
**Verified with:** `grep_search "force_scan"` + `view_file L404-440` — confirmed no weekday/market check before scan runs.

**Fact 3:** The `is_market_hours` property (L86-118) *does* correctly block weekends via Alpaca API + fallback, but the `force_scan` route bypasses this entirely.

**Fact 4:** `main.py` auto-resume at startup already checks `market_status.is_open` — **no changes needed there**.

**Fact 5:** Existing tests at `nexus2/tests/api/test_scheduler_routes.py` have a `TestForceScan` class (L169-179) but no weekend guard test.

---

## Changes Required

### 1. [MODIFY] [scheduler.py](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/scheduler.py)

**Location:** `_run_loop()` method, after L198 (`now = now_et()`) and before L201 (`if self.is_market_hours`)

**Add:** Fast weekday check that skips API call on weekends:

```python
# FAST CHECK: Skip weekends immediately (no API call needed)
if not self.sim_mode and now.weekday() >= 5:
    logger.info(f"[Scheduler] Weekend ({now.strftime('%A')}) - skipping scan cycle")
    await self._smart_wait_for_market_open(now)
    continue
```

> [!IMPORTANT]  
> Use `logger.info` not `logger.debug` — we want visibility when this fires on VPS.  
> Must check `not self.sim_mode` so sim testing isn't affected.

---

### 2. [MODIFY] [scheduler_routes.py](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/scheduler_routes.py)

**Location:** `force_scheduler_scan()`, after L448 (settings loaded) and before L449 (`logger.info(f"[ForceScan]...`)

**Add:** Market-day guard for non-sim mode:

```python
# Guard: Block force_scan on non-market days in non-sim mode (saves FMP API calls)
if not sim_mode:
    current_weekday = now_et().weekday()
    if current_weekday >= 5:
        logger.info(f"[ForceScan] Blocked on weekend ({now_et().strftime('%A')})")
        return {
            "status": "blocked",
            "reason": f"Market closed (weekend) - force scan skipped to avoid FMP API waste. Use sim_mode for testing.",
        }
```

> [!NOTE]  
> This only blocks weekends in non-sim mode. Sim mode force_scan remains unrestricted for testing.

---

### 3. [MODIFY] [test_scheduler_routes.py](file:///C:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/tests/api/test_scheduler_routes.py)

**Add a test** to `TestForceScan` class that mocks `now_et()` to return a Sunday and verifies `force_scan` returns `{"status": "blocked"}`.

---

## Verification Plan

### Automated

```powershell
cd "C:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus"
python -m pytest nexus2/tests/api/test_scheduler_routes.py -v
```

### Manual (VPS)

After deploying, on a weekend day:
1. `GET /automation/scheduler/status` → should show `is_market_hours: false`
2. `POST /automation/scheduler/force_scan` → should return `{"status": "blocked", "reason": "..."}`
3. Check logs for `[Scheduler] Weekend` entries — no FMP API calls should follow

---

## Open Questions (for specialist to investigate)

1. Should we also add a holiday check (not just weekends)? The Alpaca calendar handles holidays, but the fast weekday check only covers Sat/Sun.
2. Should the `force_scan` guard also check holidays via `get_market_calendar()`, or is weekend-only sufficient for now?
