# Audit: Catalyst Evaluation Pipeline

> **Auditor:** Code Auditor Agent  
> **Date:** 2026-02-20  
> **Scope:** `warrior_scanner_service.py` catalyst pipeline + supporting modules  

---

## 1. Complete Flow Diagram

```
_evaluate_symbol() [warrior_scanner_service.py:822]
    │
    │  headlines = market_data.get_merged_headlines(symbol, days=5)  [L920-924]
    │             Sources: FMP + Alpaca/Benzinga + Yahoo Finance + Finviz
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  _evaluate_catalyst_pillar(ctx, tracker, headlines)  [L1307-1426]  │
│                                                                     │
│  if headlines:                                                      │
│    ├── classifier.has_positive_catalyst(headlines) → regex          │
│    │   └── if confidence >= 0.6:                                   │
│    │       ctx.has_catalyst = True                       [L1335]   │
│    │       ctx.catalyst_source = "regex"                 [L1337]   │
│    │       ctx.catalyst_type = best_type                 [L1336]   │
│    │       ★ SHORT-CIRCUITS AI — has_catalyst is now True          │
│    │   └── else: ctx.catalyst_desc = "Weak catalyst..."  [L1348]  │
│    │                                                                │
│    ├── classifier.has_negative_catalyst(headlines)                  │
│    │   └── if negative AND no bypass:                              │
│    │       return "negative_catalyst"  → EARLY EXIT     [L1401]   │
│    │       _write_scan_result_to_db(FAIL)                [L1400]  │
│    │                                                                │
│  if NOT ctx.has_catalyst:                                           │
│    ├── fmp.has_recent_earnings(symbol)                   [L1404]   │
│    │   └── if has_earnings:                                        │
│    │       ctx.has_catalyst = True                       [L1409]   │
│    │       ctx.catalyst_source = "calendar"              [L1411]   │
│    │       log_headline_evaluation(PASS, earnings)       [L1415]  │
│    │       ★ SHORT-CIRCUITS AI — has_catalyst is now True          │
│    │                                                                │
│  if require_catalyst AND NOT ctx.has_catalyst AND include_runners: │
│    ├── _is_former_runner(symbol)                         [L1418]   │
│    │   └── if former_runner:                                       │
│    │       ctx.has_catalyst = True                       [L1420]   │
│    │       ctx.catalyst_source = "former_runner"         [L1422]   │
│    │       ★ SHORT-CIRCUITS AI — has_catalyst is now True          │
│    │                                                                │
│  return None (never rejects for positive catalyst)      [L1426]   │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  _run_multi_model_catalyst_validation(ctx, headlines)  [L1428-1521]│
│                                                                     │
│  GUARD: if NOT headlines OR NOT enable_multi_model_comparison:      │
│         return immediately                               [L1436]   │
│                                                                     │
│  headline_cache = get_headline_cache()                   [L1439]   │
│                                                                     │
│  ┌─ CACHE HIT: headline_cache.has_valid_catalyst(symbol) [L1442]  │
│  │  └── if cached_valid AND NOT ctx.has_catalyst:                  │
│  │      ctx.has_catalyst = True                          [L1444]   │
│  │      ctx.catalyst_source = "ai"                       [L1446]   │
│  │      log_headline_evaluation(PASS)                    [L1450]  │
│  │      return  ← EXITS EARLY                           [L1453]   │
│  │                                                                  │
│  ┌─ FILTER: new_headlines = cache.get_new_headlines()    [L1456]   │
│  │  (removes already-seen headlines by text hash)                   │
│  │                                                                  │
│  │  if new_headlines AND NOT ctx.has_catalyst:           [L1458]   │
│  │  ★ THIS IS THE KEY SHORT-CIRCUIT ★                              │
│  │  If has_catalyst was set by regex/calendar/runner above,         │
│  │  the entire multi-model loop is SKIPPED.                         │
│  │                                                                  │
│  │  for headline in new_headlines[:3]:                    [L1473]   │
│  │    ├── regex_match = classifier.classify(headline)     [L1475]  │
│  │    ├── multi_validator.validate_sync(...)              [L1482]  │
│  │    │   ├── Runs Flash-Lite AI                                   │
│  │    │   ├── If regex≠flash: calls Pro tiebreaker                 │
│  │    │   ├── Writes CatalystAudit to DB        [validator:927]    │
│  │    │   └── Writes AIComparison to DB         [validator:832]    │
│  │    │                                                             │
│  │    ├── headline_cache.add(symbol, headline, results)  [L1490]   │
│  │    │                                                             │
│  │    └── if final_valid AND NOT ctx.has_catalyst:       [L1500]   │
│  │        ctx.has_catalyst = True                        [L1501]   │
│  │        ctx.catalyst_source = "ai"                     [L1503]   │
│  │        log_headline_evaluation(PASS)                  [L1507]  │
│  │        break                                          [L1508]   │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  _run_legacy_ai_fallback(ctx, headlines)                [L1523-1559]│
│                                                                     │
│  GUARDS (ALL must pass):                                 [L1531]   │
│    - headlines exist                                                │
│    - use_ai_catalyst_fallback = True (default: True)               │
│    - NOT ctx.has_catalyst                                           │
│  EXCLUSIVE:                                              [L1533]   │
│    - if enable_multi_model_comparison: return                       │
│      (multi-model takes precedence)                                 │
│                                                                     │
│  ┌─ CACHE HIT: catalyst_cache.get(symbol)                [L1537]  │
│  │  └── if cached.is_valid AND NOT has_catalyst:                   │
│  │      ctx.has_catalyst = True                          [L1540]   │
│  │      ctx.catalyst_type = f"cached_{cached_type}"      [L1541]  │
│  │      ⚠ NO catalyst_source assigned (will be None)               │
│  │                                                                  │
│  └─ NO CACHE: ai_validator.validate_headlines()          [L1547]  │
│     └── if ai_valid:                                               │
│         ctx.has_catalyst = True                          [L1553]   │
│         ctx.catalyst_type = f"ai_{ai_type}"              [L1554]  │
│         ⚠ NO catalyst_source assigned (will be None)               │
│         ⚠ NO CatalystAudit or AIComparison DB writes               │
└─────────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Final catalyst check                                    [L936]    │
│                                                                     │
│  if require_catalyst AND NOT ctx.has_catalyst:                      │
│    ├── log_headline_evaluation(FAIL)                     [L946]    │
│    ├── _write_scan_result_to_db(FAIL, "no_catalyst")     [L950]   │
│    └── return None (rejected)                                       │
│                                                                     │
│  (continues to dilution check, 200 EMA, build candidate...)        │
│                                                                     │
│  PASS path (L1063-1072):                                            │
│    ├── log_headline_evaluation(PASS, catalyst_type)      [L1064]  │
│    └── _write_scan_result_to_db(PASS)                    [L1067]  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Every DB Write & Logging Call

### 2a. Database Writes

| What | Where | Trigger | Data Written |
|------|-------|---------|-------------|
| `WarriorScanResult` (PASS) | `warrior_scanner_service.py:1067` | Symbol passes all pillars | gap_pct, rvol, score, catalyst_type, **catalyst_source**, price, etc. |
| `WarriorScanResult` (FAIL) | `warrior_scanner_service.py:950` | No catalyst found | reason="no_catalyst" |
| `WarriorScanResult` (FAIL) | `warrior_scanner_service.py:1400` | Negative catalyst | reason="negative_catalyst:{type}" |
| `WarriorScanResult` (FAIL) | `warrior_scanner_service.py:890,1242,1301,969` | Other pillar failures | chinese/float/rvol/dilution |
| `CatalystAudit` | `ai_catalyst_validator.py:927` | **Only from `validate_sync()`** | symbol, result, headline, match_type, confidence=method |
| `AIComparison` | `ai_catalyst_validator.py:832` | **Only from `_log_comparison()`** | symbol, headline, regex/flash/pro results, winner |

**Finding:** `CatalystAudit` write at `ai_catalyst_validator.py:927`:
```python
db.add(CatalystAudit(
    timestamp=now_utc(),
    symbol=symbol,
    result="PASS" if final_valid else "FAIL",
    headline=headline[:200] if headline else None,
    article_url=article_url,
    source=None,  # Source not tracked in validate_sync
    match_type=final_type,
    confidence=method,  # Use method as confidence (consensus/tiebreaker)
))
```
**Verified with:** `Select-String -Path "nexus2\domain\automation\ai_catalyst_validator.py" -Pattern "CatalystAudit"`

**Finding:** `AIComparison` write at `ai_catalyst_validator.py:832`:
```python
db.add(AIComparisonDB(
    timestamp=now_utc(),
    symbol=result.symbol,
    headline=result.headline[:200] if result.headline else None,
    article_url=result.article_url,
    source=None,
    regex_result=result.regex_type if result.regex_type else "FAIL",
    flash_result="PASS" if flash_result and flash_result.is_valid else "FAIL" if flash_result else None,
    pro_result="PASS" if pro_result and pro_result.is_valid else "FAIL" if pro_result else None,
    final_result=final_result,
    winner=winner,
))
```
**Verified with:** `Get-ChildItem -Path "nexus2" -Filter "*.py" -Recurse | Select-String -Pattern "AIComparison\(" | Select-Object -First 20`

### 2b. File-Based Logging Calls

| Function | Where Called | What It Logs | Destination |
|----------|-------------|-------------|------------|
| `log_headline_evaluation` | `warrior_scanner_service.py:946` | FAIL — no catalyst | File: `catalyst_audit.log` |
| `log_headline_evaluation` | `warrior_scanner_service.py:1064` | PASS — final pass | File: `catalyst_audit.log` |
| `log_headline_evaluation` | `warrior_scanner_service.py:1415` | PASS — earnings calendar | File: `catalyst_audit.log` |
| `log_headline_evaluation` | `warrior_scanner_service.py:1450` | PASS — headline cache hit | File: `catalyst_audit.log` |
| `log_headline_evaluation` | `warrior_scanner_service.py:1507` | PASS — multi-model validated | File: `catalyst_audit.log` |
| `_log_comparison` (JSONL) | `ai_catalyst_validator.py:800-806` | Full comparison data | File: `data/catalyst_comparison.jsonl` |

**Finding:** `log_headline_evaluation` at `catalyst_classifier.py:314`:
```python
def log_headline_evaluation(symbol, headlines, final_result, final_type=None):
    catalyst_audit_logger.info(f"=== {symbol} | Result: {final_result} | Type: {final_type or 'none'} ===")
    for i, headline in enumerate(headlines[:5], 1):
        match = classifier.classify(headline)
        # logs to file-based logger, NOT to telemetry DB
