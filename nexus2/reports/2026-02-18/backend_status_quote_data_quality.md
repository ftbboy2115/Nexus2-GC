# Backend Status: Quote Data Quality Phase 1

**Date:** 2026-02-18
**Status:** ✅ Implementation Complete — Awaiting Testing Specialist Validation

---

## Summary

Implemented Phase 1 quote data quality fixes across 5 production files. All imports verified successfully.

---

## Files Modified

| # | File | Change |
|---|------|--------|
| 1 | [protocol.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/market_data/protocol.py) | Added `quote_age_seconds` and `price_source` fields to `Quote` dataclass |
| 2 | [polygon_adapter.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/market_data/polygon_adapter.py) | Added `_parse_polygon_timestamp()`, real timestamps, midpoint fallback |
| 3 | [unified.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/market_data/unified.py) | Single-source warning + staleness propagation |
| 4 | [models.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/db/models.py) | Added 2 columns to `QuoteAuditModel` |
| 5 | [quote_audit_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/audit/quote_audit_service.py) | Accepts + persists new staleness fields |

---

## Import Verification Results

| Module | Result |
|--------|--------|
| `polygon_adapter` (PolygonAdapter, STALE_TRADE_THRESHOLD_SECONDS) | ✅ OK, threshold=120 |
| `polygon_adapter._parse_polygon_timestamp` | ✅ Exists |
| `protocol.Quote` (quote_age_seconds, price_source) | ✅ Fields work |
| `unified.UnifiedMarketData` | ✅ OK |
| `models.QuoteAuditModel` (polygon_trade_age_seconds, polygon_price_source) | ✅ Both columns present |
| `quote_audit_service.log_quote_check` signature | ✅ Has `polygon_trade_age_seconds` and `polygon_price_source` params |

---

## Testable Claims for Testing Specialist

### Claim 1: `_parse_polygon_timestamp` converts nanosecond timestamps
- **File:** `polygon_adapter.py:97-112`
- **Behavior:** `PolygonAdapter._parse_polygon_timestamp(1705314600_000_000_000)` → `datetime(2024, 1, 15, 10, 30, tzinfo=UTC)`
- **Edge cases:** `None` → `datetime.now(UTC)`, `0` → `datetime.now(UTC)`, invalid string → `datetime.now(UTC)`

### Claim 2: `get_quote()` uses real trade timestamp
- **File:** `polygon_adapter.py:118-155`
- **Behavior:** `Quote.timestamp` is derived from `lastTrade.t` nanosecond field, NOT `datetime.now(UTC)`
- **Behavior:** `Quote.quote_age_seconds` = `(now - trade_timestamp).total_seconds()`
- **Behavior:** `Quote.price_source` = `"lastTrade"` when trade is fresh

### Claim 3: Midpoint fallback during market hours when stale
- **File:** `polygon_adapter.py:130-145`
- **Condition:** `is_market_hours() AND trade_age > 120s AND bid > 0 AND ask > 0 AND spread < 5% AND |midpoint - price| / price > 1%`
- **Behavior:** `Quote.price` = `(bid + ask) / 2`, `Quote.price_source` = `"midpoint"`
- **Guard:** NO midpoint fallback when `is_market_hours()` returns False (pre-market/after-hours)
- **Guard:** NO midpoint fallback when spread ≥ 5% (wide / illiquid)

### Claim 4: `get_last_trade()` uses real timestamp
- **File:** `polygon_adapter.py:176-189`
- **Behavior:** Uses `result.t` for timestamp, sets `quote_age_seconds` and `price_source="lastTrade"`

### Claim 5: `get_quotes_batch()` uses real timestamps + midpoint fallback
- **File:** `polygon_adapter.py:213-256`
- **Behavior:** Same timestamp and midpoint logic as `get_quote()`, applied per-symbol in batch

### Claim 6: `unified.py` single-source warning
- **File:** `unified.py:224-236`
- **Behavior:** When `len(prices) == 1`, logs at `WARNING` level: `"SINGLE SOURCE only ... no cross-validation possible"`
- **Behavior:** When Polygon-only and `quote_age_seconds > 120`, additional WARNING: `"Polygon lastTrade is Xs old — price may be stale"`

### Claim 7: Audit service persists staleness fields
- **File:** `quote_audit_service.py:140-141` (signature), `quote_audit_service.py:128-129` (flush)
- **Behavior:** `log_quote_check()` accepts `polygon_trade_age_seconds` and `polygon_price_source`
- **Behavior:** `_flush_batch()` writes both fields to `QuoteAuditModel`

### Claim 8: `Quote` dataclass backward compatible
- **File:** `protocol.py:39-40`
- **Behavior:** `quote_age_seconds` and `price_source` default to `None`, existing callers unaffected

### Claim 9: `QuoteAuditModel` has new columns
- **File:** `models.py:505-506`
- **Behavior:** `polygon_trade_age_seconds` (String(10), nullable) and `polygon_price_source` (String(20), nullable)
- **Behavior:** `to_dict()` includes both new fields

### Claim 10: `_log_and_return` passes staleness to audit
- **File:** `unified.py:195-196` and `unified.py:153-154`
- **Behavior:** Both call sites in `unified.py` pass `polygon_trade_age_seconds` and `polygon_price_source` to `audit.log_quote_check()`

---

## Mock Path Note for Tests

> [!IMPORTANT]
> `is_market_hours` is imported **locally** inside `get_quote()` and `get_quotes_batch()` via
> `from nexus2.utils.time_utils import is_market_hours`. Tests must patch at
> `nexus2.utils.time_utils.is_market_hours`, **not** at the polygon_adapter module level.

---

## DB Migration Note

> [!WARNING]
> The 2 new columns (`polygon_trade_age_seconds`, `polygon_price_source`) were added to the
> `QuoteAuditModel` SQLAlchemy model. Since this project uses SQLite with auto-creation,
> existing `quote_audit` tables will need either:
> - Table drop/recreate (acceptable for audit tables), OR
> - `ALTER TABLE quote_audit ADD COLUMN ...` migration
