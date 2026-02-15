# FMP→Polygon Migration Validation — Testing Specialist Handoff

**Agent**: Testing Specialist  
**Rule file**: `@agent-testing-specialist.md`  
**Priority**: HIGH — validate before commit/push

---

## Changes to Validate

Three FMP→Polygon migrations were implemented. Each needs independent verification.

### Migration 1: `build_session_snapshot()` → Polygon Snapshot (HIGHEST VALUE)

**File**: `nexus2/adapters/market_data/unified.py` (lines 466-530)  
**File**: `nexus2/adapters/market_data/polygon_adapter.py` (new method `get_session_snapshot`)

**What changed**:
- Added `PolygonAdapter.get_session_snapshot(symbol)` — single API call returning session OHLV, prev_close, last_price
- Rewrote `UnifiedMarketData.build_session_snapshot()` to use Polygon first, FMP as fallback
- Alpaca remains highest priority for `last_price`

**Verify**:
1. Polygon snapshot returns all required fields (session_open, session_high, session_low, session_volume, prev_close, last_price)
2. FMP fallback activates if Polygon returns None
3. Return dict shape is unchanged (same keys, same types)
4. Alpaca price overrides both Polygon and FMP for `last_price`

### Migration 2: Gap Recalc `previousClose` → Polygon

**File**: `nexus2/domain/scanner/warrior_scanner_service.py` (lines 670-673)

**What changed**:
```diff
-fmp_data = self.market_data.fmp._get(f"quote/{symbol}")
-if fmp_data and len(fmp_data) > 0:
-    prev_close = float(fmp_data[0].get("previousClose", 0))
-    if prev_close > 0:
+snap = self.market_data.polygon.get_session_snapshot(symbol)
+prev_close = snap["prev_close"] if snap else 0
+if prev_close > 0:
```

**Verify**:
1. `get_session_snapshot` returns dict with `prev_close` key
2. If snap is None, prev_close defaults to 0 safely
3. Indentation is correct after the change (the block that follows should still be inside the `if prev_close > 0:` check)

### Migration 3: Former Runner Daily Bars → Polygon

**File**: `nexus2/domain/scanner/warrior_scanner_service.py` (line 1094)

**What changed**:
```diff
-bars = self.market_data.fmp.get_daily_bars(symbol, limit=90)
+bars = self.market_data.polygon.get_daily_bars(symbol, limit=90)
```

**Verify**:
1. `polygon.get_daily_bars()` returns the same `List[OHLCV]` type as `fmp.get_daily_bars()`
2. Both have identical `limit` parameter semantics
3. The 200 EMA at L1153 already uses `polygon.get_daily_bars()` — confirms compatibility

---

## Verification Commands

```powershell
cd "c:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus"

# 1. Run all scanner tests
python -m pytest nexus2/tests/unit/scanners/ -v

# 2. Verify return type of polygon.get_session_snapshot matches build_session_snapshot usage
Select-String -Path "nexus2\adapters\market_data\polygon_adapter.py" -Pattern "def get_session_snapshot"
Select-String -Path "nexus2\adapters\market_data\unified.py" -Pattern "polygon.get_session_snapshot"

# 3. Verify no remaining FMP calls in gap recalc
Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern 'self.market_data.fmp._get\(f"quote'

# 4. Verify former runner uses polygon
Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern "self.market_data.fmp.get_daily_bars"
# Should return NO results (was the only FMP daily bars call)

# 5. Verify polygon daily bars return type matches
Select-String -Path "nexus2\adapters\market_data\polygon_adapter.py" -Pattern "def get_daily_bars"

# 6. Check indentation around gap recalc change
python -c "import ast; ast.parse(open('nexus2/domain/scanner/warrior_scanner_service.py').read()); print('SYNTAX OK')"
```

---

## Validation Report Format

```markdown
## Validation Report: FMP→Polygon Migrations

### Claims Verified
| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | build_session_snapshot returns same dict shape | PASS/FAIL | [command + output] |
| 2 | FMP fallback works when Polygon returns None | PASS/FAIL | [command + output] |
| 3 | Gap recalc uses Polygon prev_close correctly | PASS/FAIL | [command + output] |
| 4 | Former runner uses polygon.get_daily_bars | PASS/FAIL | [command + output] |
| 5 | No remaining FMP daily bar calls | PASS/FAIL | [command + output] |
| 6 | Syntax is valid | PASS/FAIL | [command + output] |
| 7 | All scanner tests pass | PASS/FAIL | [command + output] |

### Overall Rating
- **HIGH/MEDIUM/LOW**
```

Write findings to: `nexus2/reports/2026-02-15/validation_fmp_polygon_migrations.md`
