# Handoff: Backend Specialist — Quote Data Quality Phase 1

@agent-backend-specialist.md

## Context

Polygon's `lastTrade.p` can be minutes/hours old for illiquid tickers at market open. Our adapter stamps `datetime.now()` instead of the real trade timestamp, hiding staleness from all downstream consumers. This caused a 23% price gap on LRHC (bot saw $1.78, market was $2.17).

**Spec:** Read `spec_quote_data_quality.md` in this same directory for full analysis.

**Approved decisions:**
- Staleness threshold: 120 seconds
- Pre-market guard: Skip midpoint fallback outside market hours (use existing `is_market_hours()` from `nexus2.utils.time_utils`)
- New Quote fields: `quote_age_seconds` (Optional[float]) and `price_source` (Optional[str])
- Persist to DB: Add these fields to `QuoteAuditModel` for queryable staleness tracking

---

## Required Changes (4 files + 1 new test file)

### Change 1: Add timestamp helper + midpoint fallback in `polygon_adapter.py`

**File:** `nexus2/adapters/market_data/polygon_adapter.py`

**a) Add helper method (class method or module-level):**

```python
def _parse_polygon_timestamp(ns_timestamp) -> datetime:
    """Convert Polygon nanosecond Unix timestamp to datetime (UTC)."""
    if not ns_timestamp:
        return datetime.now(timezone.utc)
    try:
        seconds = int(ns_timestamp) / 1_000_000_000
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return datetime.now(timezone.utc)
```

**b) Update `get_quote()` (~L127):**

Replace `timestamp=datetime.now(timezone.utc)` with real timestamp + staleness detection:

```python
STALE_TRADE_THRESHOLD_SECONDS = 120

# Parse real trade timestamp
trade_timestamp = self._parse_polygon_timestamp(last_trade.get("t"))
trade_age_seconds = (datetime.now(timezone.utc) - trade_timestamp).total_seconds()

# Primary price
price = last_trade.get("p") or day.get("c") or 0
bid_price = last_quote.get("p", 0) or 0
ask_price = last_quote.get("P", 0) or 0
price_source = "lastTrade"

# Midpoint fallback during market hours when lastTrade is stale
from nexus2.utils.time_utils import is_market_hours
if (is_market_hours() and 
    trade_age_seconds > STALE_TRADE_THRESHOLD_SECONDS and 
    bid_price > 0 and ask_price > 0):
    midpoint = (float(bid_price) + float(ask_price)) / 2
    spread_pct = (float(ask_price) - float(bid_price)) / float(bid_price) * 100
    if spread_pct < 5.0 and abs(midpoint - float(price)) / float(price) > 0.01:
        logger.warning(
            f"[Polygon] {symbol}: lastTrade is {trade_age_seconds:.0f}s old "
            f"(${price:.2f}), using bid/ask midpoint ${midpoint:.2f} "
            f"(bid=${bid_price:.2f}, ask=${ask_price:.2f}, spread={spread_pct:.1f}%)"
        )
        price = midpoint
        price_source = "midpoint"

# Build Quote with real timestamp and age info
return Quote(
    symbol=symbol,
    price=Decimal(str(price)),
    ...existing fields...
    timestamp=trade_timestamp,  # Was: datetime.now(timezone.utc)
    quote_age_seconds=trade_age_seconds,
    price_source=price_source,
)
```

**c) Update `get_last_trade()` (~L180):**
```diff
-            timestamp=datetime.now(timezone.utc),
+            timestamp=self._parse_polygon_timestamp(result.get("t")),
```

**d) Update `get_quotes_batch()` (~L228):**
Apply same pattern: real timestamp + staleness fallback + `quote_age_seconds`/`price_source` fields.

---

### Change 2: Add fields to `Quote` dataclass in `protocol.py`

**File:** `nexus2/adapters/market_data/protocol.py`

```diff
 @dataclass
 class Quote:
     ...existing fields...
+    quote_age_seconds: Optional[float] = None  # Age of lastTrade at fetch time
+    price_source: Optional[str] = None  # "lastTrade" | "midpoint" | "day_close"
```

Both are Optional with None defaults — fully backward compatible.

---

### Change 3: Single-source warning + age propagation in `unified.py`

**File:** `nexus2/adapters/market_data/unified.py`

At L224-227, add warning when only one source is available:

```diff
 if len(prices) == 1:
     source, price = list(prices.items())[0]
-    logger.debug(f"[Quote] {symbol}: Only {source} available (${price:.2f})")
+    logger.warning(
+        f"[Quote] {symbol}: SINGLE SOURCE only ({source}, ${price:.2f}) — "
+        f"no cross-validation possible"
+    )
     if source == "Polygon":
+        if polygon_quote and polygon_quote.quote_age_seconds and polygon_quote.quote_age_seconds > 120:
+            logger.warning(
+                f"[Quote] {symbol}: Polygon lastTrade is {polygon_quote.quote_age_seconds:.0f}s old — "
+                f"price may be stale for illiquid ticker"
+            )
         return _log_and_return(polygon_quote, "Polygon", 0.0)
```

Also update `_log_and_return()` to pass `quote_age_seconds` and `price_source` to the audit service (see Change 4).

---

### Change 4: Persist staleness to quote audit DB

**File:** `nexus2/db/models.py` — Add 2 columns to `QuoteAuditModel`:

```diff
 class QuoteAuditModel(Base):
     ...existing columns...
     high_divergence = Column(Boolean, default=False, index=True)
+    polygon_trade_age_seconds = Column(String(10), nullable=True)  # Age of Polygon lastTrade
+    polygon_price_source = Column(String(20), nullable=True)  # "lastTrade" | "midpoint" | "day_close"
```

Update `to_dict()` to include the new fields.

**File:** `nexus2/domain/audit/quote_audit_service.py` — Update `log_quote_check()`:

Add `polygon_trade_age_seconds` and `polygon_price_source` keyword arguments and store them on the model. Check the existing signature and add as optional kwargs with `None` defaults.

**File:** `nexus2/adapters/market_data/unified.py` — Pass the new fields from `_log_and_return()`:

In the `_log_and_return` helper and the inline Polygon+Schwab early return (L148), pass the polygon quote's age/source:

```python
audit.log_quote_check(
    ...existing args...
    polygon_trade_age_seconds=str(polygon_quote.quote_age_seconds) if polygon_quote and polygon_quote.quote_age_seconds else None,
    polygon_price_source=polygon_quote.price_source if polygon_quote else None,
)
```

---

## Files NOT to Touch (Phase 2 scope)

- `warrior_callbacks.py` — Already has bidirectional stale guard, Phase 2 adds `quote_age_seconds` checks
- `warrior_engine_entry.py` — Phase 2: entry guards checking quote age
- `warrior_scanner_service.py` — Phase 2: scanner gap recalc with age warning

---

## Verification

1. `cd nexus2; python -c "from adapters.market_data.polygon_adapter import PolygonAdapter; print('Import OK')"`
2. `cd nexus2; python -c "from adapters.market_data.protocol import Quote; q = Quote(symbol='X', price=0, change=0, change_percent=0, volume=0, timestamp=None, quote_age_seconds=5.0, price_source='lastTrade'); print(f'Fields OK: age={q.quote_age_seconds}, src={q.price_source}')"`
3. `cd nexus2; python -m pytest tests/ -v --no-header --tb=short`
4. Verify no import errors on startup

## Reference Documents

- Planner spec: `nexus2/reports/2026-02-18/spec_quote_data_quality.md`
- Auditor findings: `nexus2/reports/2026-02-18/audit_exit_quote_freshness.md`
