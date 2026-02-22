# Validation Report: Trigger Rejection Logging

**Date:** 2026-02-22
**Validator:** Audit Validator
**Claims Report:** `nexus2/reports/2026-02-21/backend_status_trigger_rejection_logging.md`
**Handoff:** `nexus2/reports/2026-02-22/handoff_audit_validator_trigger_rejection.md`

---

## Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | `WARRIOR_TRIGGER_REJECTION = "TRIGGER_REJECTION"` at line 79 | **PASS** (minor line drift) | Actual line 80, code correct |
| 2 | `_trigger_rejection_dedup` dict in `__init__` at line 88 | **PASS** (minor line drift) | Actual line 92, code correct |
| 3 | `log_warrior_trigger_rejection()` with 30s dedup at lines 1028-1091 | **PASS** | Actual lines 1037-1096, logic correct |
| 4 | Below-score call site at ~line 619 in `warrior_engine_entry.py` | **PASS** | Actual line 634, code correct |
| 5 | Micro-pullback skip logging with throttle at ~line 422 | **PASS** | Actual line 423, code correct |
| 6 | Full test suite passes (757 passed, 0 failures) | **PASS** | 757 passed, 4 skipped, 3 deselected in 175.04s |

---

## Detailed Evidence

### Claim 1: WARRIOR_TRIGGER_REJECTION constant

**Claim:** `WARRIOR_TRIGGER_REJECTION = "TRIGGER_REJECTION"` exists at `trade_event_service.py:79`
**Verification Command:**
```powershell
Select-String -Path "nexus2\domain\automation\trade_event_service.py" -Pattern "TRIGGER_REJECTION"
```
**Actual Output:**
```
trade_event_service.py:80:    WARRIOR_TRIGGER_REJECTION = "TRIGGER_REJECTION"  # Pattern scored but below threshold
```
**Result:** PASS
**Notes:** Line 80 not 79 (off by 1). Code is exactly as claimed. Constant is correctly positioned between `WARRIOR_GUARD_BLOCK` (line 79) and `WARRIOR_REENTRY_ENABLED` (line 81), confirming the handoff's ordering requirement.

---

### Claim 2: Dedup dict initialized in `__init__`

**Claim:** `_trigger_rejection_dedup` dict initialized in `__init__` at line 88
**Verification Command:**
```powershell
Select-String -Path "nexus2\domain\automation\trade_event_service.py" -Pattern "_trigger_rejection_dedup"
```
**Actual Output:**
```
trade_event_service.py:92:        self._trigger_rejection_dedup: Dict[str, float] = {}
trade_event_service.py:1058:        last_ts = self._trigger_rejection_dedup.get(dedup_key, 0)
trade_event_service.py:1061:        self._trigger_rejection_dedup[dedup_key] = now
```
**Result:** PASS
**Notes:** Line 92 not 88 (off by 4). Type annotation `Dict[str, float]` matches the `{symbol_pattern: timestamp}` described in the report. Dict is used in 3 places: init, read, write — all consistent.

---

### Claim 3: `log_warrior_trigger_rejection()` method with 30s dedup

**Claim:** Method exists at lines 1028-1091 with 30-second dedup via `time.time()` and per-symbol+pattern key
**Verification Command:** `view_file` at lines 1037-1096
**Actual Code (key sections):**
```python
def log_warrior_trigger_rejection(
    self,
    symbol: str,
    best_pattern: str,
    best_score: float,
    threshold: float,
    candidate_count: int,
    price: float,
    all_candidates: Dict[str, float],
) -> None:
    # Dedup: skip if same symbol+pattern was rejected < 30s ago
    dedup_key = f"{symbol}_{best_pattern}"
    now = time.time()
    last_ts = self._trigger_rejection_dedup.get(dedup_key, 0)
    if (now - last_ts) < 30:
        return  # Suppress duplicate within 30s window
    self._trigger_rejection_dedup[dedup_key] = now
```
**Result:** PASS
**Notes:** Method at lines 1037-1096 (not 1028-1091 — shifted by ~9 lines). Logic verified:
- ✅ Uses `time.time()` for dedup timestamps
- ✅ Dedup key is `f"{symbol}_{best_pattern}"` (per-symbol+pattern)
- ✅ 30-second window: `if (now - last_ts) < 30: return`
- ✅ Calls `_log_to_file()` for TML forensics
- ✅ Calls `_log_event()` with `position_id="TRIGGER_REJECTION"`, `event_type=self.WARRIOR_TRIGGER_REJECTION`
- ✅ Metadata includes: best_pattern, best_score, threshold, gap_to_threshold, candidate_count, price, all_candidates

---

### Claim 4: Below-score call site in `warrior_engine_entry.py`

