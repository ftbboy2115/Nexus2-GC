# Backend Status: Trigger Rejection Logging

**Date:** 2026-02-21
**Agent:** Backend Specialist
**Spec:** `nexus2/reports/2026-02-21/spec_early_rejection_logging.md`
**Handoff:** `nexus2/reports/2026-02-21/handoff_backend_trigger_rejection_logging.md`

---

## Summary

Implemented `WARRIOR_TRIGGER_REJECTION` event type so that below-threshold pattern rejections are persisted to the trade_events DB. This is a logging-only change — no behavioral changes to entry logic.

All 4 change points from the spec are implemented (including the optional micro-pullback skip).

---

## Changes Made

### 1. `trade_event_service.py` — New constant (line 79)

```python
WARRIOR_TRIGGER_REJECTION = "TRIGGER_REJECTION"  # Pattern scored but below threshold
```

**Verified with:** `python _check_trigger_rejection.py` → `Constant: TRIGGER_REJECTION`

---

### 2. `trade_event_service.py` — Dedup dict in `__init__` (line 88)

```python
self._trigger_rejection_dedup: Dict[str, float] = {}
```

Tracks `{symbol_pattern: timestamp}` for 30-second per-symbol+pattern dedup window.

**Verified with:** `python _check_trigger_rejection.py` → `Dedup dict exists: True, type: dict`

---

### 3. `trade_event_service.py` — New `log_warrior_trigger_rejection()` method (lines 1028-1091)

Follows `log_warrior_guard_block()` template:
- **30s dedup:** `dedup_key = f"{symbol}_{best_pattern}"` — skips if same key was written <30s ago
- **TML file write:** via `_log_to_file()` for forensic review
- **DB write:** via `_log_event()` with `position_id="TRIGGER_REJECTION"`, `event_type=WARRIOR_TRIGGER_REJECTION`
- **Metadata:** best_pattern, best_score, threshold, gap_to_threshold, candidate_count, price, all_candidates

**Signature:**
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
```

---

### 4. `warrior_engine_entry.py` — Call site at below-score rejection (lines 619-628)

After the existing `logger.info` at the below-score rejection:
```python
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

Import is local (inside the `else` branch), following the existing pattern at lines 1287 and 1395.

---

### 5. `warrior_engine_entry.py` — Optional micro-pullback skip logging (lines 419-432)

When extended stock routes to micro-pullback but `_check_micro_pullback_pattern` returns None:
```python
if not getattr(watched, '_micro_skip_logged', False):
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

Per-symbol throttle via `_micro_skip_logged` flag on the `WatchedCandidate`.

---

## Verification

### Import Check
```
Constant: TRIGGER_REJECTION
Method exists: True
Dedup dict exists: True
Dedup dict type: <class 'dict'>
ALL CHECKS PASSED
```

### Test Suite
```
757 passed, 4 skipped, 3 deselected in 111.62s
```
**Zero failures.** The 4 skips and 3 deselections are pre-existing.

---

## Testable Claims for Validator

| # | Claim | Verify With |
|---|-------|-------------|
| 1 | `WARRIOR_TRIGGER_REJECTION = "TRIGGER_REJECTION"` exists at `trade_event_service.py:79` | `Select-String -Path "nexus2\domain\automation\trade_event_service.py" -Pattern "TRIGGER_REJECTION"` |
| 2 | `_trigger_rejection_dedup` dict initialized in `__init__` | `Select-String -Path "nexus2\domain\automation\trade_event_service.py" -Pattern "_trigger_rejection_dedup"` |
| 3 | `log_warrior_trigger_rejection()` method exists with 30s dedup | `Select-String -Path "nexus2\domain\automation\trade_event_service.py" -Pattern "log_warrior_trigger_rejection"` |
| 4 | Below-score call site wired at ~line 619 in `warrior_engine_entry.py` | `Select-String -Path "nexus2\domain\automation\warrior_engine_entry.py" -Pattern "log_warrior_trigger_rejection"` |
| 5 | Micro-pullback skip logging with throttle at ~line 422 | `Select-String -Path "nexus2\domain\automation\warrior_engine_entry.py" -Pattern "MICRO_PULLBACK_SKIP"` |
| 6 | Full test suite passes (757 passed, 0 failures) | `python -m pytest nexus2/tests/ -x -q` |

---

## Not In Scope (per spec)

- Logging "no pattern triggered" cycles (LOW value, too noisy)
- Changing existing `logger.info` calls
- Adding UI components to display trigger rejections (separate frontend task)
- DB migration: No schema changes — uses existing `trade_events` table with existing columns
