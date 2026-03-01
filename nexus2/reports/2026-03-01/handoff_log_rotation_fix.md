# Handoff: Fix Log Rotation FileNotFoundError in Child Processes

**Assigned to:** Backend Specialist  
**Priority:** Low (non-blocking, cosmetic noise)  
**Date:** 2026-03-01

## Problem

The batch runner (`ProcessPoolExecutor` in `sim_context.py`) spawns child processes that inherit the root logger config from `main.py`. When multiple processes independently try to rotate `data/server.log`, the `doRollover()` method calls `os.remove("server.log.3")` — but the file may not exist (e.g., first rotation cycle, or another process already removed it). This raises:

```
FileNotFoundError: [WinError 2] The system cannot find the file specified: "data\server.log.3"
```

The error is **non-blocking** — batch tests complete fine — but it's noisy in the logs.

## Verified Facts

### Fact 1: `SafeRotatingFileHandler` only catches `PermissionError`

**File:** `nexus2/api/main.py:45-58`  
**Code:**
```python
class SafeRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler that survives Windows PermissionError during rotation."""
    def doRollover(self):
        try:
            super().doRollover()
        except PermissionError:
            pass  # Another process has the file — skip rotation, retry later
```

The handler was created to handle the `PermissionError` case but **does not catch `FileNotFoundError`**, which is the error being reported.

### Fact 2: Child processes use `spawn` context

**File:** `nexus2/adapters/simulation/sim_context.py:977-982`  
**Code:**
```python
from concurrent.futures import ProcessPoolExecutor
...
with ProcessPoolExecutor(max_workers=max_workers, mp_context=multiprocessing.get_context("spawn")) as pool:
```

The `spawn` context means child processes re-import `main.py` module-level code, which registers the `SafeRotatingFileHandler` on the root logger in each child process.

## Recommended Fix

Extend the `except` clause in `SafeRotatingFileHandler.doRollover()` to also catch `FileNotFoundError`:

```diff
class SafeRotatingFileHandler(RotatingFileHandler):
-    """RotatingFileHandler that survives Windows PermissionError during rotation."""
+    """RotatingFileHandler that survives Windows file errors during rotation.
+    
+    When ProcessPoolExecutor spawns sim workers, each process gets its own
+    RotatingFileHandler pointing at the same server.log. Rotation can fail with:
+    - PermissionError: another process has the file open (os.rename fails)
+    - FileNotFoundError: backup file doesn't exist yet (os.remove fails)
+    This handler catches both — the log message stays in the current file
+    and rotation retries naturally on the next size check.
+    """
     def doRollover(self):
         try:
             super().doRollover()
-        except PermissionError:
-            pass  # Another process has the file — skip rotation, retry later
+        except (PermissionError, FileNotFoundError):
+            pass  # Another process has the file or backup doesn't exist — skip rotation
```

This is a one-line fix (plus docstring update). Using `OSError` would also work but is broader than needed.

## Open Questions

None — this is straightforward.

## Verification

1. Run `pytest` — all tests should still pass (no test exercises this handler directly)
2. Run a batch test (`POST /warrior/batch-test`) — the `FileNotFoundError` should no longer appear in logs
