# Testing Specialist Handoff: Quote Data Quality Phase 1

**Date:** 2026-02-18
**Context:** Backend Specialist implemented quote data quality fixes. Audit Validator confirmed all 10 claims PASS (HIGH rating). Now write `pytest` tests.

---

## What Was Implemented

The Polygon adapter now tracks quote staleness and falls back to bid/ask midpoint for illiquid tickers. This fixes the LRHC exit pricing bug (bot saw $1.78, market at $2.17).

**Files changed:** `polygon_adapter.py`, `protocol.py`, `unified.py`, `models.py`, `quote_audit_service.py`

**Reference docs:**
- Spec: `nexus2/reports/2026-02-18/spec_quote_data_quality.md`
- Backend status: `nexus2/reports/2026-02-18/backend_status_quote_data_quality.md`
- Validation: `nexus2/reports/2026-02-18/validation_quote_data_quality.md`

---

## Tests to Write

Create: `nexus2/tests/unit/adapters/test_polygon_quote_freshness.py`

### Test Group 1: `_parse_polygon_timestamp`

| Test | Input | Expected |
|------|-------|----------|
| Valid nanosecond timestamp | `1705314600_000_000_000` | `datetime(2024, 1, 15, 10, 30, tzinfo=UTC)` (approx) |
| None input | `None` | Returns `datetime.now(UTC)` (within 1s) |
| Zero input | `0` | Returns `datetime.now(UTC)` (within 1s) |
| Invalid string | `"not_a_number"` | Returns `datetime.now(UTC)` (within 1s) |

### Test Group 2: `get_quote()` Timestamp Propagation

| Test | Setup | Assert |
|------|-------|--------|
| Fresh trade | Mock snapshot with recent `lastTrade.t` | `quote.quote_age_seconds` < 5, `quote.price_source` == `"lastTrade"` |
| Stale trade (no fallback, outside market hours) | Mock snapshot with old `lastTrade.t`, patch `is_market_hours` → False | `quote.price_source` == `"lastTrade"` (no midpoint fallback) |

### Test Group 3: Midpoint Fallback Logic

| Test | Condition | Assert |
|------|-----------|--------|
| Triggers fallback | `is_market_hours=True`, trade age > 120s, bid/ask present, spread < 5% | `quote.price_source` == `"midpoint"`, `quote.price` == `(bid+ask)/2` |
| No fallback: outside market hours | `is_market_hours=False`, trade stale | `quote.price_source` == `"lastTrade"` |
| No fallback: spread too wide | `is_market_hours=True`, spread ≥ 5% | `quote.price_source` == `"lastTrade"` |
| No fallback: trade still fresh | `is_market_hours=True`, trade age < 120s | `quote.price_source` == `"lastTrade"` |
| No fallback: no bid/ask | `is_market_hours=True`, trade stale, bid=0 | `quote.price_source` == `"lastTrade"` |

### Test Group 4: `get_quotes_batch()` Same Logic

| Test | Setup | Assert |
|------|-------|--------|
| Batch uses timestamps + midpoint | Mock multi-symbol snapshot | Per-symbol `quote_age_seconds` and `price_source` populated |

### Test Group 5: `Quote` Dataclass Backward Compat

| Test | Setup | Assert |
|------|-------|--------|
| Old callers work | Create `Quote(symbol=..., price=..., ...)` without new fields | `quote_age_seconds` is None, `price_source` is None |

### Test Group 6: Single-Source Warning in `unified.py`

| Test | Setup | Assert |
|------|-------|--------|
| Single source logs warning | Mock only 1 provider returning data | WARNING log contains "SINGLE SOURCE" |
| Stale Polygon logs extra warning | Single source + `quote_age_seconds` > 120 | WARNING log mentions staleness |

---

## Mock Path Note

> [!IMPORTANT]
> `is_market_hours` is imported **locally** inside `get_quote()` and `get_quotes_batch()`.
> Patch at `nexus2.utils.time_utils.is_market_hours`, **NOT** at the adapter module level.

---

## Existing Test Baseline

741 tests pass, 4 skipped. Your new tests must not break any existing tests.
