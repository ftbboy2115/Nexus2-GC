# Wave 1.5 Code Audit Report

**Auditor:** Claude (Code Auditor Agent)
**Date:** 2026-02-08
**Scope:** 10 files across 2 commits (`c8b47df` backend, `4056afc` frontend)
**Mode:** Read-only forensic review — no code modified

---

## Summary

| Metric | Value |
|--------|-------|
| Files audited | 10 |
| Claims verified | 38 |
| Issues found | 6 |
| Critical | 1 |
| Medium | 3 |
| Low | 2 |
| **Overall Rating** | **MEDIUM** — One critical log-level violation per project mandate; remainder are quality/hardening items |

---

## Backend Audit

### 1. ET→UTC Date Filter Conversion — `data_routes.py`

#### Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 1 | `et_to_utc` imported | ✅ PASS | L12: `from nexus2.utils.time_utils import et_to_utc, EASTERN` |
| 2 | NAC Trades uses `et_to_utc` for both date params | ✅ PASS | L180: `et_to_utc(et_start)`, L183: `et_to_utc(et_end)` |
| 3 | Warrior Trades uses `et_to_utc` for both date params | ✅ PASS | L917: `et_to_utc(et_start)`, L920: `et_to_utc(et_end)` |
| 4 | Quote Audits uses `et_to_utc` for both date params | ✅ PASS | L1050: `et_to_utc(et_start)`, L1053: `et_to_utc(et_end)` |
| 5 | Invalid date edge cases handled | ✅ PASS | `except ValueError` at L350, L359, L533, L541, L661, L669 — skips filter on bad input |

**Verification command:**
```powershell
Select-String -Path "nexus2\api\routes\data_routes.py" -Pattern "et_to_utc|ZoneInfo|except ValueError"
```

#### Issues Found

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| 1 | LOW | **Inconsistent conversion approach.** Some endpoints (Warrior Scan History L341, Catalyst Audits L525, AI Comparisons L653) use inline `ZoneInfo` conversion instead of the `et_to_utc()` helper. Functionally equivalent but inconsistent — extraction opportunity. | L323-359, L504-541, L637-669 |

---

### 2. Mock Market Notes Endpoints — `warrior_routes.py`

#### Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 6 | PUT `/test-case-notes` validates field whitelist | ✅ PASS | L987-989: `ALLOWED_FIELDS = {"notes", "description"}` with HTTPException(400) |
| 7 | PUT `/test-case-notes` validates case_id exists | ✅ PASS | L1010-1011: HTTPException(404) if `not found` |
| 8 | Pydantic `Field(...)` enforces required params | ✅ PASS | L966: `case_id: str = Field(...)`, L973: same pattern |
| 9 | File paths are safe (no path traversal) | ✅ PASS | L991, L1030, L1051: Paths built from `Path(__file__)` — `case_id` only used as dict key (L1005, L1061), never in path construction |
| 10 | YAML read/write has error handling | ✅ PASS | L995-999: try/except → HTTPException(500) for parse, L1013-1017: same for write |
| 11 | JSON notes write has error handling | ✅ PASS | L1063-1067: try/except → HTTPException(500) |
| 12 | GET `/notes` handles missing file | ✅ PASS | L1033: `if notes_path.exists()` check, returns empty string |

**Verification command:**
```powershell
Select-String -Path "nexus2\api\routes\warrior_routes.py" -Pattern "ALLOWED_FIELDS|case_id|HTTPException|yaml_path|notes_path"
```

#### Issues Found

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| 2 | MEDIUM | **Silent exception swallowing in GET `/notes`.** L1037-1038: `except Exception: notes_data = {}` — file corruption or permission errors silently return empty data. Should log a warning. | L1037-1038 |
| 3 | LOW | **No `case_id` sanitization.** While `case_id` is never used in file paths (safe from traversal), it's used as a JSON dict key with no length or character constraints. Unlikely exploit but unbounded. | L1061 |

---

### 3. Scanner Polygon Integration — `warrior_scanner_service.py`

#### Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 13 | Polygon gainers added first in priority order | ✅ PASS | L616-624: `polygon_gainers` iterated before FMP gainers (L628), actives (L635), and Alpaca (L642) |
| 14 | Dedup uses `seen` set | ✅ PASS | L612: `seen = set()`, L621: `if sym not in seen` |
| 15 | Polygon call wrapped in try/except | ✅ PASS | L616: `try:`, L624: `except Exception as e:` |
| 16 | Error does NOT crash scanner | ✅ PASS | Exception caught, scanner continues to FMP/Alpaca sources |