```
**Verified with:** `Select-String -Path "nexus2\domain\automation\catalyst_classifier.py" -Pattern "log_headline_evaluation"`
**Conclusion:** This function writes to a file-based logger only, NOT to the `catalyst_audits` DB table.

### 2c. HeadlineCache Writes

| Method | Where Called | What It Stores |
|--------|-------------|---------------|
| `headline_cache.add()` | `warrior_scanner_service.py:1490` | Success: validated headline with regex/flash/method |
| `headline_cache.add()` | `warrior_scanner_service.py:1513` | Error: headline marked invalid |

**Finding:** `HeadlineCache` at `ai_catalyst_validator.py:173`:
```python
class HeadlineCache:
    """Persistent cache for headlines and their validation results.
    Headlines are stored by symbol with text hash for deduplication.
    Cache persists to JSON file for survival across restarts.
    TTL is 14 days."""
```
**Conclusion:** HeadlineCache is disk-backed JSON (`data/headline_cache.json`), keyed by symbol, uses MD5 hash for dedup. It stores `is_valid`, `catalyst_type`, `regex_passed`, `flash_passed`, and `method` for each headline.

---

## 3. Every `ctx.has_catalyst` Check That Gates Downstream Logic

| Line | Location | Gate Effect |
|------|----------|------------|
| 936 | `_evaluate_symbol` | Final rejection: if `require_catalyst AND NOT has_catalyst` → FAIL |
| 1335 | `_evaluate_catalyst_pillar` | Set True by regex (confidence ≥ 0.6) |
| 1362 | `_evaluate_catalyst_pillar` | Negative catalyst bypass: only if `has_catalyst AND type not none` |
| 1404 | `_evaluate_catalyst_pillar` | Earnings check: only if `NOT has_catalyst` |
| 1409 | `_evaluate_catalyst_pillar` | Set True by earnings calendar |
| 1418 | `_evaluate_catalyst_pillar` | Former runner: only if `require_catalyst AND NOT has_catalyst` |
| 1420 | `_evaluate_catalyst_pillar` | Set True by former runner |
| 1443 | `_run_multi_model` | Cache hit: only if `NOT has_catalyst` → **SKIPPED if regex set it** |
| 1458 | `_run_multi_model` | New headlines: only if `NOT has_catalyst` → **SKIPPED if regex set it** |
| 1500 | `_run_multi_model` | validate_sync result: only if `NOT has_catalyst` |
| 1531 | `_run_legacy_ai_fallback` | Entry guard: exits if `has_catalyst` → **SKIPPED if regex set it** |
| 1539 | `_run_legacy_ai_fallback` | Cache check: only if `NOT has_catalyst` |

**Verified with:** `Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern "has_catalyst"`

---

## 4. Every Setting That Controls Flow (Feature Flags)

| Setting | Default | Where Used | Effect |
|---------|---------|-----------|--------|
| `require_catalyst` | `True` | L936, L1418 | If True, symbols without catalyst are rejected |
| `enable_multi_model_comparison` | `True` | L1436, L1533 | Gates multi-model path; blocks legacy fallback |
| `use_ai_catalyst_fallback` | `True` | L1531 | Gates legacy single-model AI |
| `include_former_runners` | `False` | L1418 | Allow former runners as catalyst substitute |
| `catalyst_lookback_days` | `5` | L922, L1341, L1406, L1466 | How far back to search for headlines |
| `comparison_models` | `["flash_lite", "pro"]` | L149, L153 | Which AI models to use for comparison |
| `allow_offering_for_reverse_splits` | (in settings) | L1355 | Bypass negative offering for RS stocks |
| `momentum_override_rvol` | (in settings) | L1375 | RVOL threshold for momentum override |
| `momentum_override_gap` | (in settings) | L1375 | Gap threshold for momentum override |

**Verified with:** `Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern "enable_multi_model|use_ai_catalyst|comparison_models|require_catalyst|include_former_runners|catalyst_lookback"`

---

## 5. Which Paths Generate Audit/Comparison Data

| Path | CatalystAudit DB | AIComparison DB | HeadlineCache | File Log |
|------|:---:|:---:|:---:|:---:|
| **Regex match (conf ≥ 0.6)** | ❌ | ❌ | ❌ | ✅ (final pass/fail only) |
| **Earnings calendar** | ❌ | ❌ | ❌ | ✅ |
| **Former runner** | ❌ | ❌ | ❌ | ❌ |
| **Multi-model validate_sync** | ✅ | ✅ | ✅ | ✅ |
| **Multi-model cache hit** | ❌ | ❌ | ❌ | ✅ |
| **Legacy AI (disabled by default)** | ❌ | ❌ | ❌ | ❌ |
| **No catalyst (final reject)** | ❌ | ❌ | ❌ | ✅ |

---

## 6. Summary: What Data Is LOST Due to Short-Circuiting

### The Core Problem

When the regex classifier finds a positive catalyst with confidence ≥ 0.6 (line 1334), `ctx.has_catalyst` is set to `True` at line 1335. This prevents:

1. **Multi-model validation** from running (guarded by `not ctx.has_catalyst` at L1458)
2. **CatalystAudit** DB writes (only happen inside `validate_sync`, which is inside the multi-model loop)
3. **AIComparison** DB writes (only happen inside `_log_comparison`, called from `validate_sync`)
4. **HeadlineCache** entries from being created (only written inside the multi-model loop at L1490)

### What Is Lost

| Lost Data | Impact |
|-----------|--------|
| **No Regex vs AI comparison** for regex-resolved symbols | Cannot train regex accuracy — no ground truth from AI to compare against |
| **No CatalystAudit records** for regex-resolved symbols | "Catalyst Audits" tab in Data Explorer shows nothing for these symbols |
| **No AIComparison records** for regex-resolved symbols  | "AI Comparisons" tab shows nothing for these symbols |
| **No HeadlineCache entries** for regex-resolved headlines | Headlines re-evaluated on every scan cycle instead of being cached |

### Same Problem for Earnings Calendar

When `has_recent_earnings()` sets `has_catalyst = True` at line 1409, the same short-circuit prevents multi-model from running. Earnings-resolved symbols also produce **zero** CatalystAudit/AIComparison/HeadlineCache data.

### Quantitative Impact

Under default settings (`enable_multi_model_comparison = True`, `include_former_runners = False`):

- **Regex** is the primary fast path — most symbols with clear headlines (earnings beat, FDA, contract) match here
- **Earnings calendar** catches earnings-driven moves without headlines
- **Multi-model** only runs for symbols where regex **failed** (confidence < 0.6) AND the earnings calendar found nothing
- This means **most of the training data that the system was designed to generate is never created**

### The Design Intent vs. Reality

The module docstring in `ai_catalyst_validator.py:1-66` describes a **parallel assessment** system where regex and AI run side-by-side to generate comparison data. But the actual implementation is **sequential with short-circuiting**: regex runs first, and if it succeeds, AI never runs.

---

## A. File Inventory

| File | Lines | Key Components |
|------|-------|---------------|
| `warrior_scanner_service.py` | 1840 | `_evaluate_catalyst_pillar`, `_run_multi_model_catalyst_validation`, `_run_legacy_ai_fallback` |
| `ai_catalyst_validator.py` | 974 | `HeadlineCache`, `CatalystCache`, `AICatalystValidator`, `MultiModelValidator` |
| `catalyst_classifier.py` | 334+ | `get_classifier()`, `log_headline_evaluation()`, regex patterns |
| `unified.py` | 932+ | `get_merged_headlines()` (FMP + Alpaca + Yahoo + Finviz) |
| `telemetry_db.py` | 252 | `CatalystAudit`, `AIComparison`, `WarriorScanResult` models |
| `data_routes.py` | 700+ | API endpoints to read CatalystAudit and AIComparison |

## B. Dependency Graph

```
warrior_scanner_service.py
  └── imports from:
      ├── catalyst_classifier.py → get_classifier(), log_headline_evaluation()
      ├── ai_catalyst_validator.py → get_headline_cache(), get_multi_validator(),
      │                              get_catalyst_cache(), get_ai_validator()
      └── unified.py → UnifiedMarketData.get_merged_headlines()