**Claim:** Call site wired at ~line 619 after the existing `logger.info` at the below-score rejection
**Verification Command:**
```powershell
Select-String -Path "nexus2\domain\automation\warrior_engine_entry.py" -Pattern "log_warrior_trigger_rejection"
```
**Actual Output:**
```
warrior_engine_entry.py:423:    trade_event_service.log_warrior_trigger_rejection(
warrior_engine_entry.py:634:    trade_event_service.log_warrior_trigger_rejection(
```
**Actual Code (lines 627-642):**
```python
else:
    logger.info(
        f"[Warrior Entry] {symbol}: Best candidate {winner.pattern.name} "
        f"BELOW THRESHOLD ({winner.score:.3f} < {MIN_SCORE_THRESHOLD})"
    )
    # Persist rejection to DB for analytics (closest-to-trade events)
    from nexus2.domain.automation.trade_event_service import trade_event_service
    trade_event_service.log_warrior_trigger_rejection(
        symbol=symbol,
        best_pattern=winner.pattern.name,
        best_score=winner.score,
        threshold=MIN_SCORE_THRESHOLD,
        candidate_count=len(candidates),
        price=float(current_price),
        all_candidates={c.pattern.name: c.score for c in candidates},
    )
```
**Result:** PASS
**Notes:** Actual line 634 (not 619 — off by 15). Import is local (inside the `else` branch at line 633), as claimed. All arguments match the method signature. Uses correct `winner.pattern.name`, `winner.score`, and dict comprehension for `all_candidates`.

---

### Claim 5: Micro-pullback skip logging with throttle

**Claim:** Micro-pullback skip logging at ~line 422 with `_micro_skip_logged` per-symbol throttle
**Verification Command:**
```powershell
Select-String -Path "nexus2\domain\automation\warrior_engine_entry.py" -Pattern "MICRO_PULLBACK_SKIP"
```
**Actual Output:**
```
warrior_engine_entry.py:425:    best_pattern="MICRO_PULLBACK_SKIP",
```
**Actual Code (lines 420-432):**
```python
# Log first skip per symbol (throttled to avoid noise)
if not getattr(watched, '_micro_skip_logged', False):
    from nexus2.domain.automation.trade_event_service import trade_event_service
    trade_event_service.log_warrior_trigger_rejection(
        symbol=symbol,
        best_pattern="MICRO_PULLBACK_SKIP",
        best_score=0.0,
        threshold=0.0,
        candidate_count=0,
        price=float(current_price),
        all_candidates={},
    )
    watched._micro_skip_logged = True
```
**Result:** PASS
**Notes:** Lines 420-432 (claimed ~419-432 — accurate). Throttle uses `getattr(watched, '_micro_skip_logged', False)` with safe default, and sets `watched._micro_skip_logged = True` after logging. This ensures only one event per symbol per watchlist session.

---

### Claim 6: Full test suite passes

**Claim:** 757 passed, 4 skipped, 3 deselected, 0 failures
**Verification Command:**
```powershell
python -m pytest nexus2/tests/ -x -q 2>&1 | Select-Object -Last 20
```
**Actual Output:**
```
757 passed, 4 skipped, 3 deselected in 175.04s (0:02:55)
```
**Result:** PASS
**Notes:** Exact match on pass/skip/deselect counts. Zero failures. Runtime difference (175s vs reported 111s) is expected variance.

---

## Additional Checks (from handoff)

### Constant ordering
**Requirement:** `WARRIOR_TRIGGER_REJECTION` should be between `WARRIOR_GUARD_BLOCK` and `WARRIOR_REENTRY_ENABLED`
**Verified:** Lines 79-81:
```python
WARRIOR_GUARD_BLOCK = "GUARD_BLOCK"           # line 79
WARRIOR_TRIGGER_REJECTION = "TRIGGER_REJECTION"  # line 80
WARRIOR_REENTRY_ENABLED = "REENTRY_ENABLED"      # line 81
```
**Result:** ✅ PASS — Correct ordering

### 30-second dedup uses `time.time()`
**Verified:** Line 1057: `now = time.time()` — uses wall-clock time, not sim clock. Appropriate for dedup (prevents log spam regardless of mode).
**Result:** ✅ PASS

### Micro-pullback throttle uses `_micro_skip_logged`
**Verified:** Line 421: `if not getattr(watched, '_micro_skip_logged', False)` + line 432: `watched._micro_skip_logged = True`
**Result:** ✅ PASS — Per-symbol throttle via attribute on `WatchedCandidate`

---

## Overall Rating

### **HIGH** — All 6 claims verified, clean implementation

All code exists, all logic matches descriptions, test suite passes with zero failures. The only discrepancies are minor line number drifts (1-15 lines off), which is expected when other changes have been made to these files between the implementation and validation.

No issues found. No rework required.
