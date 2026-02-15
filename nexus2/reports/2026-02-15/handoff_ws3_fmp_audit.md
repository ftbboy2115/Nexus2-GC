# WS3: FMP→Polygon Data Provider Audit — Agent Handoff

**Agent**: Code Auditor
**Rule file**: `@agent-code-auditor.md`
**Priority**: Low (informational — no code changes)

---

## Objective

Audit every FMP API call in the Warrior Scanner to determine which can be migrated to Polygon. Clay pays $200/mo for Polygon Advanced tier and wants it prioritized as the primary data source. FMP should only be used where Polygon lacks equivalent data.

## Scope

Audit these files:

| File | Path |
|------|------|
| Scanner Service | `nexus2/domain/scanner/warrior_scanner_service.py` |
| Unified Market Data | `nexus2/adapters/market_data/unified.py` |
| FMP Adapter | `nexus2/adapters/market_data/fmp_adapter.py` |
| Polygon Adapter | `nexus2/adapters/market_data/polygon_adapter.py` |

## Known FMP Usage in Scanner (from coordinator research)

| Function | FMP Call | Line | Polygon Alternative? |
|----------|----------|------|---------------------|
| `_get_float_shares()` | `fmp.get_float_shares()` | L1052-1078 | ❌ Polygon lacks float data |
| `_is_former_runner()` | `fmp.get_daily_chart_bars()` | L1080-1107 | ✅ Polygon daily bars exist |
| `_get_country()` | `fmp.get_country()` | L1183-1188 | ❌ Polygon limited profiles |
| Catalyst headlines | `fmp.get_news_with_dates()` / `get_headlines_with_urls()` | L1283+ | ❓ Investigate Polygon news API |
| `build_session_snapshot()` | `fmp._get(f"quote/{symbol}")` | unified.py:466+ | ✅ Polygon snapshot API |
| Gap recalc in `scan()` | `fmp._get(f"quote/{symbol}")` for `previousClose` | L668 | ✅ Polygon previous close |
| ETF exclusion | `fmp.get_etf_symbols()` | L694 | ❌ FMP comprehensive ETF list |
| Pre-market gainers | `market_data.get_premarket_gainers()` | L590 | ✅ Already have `polygon.get_gainers()` |

## Investigation Questions

1. For each FMP call, does Polygon provide equivalent data quality and coverage?
2. What is the Polygon API call for each (endpoint, rate limits)?
3. Which migrations are safe (data parity) vs risky (different coverage)?
4. What's the recommended migration order (quick wins first)?

## Evidence Requirements

For EACH finding, provide:
- Exact file path and line number
- Exact FMP call being made
- Polygon equivalent (if exists) with API docs reference
- Migration risk level (LOW/MEDIUM/HIGH)

## Deliverable

Write findings to: `nexus2/reports/2026-02-15/audit_fmp_scanner_usage.md`