ai_catalyst_validator.py
  └── imports from:
      └── telemetry_db.py → AIComparison, CatalystAudit, get_telemetry_session()

data_routes.py (read-only consumer)
  └── imports from:
      └── telemetry_db.py → CatalystAudit, AIComparison, get_telemetry_session()
```

## C. Headline Sources in `get_merged_headlines`

**Finding:** `unified.py:860-932`:
```python
def get_merged_headlines(self, symbol, days=5, alpaca_broker=None):
    # 1. FMP headlines (existing source)
    fmp_headlines = self.fmp.get_recent_headlines(symbol, days=days)
    # 2. Alpaca headlines (Benzinga-powered, better micro-cap coverage)
    alpaca_news = alpaca_broker.get_news(symbol, limit=10, days=days)
    # 3. Yahoo Finance headlines
    get_yahoo_headlines(symbol, days=days)
    # 4. Finviz headlines
    get_finviz_headlines(symbol, limit=5)
```
**Verified with:** `Get-ChildItem -Path "nexus2" -Filter "*.py" -Recurse | Select-String -Pattern "def get_merged_headlines"`
**Conclusion:** 4 sources merged with set-based deduplication (normalized lowercase).

---

## D. Refactoring Recommendations

| # | Issue | Impact | Effort | Recommendation |
|---|-------|--------|--------|---------------|
| 1 | **Multi-model never runs when regex succeeds** | CRITICAL: No comparison data generated for training | M | Run `validate_sync` for ALL headlines regardless of `ctx.has_catalyst` state. Use regex result for trading decision, but still generate comparison data. |
| 2 | **Legacy AI path sets no `catalyst_source`** | Minor: missing telemetry data | S | Add `ctx.catalyst_source = "ai"` in legacy path (L1540, L1553) |
| 3 | **CatalystAudit/AIComparison never written for regex/calendar/runner** | HIGH: Data Explorer tabs are incomplete | M | Write audit records from all paths, not just multi-model |
| 4 | **HeadlineCache not populated for regex-resolved headlines** | MEDIUM: Same headlines re-evaluated each scan | S | Add `headline_cache.add()` after regex match in `_evaluate_catalyst_pillar` |