**Verification command:**
```powershell
Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern "_cached|polygon_gainers|scan_logger\.(debug|warning|error)"
```

#### Issues Found

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| 4 | **CRITICAL** | **Polygon error logged as `scan_logger.debug`, not WARNING/ERROR.** L625: `scan_logger.debug(f"POLYGON GAINERS \| Error: {e}")`. Per project mandate: _"If a safety check fails, BLOCK THE TRADE"_ and _"NEVER use `logger.debug` for conditions that affect trading outcomes."_ A data source failure directly affects scanner coverage and trade discovery. Must be `scan_logger.warning` or `scan_logger.error`. | L625 |

---

### 4. Scanner Caching — `warrior_scanner_service.py`

#### Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 17 | `_cached()` method exists with TTL logic | ✅ PASS | L508-519: Checks `(now - cached_at).total_seconds() < ttl_seconds` |
| 18 | ETF set cached at 86400s (24h) | ✅ PASS | L694: `self._cached("etf_set", 86400, ...)` |
| 19 | Country cached at 2592000s (30 days) | ✅ PASS | L853: `self._cached(f"country:{symbol}", 2592000, ...)` |
| 20 | Runner cached at 21600s (6h) | ✅ PASS | L961: `self._cached(f"runner:{symbol}", 21600, ...)` |
| 21 | Float cached at 86400s (24h) | ✅ PASS | L1202: `self._cached(f"float:{ctx.symbol}", 86400, ...)` |
| 22 | EMA200 cached at 21600s (6h) | ✅ PASS | L1620: `self._cached(f"ema200:{ctx.symbol}", 21600, ...)` |
| 23 | Cache is instance-level (not global) | ✅ PASS | L506: `self._cache: Dict[str, Tuple[Any, datetime]] = {}` |

#### Issues Found

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| 5 | MEDIUM | **`_cached()` is not thread-safe.** Two concurrent calls could both see a cache miss and invoke `fetch_fn()` simultaneously. Low real-world risk since scanner runs sequentially, but the method has no locking mechanism. Document as tech debt. | L508-519 |

---

## Frontend Audit

### 5. Country Names — `countryNames.ts` + `data-explorer.tsx`

#### Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 24 | `COUNTRY_NAMES` exported as `Record<string, string>` | ✅ PASS | `countryNames.ts` L3: `export const COUNTRY_NAMES: Record<string, string> = {` |
| 25 | Imported correctly in data-explorer | ✅ PASS | `data-explorer.tsx` L18: `import { COUNTRY_NAMES } from '../utils/countryNames'` |
| 26 | Used for country name display | ✅ PASS | `data-explorer.tsx` L1308: `COUNTRY_NAMES[rawVal as string]` with fallback |

---

### 6. Scrollbars & Clipping — `DataExplorer.module.css`

#### Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 27 | `.tableContainer` has `min-height` | ✅ PASS | L171: `min-height: 300px;` |
| 28 | Auto-hiding scrollbars (thin style) | ✅ PASS | L172: `scrollbar-width: thin;`, L173: `scrollbar-color: rgba(255, 255, 255, 0.15) transparent;` |
| 29 | Webkit scrollbar overrides present | ✅ PASS | L176-190: `::-webkit-scrollbar`, `::-webkit-scrollbar-track`, `::-webkit-scrollbar-thumb` |

**Verification command:**
```powershell
Select-String -Path "nexus2\frontend\src\styles\DataExplorer.module.css" -Pattern "min-height|scrollbar"
```

---

### 7. Card Visibility Toggle — `warrior.tsx` + `Warrior.module.css`

#### Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 30 | `hiddenCards` state initialized from localStorage | ✅ PASS | L139-142: `useState<Set<string>>` with `localStorage.getItem('warrior-card-visibility')` |
| 31 | `toggleCard` persists to localStorage | ✅ PASS | L148-153: `localStorage.setItem('warrior-card-visibility', JSON.stringify(...))` |
| 32 | `isCardVisible` helper exists | ✅ PASS | L158: `const isCardVisible = (id: string) => !hiddenCards.has(id)` |
| 33 | localStorage key is unique | ✅ PASS | Key `'warrior-card-visibility'` — namespaced to Warrior page |
| 34 | Toggle wired to UI | ✅ PASS | L552: `onChange={() => toggleCard(id)}` |

---

