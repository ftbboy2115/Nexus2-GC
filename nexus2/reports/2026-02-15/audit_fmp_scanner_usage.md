# Audit: FMP Usage in Warrior Scanner — Polygon Migration Opportunities

**Date**: 2026-02-15
**Agent**: Code Auditor
**Scope**: `warrior_scanner_service.py`, `unified.py`, `fmp_adapter.py`, `polygon_adapter.py`

---

## Executive Summary

The Warrior Scanner pipeline makes **10 distinct FMP API calls** during a single scan cycle. Of these:

| Category | Count | Examples |
|----------|-------|---------|
| ✅ **Migratable to Polygon** | 5 | daily bars, previousClose, session snapshot, news, pre-market gainers |
| ❌ **Must keep FMP** | 3 | float shares, ETF list, country profile |
| 🔄 **Already using Polygon** | 2 | 200 EMA, top gainers (primary) |

**Estimated API call savings**: ~60% of scanner FMP calls per scan cycle can migrate to Polygon, which Clay already pays $200/mo for (unlimited calls).

---

## A. File Inventory

| File | Lines | Key Functions | FMP Calls |
|------|-------|---------------|-----------|
| [warrior_scanner_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py) | 1798 | 25 | 3 direct, 7 through unified |
| [unified.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/market_data/unified.py) | 886 | 31 | 15+ delegations to `self.fmp` |
| [fmp_adapter.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/market_data/fmp_adapter.py) | 1182 | 48 | N/A (is the source) |
| [polygon_adapter.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/market_data/polygon_adapter.py) | 487 | 18 | 0 |

---

## B. Dependency Graph

```
warrior_scanner_service.py
  └── imports: unified.py (as UnifiedMarketData)
  └── accesses: self.market_data.fmp._get()     (DIRECT bypass of unified)
  └── accesses: self.market_data.fmp.get_etf_symbols()  (DIRECT bypass)
  └── accesses: self.market_data.fmp.get_daily_bars()   (DIRECT bypass)
  └── accesses: self.market_data.fmp.get_country()      (DIRECT bypass)
  └── accesses: self.market_data.polygon.get_gainers()  (DIRECT bypass)
  └── accesses: self.market_data.polygon.get_daily_bars() (DIRECT bypass)
  └── calls: self.market_data.get_quote()
  └── calls: self.market_data.get_gainers()
  └── calls: self.market_data.get_actives()
  └── calls: self.market_data.get_premarket_gainers()
  └── calls: self.market_data.build_session_snapshot()
  └── calls: self.market_data.get_merged_headlines()
  └── makes: DIRECT httpx.get() to FMP stable/shares-float

unified.py
  └── imports: fmp_adapter.py (as self.fmp)
  └── imports: polygon_adapter.py (as self.polygon)
  └── imports: alpaca_adapter.py (as self.alpaca)
```

> [!WARNING]
> **Layer violation**: Scanner directly accesses `self.market_data.fmp._get()` and individual adapter methods instead of going through unified interface methods. This makes migration harder — every direct access needs individual attention.

---

## C. Complete FMP Call Inventory

### Finding 1: Float Shares — ❌ KEEP FMP

