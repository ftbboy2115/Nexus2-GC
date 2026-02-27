# Handoff: Backend Specialist — L2 Minor Bug Fixes

## Task
Fix 2 minor bugs found during live L2 testing on VPS.

## Important: Search Path
Use `C:\Dev\Nexus` for search tools.

---

## Bug 1: Handler `await` TypeError

**Error from live test:**
```
TypeError: object NoneType can't be used in 'await' expression
```

**Location:** `schwab_l2_streamer.py` — the book handler callback
**Cause:** The handler tries to `await` the user-provided callback, but it may be a sync function (not async). 
**Fix:** Check if the callback is a coroutine function before awaiting:
```python
if asyncio.iscoroutinefunction(callback):
    await callback(snapshot)
else:
    callback(snapshot)
```

Also check the recorder's `record()` method — it's likely sync (uses `queue.Queue.put()`), so the handler shouldn't await it.

---

## Bug 2: Missing `get_status()` method

**Error from live test:**
```
AttributeError: 'SchwabL2Streamer' object has no attribute 'get_status'
```

**Fix:** Add a `get_status()` method to `SchwabL2Streamer`:
```python
def get_status(self) -> dict:
    return {
        "connected": self.is_connected,
        "subscribed_symbols": list(self._subscribed_symbols),
        "cached_books": list(self._books.keys()),
    }
```

---

## Verification
1. Run existing L2 tests: `.venv\Scripts\python -m pytest nexus2/tests/unit/market_data/ -v --timeout=30`
2. All 58 tests should still pass (41 Phase 1 + 17 Phase 2)
3. Deploy to VPS and restart: `ssh root@100.113.178.7 "cd ~/Nexus2 && git pull && systemctl restart nexus2"`
