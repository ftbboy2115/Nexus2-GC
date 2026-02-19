# Audit Validator Handoff: Quote Data Quality Phase 1

**Date:** 2026-02-18
**Implementer:** Backend Specialist
**Validator:** Audit Validator
**Reference Spec:** `nexus2/reports/2026-02-18/spec_quote_data_quality.md`
**Backend Status:** `nexus2/reports/2026-02-18/backend_status_quote_data_quality.md`

---

## Context

The Backend Specialist implemented Phase 1 quote data quality fixes to address stale Polygon prices for illiquid tickers (root cause of LRHC exit pricing bug: bot saw $1.78, market was $2.17).

**5 production files were modified.** The backend agent provided 10 testable claims. Your job is to independently verify each claim using the PowerShell commands below.

---

## Verification Commands

### Claim 1: `_parse_polygon_timestamp` exists and handles nanosecond timestamps
**File:** `polygon_adapter.py:97-112`

```powershell
# Verify function exists
Select-String -Path "nexus2\adapters\market_data\polygon_adapter.py" -Pattern "def _parse_polygon_timestamp"

# Verify it handles nanoseconds (divides by 1e9)
Select-String -Path "nexus2\adapters\market_data\polygon_adapter.py" -Pattern "1e9|1_000_000_000"

# Verify None/0 fallback to datetime.now(UTC)
Select-String -Path "nexus2\adapters\market_data\polygon_adapter.py" -Pattern "not ts|ts.*==.*0|utcnow|timezone.utc"
```

---

### Claim 2: `get_quote()` uses real trade timestamp
**File:** `polygon_adapter.py:118-155`

```powershell
# Verify _parse_polygon_timestamp is called in get_quote
Select-String -Path "nexus2\adapters\market_data\polygon_adapter.py" -Pattern "_parse_polygon_timestamp" | Select-Object LineNumber, Line

# Verify quote_age_seconds is calculated
Select-String -Path "nexus2\adapters\market_data\polygon_adapter.py" -Pattern "quote_age_seconds"

# Verify price_source is set
Select-String -Path "nexus2\adapters\market_data\polygon_adapter.py" -Pattern "price_source"
```

---

### Claim 3: Midpoint fallback with guards (market hours, spread <5%, age >120s)
**File:** `polygon_adapter.py:130-145`

```powershell
# Verify STALE_TRADE_THRESHOLD_SECONDS constant = 120
Select-String -Path "nexus2\adapters\market_data\polygon_adapter.py" -Pattern "STALE_TRADE_THRESHOLD_SECONDS"

# Verify is_market_hours guard
Select-String -Path "nexus2\adapters\market_data\polygon_adapter.py" -Pattern "is_market_hours"

# Verify spread guard (<5%)
Select-String -Path "nexus2\adapters\market_data\polygon_adapter.py" -Pattern "spread|0\.05"

# Verify midpoint calculation
Select-String -Path "nexus2\adapters\market_data\polygon_adapter.py" -Pattern "midpoint|bid.*ask.*2"

# Verify price_source = "midpoint" when fallback triggers
Select-String -Path "nexus2\adapters\market_data\polygon_adapter.py" -Pattern '"midpoint"'
```

---

### Claim 4: `get_last_trade()` uses real timestamp
**File:** `polygon_adapter.py:176-189`

```powershell
# Verify _parse_polygon_timestamp called in get_last_trade
# (look at code in that line range)
.venv\Scripts\python -c "lines = open('nexus2/adapters/market_data/polygon_adapter.py').readlines(); [print(f'{i+1}: {l}', end='') for i, l in enumerate(lines[175:195])]"
```

---

### Claim 5: `get_quotes_batch()` uses real timestamps + midpoint fallback
**File:** `polygon_adapter.py:213-256`

```powershell
# Verify per-symbol timestamp parsing in batch method
.venv\Scripts\python -c "lines = open('nexus2/adapters/market_data/polygon_adapter.py').readlines(); [print(f'{i+1}: {l}', end='') for i, l in enumerate(lines[212:260])]"
```

---

### Claim 6: `unified.py` single-source WARNING
**File:** `unified.py:224-236`

```powershell
# Verify single-source warning log
Select-String -Path "nexus2\adapters\market_data\unified.py" -Pattern "SINGLE SOURCE|single.source|no cross-validation"

# Verify staleness warning
Select-String -Path "nexus2\adapters\market_data\unified.py" -Pattern "stale|Xs old|quote_age_seconds"
```

---

### Claim 7: Audit service accepts + persists staleness fields
**File:** `quote_audit_service.py`

```powershell
# Verify function signature includes new params
Select-String -Path "nexus2\domain\audit\quote_audit_service.py" -Pattern "polygon_trade_age_seconds|polygon_price_source"

# Verify _flush_batch writes the fields
Select-String -Path "nexus2\domain\audit\quote_audit_service.py" -Pattern "polygon_trade_age|polygon_price_source"
```

---

### Claim 8: `Quote` dataclass backward compatible (new fields default to None)
**File:** `protocol.py:39-40`

```powershell
# Verify fields exist with Optional/None defaults
Select-String -Path "nexus2\adapters\market_data\protocol.py" -Pattern "quote_age_seconds|price_source"

# Verify backward compat: create Quote without new fields
.venv\Scripts\python -c "from nexus2.adapters.market_data.protocol import Quote; q = Quote(symbol='X', price=0, change=0, change_percent=0, volume=0, timestamp=None); print(f'Backward compat OK: age={q.quote_age_seconds}, src={q.price_source}')"
```

---

### Claim 9: `QuoteAuditModel` has new columns
**File:** `models.py:505-506`

```powershell
# Verify columns exist on model
Select-String -Path "nexus2\db\models.py" -Pattern "polygon_trade_age_seconds|polygon_price_source"

# Verify to_dict includes them
.venv\Scripts\python -c "from nexus2.db.models import QuoteAuditModel; m = QuoteAuditModel(); d = m.to_dict(); print(f'to_dict has age: {\"polygon_trade_age_seconds\" in d}, src: {\"polygon_price_source\" in d}')"
```

---

### Claim 10: `_log_and_return` passes staleness to audit
**File:** `unified.py:195-196` and `unified.py:153-154`

```powershell
# Verify both call sites pass the new fields to audit.log_quote_check
Select-String -Path "nexus2\adapters\market_data\unified.py" -Pattern "log_quote_check" | Select-Object LineNumber, Line
```

---

## Negative Checks

```powershell
# Verify the deleted test file is gone
Test-Path "nexus2\tests\unit\adapters\test_polygon_quote_freshness.py"
# Expected: False

# Verify no new datetime.now() violations were introduced
Select-String -Path "nexus2\adapters\market_data\polygon_adapter.py" -Pattern "datetime\.now\(\s*\)"
# Expected: No matches (all should use _parse_polygon_timestamp or datetime.now(timezone.utc) in fallback)

# Verify existing tests still pass
.venv\Scripts\python -m pytest nexus2/tests/ -x --no-header --tb=short -q 2>&1 | Select-Object -Last 5
```

---

## Validation Report Format

Produce a report with:

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | _parse_polygon_timestamp exists | PASS/FAIL | [command + output] |
| ... | ... | ... | ... |

### Overall Rating
- **HIGH**: All claims verified
- **MEDIUM**: Minor issues (cosmetic)
- **LOW**: Major issues (requires rework)