### 8. Mock Market Notes UI — `MockMarketCard.tsx`

#### Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 35 | Cliffnotes editing state exists | ✅ PASS | L99-100: `editingField` state, L113: `saveCliffnotes` handler |
| 36 | Per-test-case notepad state exists | ✅ PASS | L103-106: `showNotepad`, `notepadText`, `notepadLoading` |
| 37 | Global notepad state exists | ✅ PASS | L108-111: `showGlobalNotepad`, `globalNotepadText`, `globalNotepadLoading` |
| 35b | API calls use correct endpoints | ✅ PASS | L116: `/warrior/mock-market/test-case-notes` (PUT), L133: `/warrior/mock-market/notes?case_id=` (GET), L148: `/warrior/mock-market/notes` (PUT), L162: `/warrior/mock-market/notes?case_id=_global` (GET) |
| 35c | XSS protection — notes rendered safely | ✅ PASS | Notes rendered via `value={notepadText}` in `<textarea>` — not `dangerouslySetInnerHTML` |

---

### 9. Clickable Ticker — `ChartPanel.tsx`

#### Claims Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| 36 | TradingView URL is correct | ✅ PASS | L347: `https://www.tradingview.com/chart/D7F9NNnO/?symbol=${symbol}` |
| 37 | Opens in new tab | ✅ PASS | L347: `window.open(..., '_blank')` |

**Verification command:**
```powershell
Select-String -Path "nexus2\frontend\src\components\warrior\ChartPanel.tsx" -Pattern "tradingview|noopener|window.open|_blank"
```

#### Issues Found

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| 6 | MEDIUM | **Missing `noopener` in `window.open()`.** Uses `window.open(url, '_blank')` without passing `'noopener,noreferrer'` as the third argument. Modern browsers auto-apply `noopener` for cross-origin opens, but explicit is safer. Should be: `window.open(url, '_blank', 'noopener,noreferrer')`. | L347 |

---

## Cross-File Analysis

### API Contract Alignment

| Frontend Call | Backend Endpoint | Match |
|---------------|------------------|-------|
| `fetch('/warrior/mock-market/test-case-notes', { method: 'PUT' })` | `@router.put("/mock-market/test-case-notes")` | ✅ |
| `fetch('/warrior/mock-market/notes?case_id=...')` | `@router.get("/mock-market/notes")` | ✅ |
| `fetch('/warrior/mock-market/notes', { method: 'PUT' })` | `@router.put("/mock-market/notes")` | ✅ |

### Extraction Opportunities

1. **ET→UTC inline conversion** (3 endpoints in `data_routes.py`) could be consolidated into the existing `et_to_utc()` helper — currently only NAC/Warrior/Quote endpoints use the helper, while Warrior Scan History, Catalyst Audits, and AI Comparisons use inline `ZoneInfo`.

2. **Scanner `_cached()` method** is a good candidate for extraction into a shared `utils/cache.py` with optional thread-safety.

---

## Issues Summary

| # | Severity | File | Issue |
|---|----------|------|-------|
| 1 | LOW | `data_routes.py` | Inconsistent ET→UTC approach (some inline, some helper) |
| 2 | MEDIUM | `warrior_routes.py` | Silent exception swallowing in GET `/notes` (L1037-1038) |
| 3 | LOW | `warrior_routes.py` | No `case_id` length/format validation |
| 4 | **CRITICAL** | `warrior_scanner_service.py` | Polygon error logged as `debug` instead of `warning`/`error` (L625) |
| 5 | MEDIUM | `warrior_scanner_service.py` | `_cached()` not thread-safe |
| 6 | MEDIUM | `ChartPanel.tsx` | Missing `noopener,noreferrer` in `window.open()` |

---

## Overall Rating: **MEDIUM**

> All Wave 1.5 features are implemented correctly. The critical finding (#4) violates the project's non-negotiable mandate (_"NEVER use `logger.debug` for conditions that affect trading outcomes"_). Polygon data source failures silently degrade scanner coverage. Remaining issues are hardening and consistency items that should be addressed in a follow-up commit.

### Recommended Priority

1. **Immediate:** Fix Polygon error log level from `debug` → `warning` (Issue #4)
2. **Next sprint:** Add logging to silent exception catch in notes GET (Issue #2), add `noopener` to `window.open` (Issue #6)
3. **Tech debt:** Consolidate inline ZoneInfo to `et_to_utc()` helper (Issue #1), add thread safety docs to `_cached()` (Issue #5)
