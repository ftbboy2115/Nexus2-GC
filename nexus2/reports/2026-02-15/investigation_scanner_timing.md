# Scanner Timing Fix — Coordinator Handoff

**From**: Backend Planner  
**Date**: 2026-02-15  
**Priority**: CRITICAL — scanner is broken on VPS right now

---

## Verified Root Cause

> [!CAUTION]
> **`KeyError: 'name'`** crashes every scan cycle. The scanner has been silently failing.

**VPS Evidence** (server.log, last error):
```
07:34:52.474 | ERROR | nexus2.domain.automation.warrior_engine | [Warrior Scan] Error: 'name'
```

**Bug Location**: `nexus2/domain/scanner/warrior_scanner_service.py`, line 712

```python
# Line 708-713 — Chinese stock exclusion filter
if self.settings.exclude_chinese_stocks:
    filtered_movers = [
        g for g in filtered_movers
        if g["symbol"] not in CHINESE_STOCK_PATTERNS
        and not self._is_likely_chinese(g["name"])  # ← BUG: KeyError when Polygon/Alpaca mover has no "name"
    ]
```

**Verified with**: `view_file` on `warrior_scanner_service.py:706-714`

**Why it crashes**: The `filtered_movers` list merges data from 4 sources (Polygon, FMP gainers, FMP actives, Alpaca movers). Polygon and Alpaca entries may not include a `"name"` field. Direct dict access `g["name"]` raises `KeyError`, killing the entire `scan()` method. The error handler in `_scan_loop()` retries every 30 seconds but hits the same crash repeatedly.

**Why 9:28 AM**: The one successful scan wrote results to the DB at ~9:28 AM. After that, a new mover without `name` appeared, and all subsequent scans crashed.

---

## Agent Assignments

### Agent 1: Backend Specialist

**Rule file**: `@agent-backend-specialist.md`  
**Task**: Fix the KeyError bug + add scan resilience

#### Fix 1: KeyError Fix (CRITICAL, 1 line)

**File**: `nexus2/domain/scanner/warrior_scanner_service.py`  
**Line**: 712

```diff
-        and not self._is_likely_chinese(g["name"])
+        and not self._is_likely_chinese(g.get("name", ""))
```

#### Fix 2: Improved Error Logging in Scan Loop

**File**: `nexus2/domain/automation/warrior_engine.py`  
**Lines**: 406-409

Current code:
```python
except Exception as e:
    self.stats.last_error = str(e)
    logger.error(f"[Warrior Scan] Error: {e}")
    await asyncio.sleep(30)
```

Change to:
```python
except Exception as e:
    import traceback
    self.stats.last_error = str(e)
    logger.error(f"[Warrior Scan] Error: {e}\n{traceback.format_exc()}")
    await asyncio.sleep(30)
```

#### Fix 3: Scan Timeout (prevents future hangs)

**File**: `nexus2/domain/automation/warrior_engine.py`  
**Line**: 424

Current code:
```python
result = await asyncio.to_thread(self.scanner.scan, self.config.debug_catalyst)
```

Change to:
```python
try:
    result = await asyncio.wait_for(
        asyncio.to_thread(self.scanner.scan, self.config.debug_catalyst),
        timeout=120.0
    )
except asyncio.TimeoutError:
    logger.error("[Warrior Scan] TIMEOUT - scan exceeded 120s, skipping cycle")
    return
```

#### Fix 4: Audit other direct dict accesses on mover dicts

**File**: `nexus2/domain/scanner/warrior_scanner_service.py`

Search for other `g["name"]` or `mover["name"]` direct accesses in `scan()`. The safe pattern `mover.get("name", "")` is already used at line 752 — line 712 was missed.

---

### Agent 2: Testing Specialist

**Rule file**: `@agent-testing-specialist.md`  
**Task**: Verify fixes + add regression test

1. Run existing scanner tests: `python -m pytest nexus2/tests/unit/scanners/ -v`
2. Add a test case for a mover dict **without** a `name` field going through the Chinese stock filter
3. Verify the scan timeout doesn't break normal scan flow

---

## Verification Commands

```powershell
# Run tests locally
cd "c:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus"
python -m pytest nexus2/tests/unit/scanners/ -v

# After deploying to VPS, verify scanner is working
# (on VPS via SSH)
grep "\[Warrior Scan\]" data/server.log | tail -10
# Should see: "[Warrior Scan] Found X candidates, watching Y"
# Should NOT see: "[Warrior Scan] Error: 'name'"
```

---

## Secondary Findings (Not Blocking, Document Only)

| Finding | Evidence | Impact |
|---------|----------|--------|
| Scans fire every ~30s during error loop | warrior_scan.log: `04:00:15`, `04:00:46`, `04:01:16` | Excessive API calls during failures |
| warrior_scan.log timestamps are UTC, not ET | 04:00 entries when 11 PM ET | Cosmetic — makes log analysis confusing |
| No scan health monitoring exists | No alerting for "0 results in X minutes" | Silent failures go undetected |