**File:** [warrior_scanner_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py#L1056-L1082)
**Code:**
```python
# Line 1068-1071
response = httpx.get(
    "https://financialmodelingprep.com/stable/shares-float",
    params={"symbol": symbol, "apikey": app_config.FMP_API_KEY},
    timeout=5.0,
)
```
**Migration Risk:** N/A — Polygon does NOT provide float shares
**Polygon equivalent:** None. `get_ticker_details()` returns `share_class_shares_outstanding` and `weighted_shares_outstanding` (total shares), but NOT float. The adapter even documents this:
```python
# polygon_adapter.py:261 comment
# Note: Does NOT include float shares (use FMP for that).
```
**Conclusion:** Must keep FMP for float data. This is the most critical FMP dependency — float is Pillar 1 of Ross Cameron's 5 Pillars.

---

### Finding 2: Former Runner Check (Daily Bars) — ✅ MIGRATE TO POLYGON

**File:** [warrior_scanner_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py#L1084-L1111)
**Code:**
```python
# Line 1095
bars = self.market_data.fmp.get_daily_bars(symbol, limit=90)
```
**Migration Risk:** LOW
**Polygon equivalent:** `polygon_adapter.get_daily_bars(symbol, limit=90)` — already implemented, returns identical `OHLCV` objects
**Evidence:** The scanner already uses `self.market_data.polygon.get_daily_bars()` for 200 EMA at [L1153](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py#L1153), proving Polygon daily bars are trusted.
**Fix:**
```diff
-bars = self.market_data.fmp.get_daily_bars(symbol, limit=90)
+bars = self.market_data.polygon.get_daily_bars(symbol, limit=90)
```

---

### Finding 3: Country Profile — ❌ KEEP FMP (with Polygon partial alternative)

**File:** [warrior_scanner_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py#L1187-L1192)
**Code:**
```python
# Line 1190
return self.market_data.fmp.get_country(symbol)
```
**FMP endpoint:** `GET /api/v3/profile/{symbol}` → returns `country` field
**Polygon equivalent:** Partial. `get_ticker_details()` returns `sic_code` and `primary_exchange` but NOT a `country` field. The Polygon v3 reference/tickers endpoint has a `locale` field and `address` fields on detailed responses, but the current adapter doesn't extract them.
**Migration Risk:** MEDIUM — Would require extending `PolygonAdapter.get_ticker_details()` to parse `address.state` / locale data, and coverage may differ for micro-cap Chinese stocks
**Conclusion:** Keep FMP for now. Country check is cached for 30 days (`ttl 2592000` at L857), so API call volume is minimal.

---

### Finding 4: Gap Recalculation (previousClose) — ✅ MIGRATE TO POLYGON

**File:** [warrior_scanner_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py#L660-L686)
**Code:**
```python
# Line 671
fmp_data = self.market_data.fmp._get(f"quote/{symbol}")
if fmp_data and len(fmp_data) > 0:
    prev_close = float(fmp_data[0].get("previousClose", 0))
```
**Migration Risk:** LOW
**Polygon equivalent:** The Polygon snapshot endpoint already returns `prevDay.c` (previous close). Proof from [polygon_adapter.py:115](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/market_data/polygon_adapter.py#L115):
```python
prev_day = ticker.get("prevDay", {})
# ...
"prev_close": prev_day.get("c", 0),
```
**Fix:** Replace the raw FMP `_get()` call with a Polygon snapshot to get `prevDay.c`:
```diff
-fmp_data = self.market_data.fmp._get(f"quote/{symbol}")
-if fmp_data and len(fmp_data) > 0:
-    prev_close = float(fmp_data[0].get("previousClose", 0))
+polygon_quote = self.market_data.polygon.get_quote(symbol)
+if polygon_quote:
+    # Polygon snapshot includes prev_close in the Quote already computed
+    # But we need raw prevDay.c — add to get_quote or use snapshot directly
```

> [!IMPORTANT]
> The current `PolygonAdapter.get_quote()` computes `change` from `prevDay.c` but doesn't expose `prev_close` in the returned `Quote` object. A small addition to the Polygon `Quote` or a dedicated `get_prev_close()` method is needed.

---

### Finding 5: ETF Exclusion List — ❌ KEEP FMP

**File:** [warrior_scanner_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py#L697)
**Code:**
```python
# Line 697
etf_set = self._cached("etf_set", 86400, lambda: self.market_data.fmp.get_etf_symbols())
```
**FMP endpoint:** `GET /api/v3/etf/list` — returns all ETF symbols
**Polygon equivalent:** None directly. Polygon has `type` field in `get_ticker_details()` that can indicate ETFs, but no bulk ETF list endpoint. You'd need to call `get_ticker_details()` for EACH symbol to check type.
**Migration Risk:** HIGH — No equivalent bulk endpoint
**Conclusion:** Keep FMP. This is cached for 24 hours (86400s), so only 1 API call per day. Very low cost.

---

### Finding 6: Session Snapshot (FMP Quote) — ✅ MIGRATE TO POLYGON

**File:** [unified.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/market_data/unified.py#L466-L556)
**Code:**
```python
# unified.py Line 488 — initial quote
quote = self.fmp.get_quote(symbol)

# unified.py Line 530 — session OHLV data
quote_data = self.fmp._get(f"quote/{symbol}")
session_open = Decimal(str(q.get("open", 0)))
session_high = Decimal(str(q.get("dayHigh", 0)))
session_low = Decimal(str(q.get("dayLow", 0)))
session_volume = int(q.get("volume", 0))
```
**Migration Risk:** LOW-MEDIUM
**Polygon equivalent:** The Polygon snapshot at `/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}` returns:
- `day.o` = session open
- `day.h` = session high
- `day.l` = session low
- `day.v` = session volume
- `prevDay.c` = yesterday close
- `lastTrade.p` = last trade price

This is a **complete replacement** for the FMP quote data used in `build_session_snapshot()`.

**Fix:** Rewrite `build_session_snapshot()` to use Polygon snapshot:
```diff
-quote = self.fmp.get_quote(symbol)
+# Use Polygon snapshot — includes day OHLV, prevDay, volume
+snapshot_data = self.polygon._get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}")
```

> [!NOTE]
> This is the **highest-value migration** — `build_session_snapshot()` is called for EVERY symbol during evaluation (not just passed ones). Migrating this saves 1-2 FMP API calls per symbol evaluated.

---

### Finding 7: Headlines (News) — ✅ MIGRATE TO POLYGON (as additional source)

**File:** [unified.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/market_data/unified.py#L812-L884)
**Code:**
```python
# unified.py Line 837
fmp_headlines = self.fmp.get_recent_headlines(symbol, days=days)
```
**Migration Risk:** MEDIUM
**Polygon equivalent:** `polygon_adapter.get_news(symbol=symbol, limit=10)` — already implemented at [polygon_adapter.py:443-474](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/market_data/polygon_adapter.py#L443-L474)
**Coverage comparison:**
- FMP news: Good general coverage, includes micro-cap
- Polygon news: Sources from major wires (AP, Reuters, etc.), may miss some micro-cap stories
- The system already merges FMP + Alpaca/Benzinga + Yahoo + Finviz headlines

**Recommendation:** Add Polygon as **another source** in `get_merged_headlines()` rather than replacing FMP. This increases catalyst detection coverage. Eventually FMP can be demoted to fallback only.

**Fix:**
```python
# In get_merged_headlines(), add Polygon as source:
# 5. Polygon headlines (another pay source, different coverage)
try:
    polygon_news = self.polygon.get_news(symbol=symbol, limit=10)
    for item in polygon_news:
        headline = item.get("title", "").strip()
        normalized = headline.strip().lower()
        if normalized and normalized not in headlines_set:
            headlines_set.add(normalized)
            headlines_list.append(headline)
except Exception as e:
    print(f"[Unified] Polygon headlines error for {symbol}: {e}")
```

---

### Finding 8: Pre-Market Gainers — ✅ PARTIAL MIGRATION

**File:** [unified.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/market_data/unified.py#L601-L614)
**Code:**
```python
# unified.py Line 614
return self.fmp.get_premarket_gainers(min_change_pct=min_change_pct)
```
**FMP endpoint:** `GET /api/v3/pre_post_market/gainers`
**Polygon equivalent:** `polygon.get_gainers()` already captures pre-market data since Polygon snapshot includes extended hours with Developer tier ($200/mo). However, Polygon's endpoint only returns top 20 (hardcoded limit).
**Migration Risk:** MEDIUM — Polygon already used first in the scanner's `scan()` method at L620:
```python
polygon_gainers = self.market_data.polygon.get_gainers()
```
The FMP pre-market gainers serve as a **separate additional source** at L593.

**Conclusion:** Polygon gainers are already the primary source (L618-628). The FMP premarket gainers add coverage beyond Polygon's top-20 limit. Keep as secondary but deprioritize.

---

### Finding 9: Regular Gainers + Actives — 🔄 ALREADY HYBRID

**File:** [unified.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/market_data/unified.py#L585-L599)
**Code:**
```python
# unified.py Line 591
gainers = self.fmp.get_gainers()
# unified.py Line 599
return self.fmp.get_actives()
```
**Current state:** Scanner already uses Polygon gainers FIRST (L618-628), then adds FMP gainers (L630-635), then FMP actives (L637-642), then Alpaca movers (L644-49).
**Polygon equivalent for actives:** Not directly. Polygon has gainers/losers but no "most active by volume" endpoint.
**Migration Risk:** LOW — FMP provides `name` field which Polygon doesn't. Keep both sources merged.

---

### Finding 10: Cross-Validated Quote — 🔄 ALREADY POLYGON-FIRST

**File:** [unified.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/market_data/unified.py#L59-L315)
**Code:**
```python
# unified.py Line 107
polygon_quote = self.polygon.get_quote(symbol)
# ...
# Line 157 (only called if Polygon+Schwab disagree)
fmp_quote = self.fmp.get_quote(symbol)
```
**Current state:** Already properly structured. Polygon is primary (L107), Schwab validates (L122), FMP only called as fallback when Polygon+Schwab diverge >10% (L155-157).
**Conclusion:** No migration needed. FMP serves correctly as fallback/tie-breaker.

---

## D. Migration Plan — Recommended Order

| Priority | FMP Call | File:Line | Polygon Equivalent | Risk | Effort | API Savings |
|----------|----------|-----------|-------------------|------|--------|-------------|
| **1** | `build_session_snapshot()` FMP quote | unified.py:488,530 | Polygon snapshot `day.o/h/l/v` + `prevDay.c` | LOW-MED | S | HIGH (1-2 calls/symbol) |
| **2** | Gap recalc `previousClose` | scanner:671 | Polygon snapshot `prevDay.c` | LOW | S | MED (1 call/symbol) |
| **3** | Former runner daily bars | scanner:1095 | `polygon.get_daily_bars()` | LOW | XS | LOW (1 call/symbol, cached) |
| **4** | News headlines | unified.py:837 | `polygon.get_news()` | MED | S | LOW (add as source, don't remove FMP yet) |
| **5** | Pre-market gainers | unified.py:614 | Already primary via Polygon | LOW | XS | N/A (already done) |

### Cannot Migrate — Keep FMP

| FMP Call | Reason |
|----------|--------|
| Float shares (`stable/shares-float`) | Polygon has no float data |
| ETF list (`etf/list`) | No bulk ETF endpoint in Polygon |
| Country profile (`profile/{symbol}`) | Polygon lacks country field; low call volume (30-day cache) |

### Already Migrated

| Feature | Status |
|---------|--------|
| 200 EMA calculation | ✅ Uses `polygon.get_daily_bars()` exclusively (L1153) |
| Top gainers (primary) | ✅ Polygon gainers checked first in scan flow (L618-628) |
| Quote cross-validation | ✅ Polygon is primary source, FMP is fallback only (L107-157) |

---

## E. Architectural Recommendations

### 1. Fix Layer Violations (Effort: M)
The scanner directly accesses `self.market_data.fmp._get()` and `self.market_data.polygon.get_daily_bars()` instead of going through unified interface methods. This tight coupling will make every migration a scanner-level code change.

**Recommendation:** Add unified methods like `get_prev_close()` and `get_session_ohlv()` that handle Polygon→FMP fallback internally.

### 2. Add Polygon `previousClose` Extraction (Effort: XS)
The `PolygonAdapter.get_quote()` already fetches `prevDay.c` but doesn't expose it. Either:
- Add `prev_close` field to the `Quote` protocol, OR
- Add `PolygonAdapter.get_prev_close(symbol)` method

### 3. Batch Snapshot Migration (Effort: M)
The biggest win is migrating `build_session_snapshot()` to Polygon. This function is called for **every symbol** during evaluation. Currently it makes 2 FMP calls (one `get_quote`, one `_get("quote/{symbol}")`). A single Polygon snapshot call returns all the same data.

---

## F. Verification Commands

All findings were verified by code inspection. Key verification commands for the Audit Validator:

```powershell
# Finding 1: Float shares — direct FMP httpx call
Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern "financialmodelingprep.com/stable/shares-float"

# Finding 2: Former runner — direct FMP daily bars bypass
Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern "self.market_data.fmp.get_daily_bars"

# Finding 3: Country — direct FMP profile
Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern "self.market_data.fmp.get_country"

# Finding 4: Gap recalc — direct FMP quote bypass
Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern 'self.market_data.fmp._get'

# Finding 5: ETF list
Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern "self.market_data.fmp.get_etf_symbols"

# Finding 6: Session snapshot — FMP calls in unified
Select-String -Path "nexus2\adapters\market_data\unified.py" -Pattern "self.fmp"

# Finding 7: Headlines — FMP in unified
Select-String -Path "nexus2\adapters\market_data\unified.py" -Pattern "self.fmp.get_recent_headlines"

# Finding 8: Pre-market gainers
Select-String -Path "nexus2\adapters\market_data\unified.py" -Pattern "self.fmp.get_premarket_gainers"

# Verify Polygon already used for 200 EMA
Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern "self.market_data.polygon.get_daily_bars"

# Verify Polygon already first for gainers
Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern "self.market_data.polygon.get_gainers"

# Verify Polygon adapter has news
Select-String -Path "nexus2\adapters\market_data\polygon_adapter.py" -Pattern "def get_news"

# Verify Polygon adapter comment about float
Select-String -Path "nexus2\adapters\market_data\polygon_adapter.py" -Pattern "Does NOT include float"
```
