# Investigation: Zero/Default Metrics Across Data Explorer Tabs

**Date:** 2026-02-19  
**Investigator:** Backend Planner (Coordinator-initiated)  
**Scope:** All 9 Data Explorer tabs  

---

## Executive Summary

**Only the Warrior Scans tab has the "early-rejection writes default zeros" pattern.** All other tabs either use explicit-value writes, string storage, or file-based data sources that don't exhibit this issue. The root cause is that `EvaluationContext` defaults (`rvol=Decimal('0')`, `gap_pct=Decimal('0')`) get converted to `0.0` in the database when a rejection fires before the enriching pillar populates the field.

---

## Tab-by-Tab Analysis

### 1. Warrior Scans — ⚠️ AFFECTED

| Property | Value |
|----------|-------|
| **Endpoint** | `GET /data/warrior-scan-history` |
| **Data Source** | `telemetry.db` → `warrior_scan_results` table |
| **Model** | `WarriorScanResult` in [telemetry_db.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/db/telemetry_db.py) |
| **Writer** | [_write_scan_result_to_db](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py#L539-L581) |

**Root Cause:** The `_evaluate_symbol` method creates an `EvaluationContext` at line 841 with dataclass defaults, then progressively enriches it through pillar checks. When a pillar rejects the symbol, `_write_scan_result_to_db` is called with the partially-enriched `ctx`. Fields not yet enriched retain their defaults.

**Pillar Evaluation Order and Enrichment:**

| Order | Pillar | Enriches | Early-Reject Call Site |
|-------|--------|----------|----------------------|
| Pre | Snapshot | `session_volume`, `avg_volume`, `session_high`, `session_low`, `last_price` | L852: returns `None` (no DB write) |
| 0 | Chinese check | `country`, `is_chinese` | L888: `ctx` has snapshot data but no float/rvol/gap |
| 1 | Float (P1) | `float_shares`, `is_ideal_float` | L1240: `ctx` has snapshot + float, but `rvol=0`, `gap_pct=0` |
| 2 | RVOL (P2) | `rvol`, `is_ideal_rvol` | L1299: `ctx` has float + rvol, but `gap_pct=0` |
| 3 | Price (P3) | *(no new fields)* | L1570: `ctx` has float + rvol, but `gap_pct=0` |
| 4 | Gap (P4) | `gap_pct`, `opening_gap_pct`, `live_gap_pct` | L1636: `ctx` fully enriched for numerics |
| 5 | Catalyst (P5) | `catalyst_type`, `catalyst_desc`, `catalyst_confidence` | L948, L967, L1397: `ctx` fully enriched |
| 6 | 200 EMA | `ema_200_value`, `room_to_ema_pct` | L1694: `ctx` fully enriched |
| 7 | Borrow+Float | `easy_to_borrow`, `hard_to_borrow` | L1738, L1755: `ctx` fully enriched |
| ✅ | PASS | All fields enriched | L1065: complete `ctx` + `candidate` |

> [!IMPORTANT]
> **Fields written as `0.0` when they shouldn't be:**
> - `rvol` → written as `0.0` when rejection is at Pillar 1 (float) or Chinese check
> - `gap_pct` → written as `0.0` when rejection is at Pillar 1, 2, or 3
> - `price` → `ctx.last_price` defaults to `Decimal('0')`, written as `0.0` when snapshot fails (though snapshot failure returns early without DB write)

**Fields that are safe (nullable, default `None`):** `score`, `float_shares`, `catalyst_type`, `country`, `ema_200`, `room_to_ema_pct`, `is_etb`, `name`

**The write method at line 559-577:**
```python
db.add(WarriorScanResultDB(
    gap_pct=float(ctx.gap_pct) if ctx and ctx.gap_pct is not None else None,
    rvol=float(ctx.rvol) if ctx and ctx.rvol is not None else None,
    price=float(ctx.last_price) if ctx and ctx.last_price is not None else None,
    ...
))
```

The `is not None` check passes because `Decimal('0')` is not `None` — it's a valid value. So `float(Decimal('0'))` = `0.0` gets written.

**Fix approach:** Change the `is not None` checks to also exclude the default value, e.g.:
```python
gap_pct=float(ctx.gap_pct) if ctx and ctx.gap_pct not in (None, Decimal('0')) else None,
# OR: only write rvol/gap_pct if their enriching pillar has run
```

**14 total `_write_scan_result_to_db` call sites found** (1 definition + 13 calls).

---

### 2. NAC Scans — ✅ NOT AFFECTED

| Property | Value |
|----------|-------|
| **Endpoint** | `GET /data/scan-history` |
| **Data Source** | `scan_history.json` (file-based) |
| **Reader** | `get_scan_history_logger()` from `nexus2/domain/lab/scan_history_logger.py` |

**Analysis:** This tab reads from a JSON file, not a database. The `NACScanResult` model exists in `telemetry_db.py` but **nothing writes to it**. Data is appended to `scan_history.json` by `log_passed_symbol()` which only logs PASS candidates with real values. No default-zero risk.

**Note:** The `NACScanResult` DB model is currently unused dead code.

---

### 3. Catalyst Audits — ✅ NOT AFFECTED

| Property | Value |
|----------|-------|
| **Endpoint** | `GET /data/catalyst-audits` |
| **Data Source** | `telemetry.db` → `catalyst_audits` table |
| **Writer** | `ai_catalyst_validator.py` |

**Analysis:** All fields are strings (symbol, headline, regex_result, ai_result, confidence, etc.). No numeric columns that could default to zero. The writer only logs when a catalyst evaluation actually runs, so all values are explicit.

---

### 4. AI Comparisons — ✅ NOT AFFECTED

| Property | Value |
|----------|-------|
| **Endpoint** | `GET /data/ai-comparisons` |
| **Data Source** | `telemetry.db` → `ai_comparisons` table |
| **Writer** | `ai_catalyst_validator.py` |

**Analysis:** All fields are strings (symbol, headline, flash_lite_result, pro_result, etc.). No numeric columns. Same reasoning as Catalyst Audits.

---

### 5. Warrior Trades — ✅ NOT AFFECTED

| Property | Value |
|----------|-------|
| **Endpoint** | `GET /data/warrior-trades` |
| **Data Source** | `warrior.db` → `warrior_trades` table |
| **Model** | `WarriorTradeModel` in [warrior_db.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/db/warrior_db.py#L48-L139) |

**Analysis:** All price fields are stored as **strings** (`Column(String(20))`). The writer `log_warrior_entry()` converts floats to strings explicitly: `entry_price=str(entry_price)`, `stop_price=str(stop_price)`. The only field with a default value is `realized_pnl=default "0"` — this is **intentional** (P&L starts at zero). `high_since_entry=default "0"` is also intentional and immediately overridden to `str(entry_price)` at write time.

No misleading zero defaults.

---

### 6. NAC Trades — ✅ NOT AFFECTED

| Property | Value |
|----------|-------|
| **Endpoint** | `GET /data/nac-trades` |
| **Data Source** | `nexus.db` → `positions` table |
| **Model** | `PositionModel` in [models.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/db/models.py#L118-L207) |

**Analysis:** Price fields stored as strings. Default values are `realized_pnl="0"` and `unrealized_pnl="0"` — both intentional. Quality metrics (`quality_score`, `rs_percentile`) are nullable integers with default `None`. No early-rejection write pattern; positions are only created when an actual trade occurs.

---

### 7. Trade Events — ✅ NOT AFFECTED

| Property | Value |
|----------|-------|
| **Endpoint** | `GET /data/trade-events` |
| **Data Source** | `nexus.db` → `trade_events` table |
| **Model** | `TradeEventModel` in [models.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/db/models.py#L372-L420) |

**Analysis:** All value fields are strings (`old_value`, `new_value`). Events are append-only and only created when an actual trade action occurs (entry, stop move, exit). No default-zero risk.

---

### 8. Quote Audits — ✅ NOT AFFECTED  

| Property | Value |
|----------|-------|
| **Endpoint** | `GET /data/quote-audits` |
| **Data Source** | `nexus.db` → `quote_audits` table |
| **Model** | `QuoteAuditModel` in [models.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/db/models.py#L473-L526) |

**Analysis:** All price fields stored as strings. `divergence_pct` is a string. Nullable source prices (`alpaca_price`, `fmp_price`, `schwab_price`) default to `None`. The writer only creates a record when a quote comparison actually runs with real values. No default-zero risk.

---

### 9. Validation Log — ✅ NOT AFFECTED

| Property | Value |
|----------|-------|
| **Endpoint** | `GET /data/validation-log` |
| **Data Source** | `warrior.db` → `entry_validation_log` table |
| **Model** | `EntryValidationLogModel` in [warrior_db.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/db/warrior_db.py#L142-L195) |
| **Writer** | `log_entry_validation()` at [warrior_db.py:L1013-L1050](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/db/warrior_db.py#L1013-L1050) |

**Analysis:** All price fields stored as strings. The writer uses the pattern `str(value) if value else None`, which writes `None` for missing data instead of `"0"`. Booleans are nullable. Records are only created when an actual trade entry occurs, so no early-rejection write pattern.

---

## Consolidated Summary

| Tab | Affected? | Data Type | Write Pattern | Default Risk |
|-----|-----------|-----------|---------------|-------------|
| **Warrior Scans** | ⚠️ YES | Float columns | Early-rejection writes `EvaluationContext` defaults | `rvol=0.0`, `gap_pct=0.0`, `price=0.0` |
| NAC Scans | ✅ No | JSON file | Only PASS candidates logged | N/A |
| Catalyst Audits | ✅ No | String columns | Explicit values only | N/A |
| AI Comparisons | ✅ No | String columns | Explicit values only | N/A |
| Warrior Trades | ✅ No | String columns | Explicit `str(value)` | `"0"` is intentional for P&L |
| NAC Trades | ✅ No | String columns | Explicit values | `"0"` is intentional for P&L |
| Trade Events | ✅ No | String columns | Append-only, real values | N/A |
| Quote Audits | ✅ No | String columns | Explicit values | N/A |
| Validation Log | ✅ No | String columns | `str(v) if v else None` | N/A |

---

## Recommended Fix (Warrior Scans Only)

The fix should be in `_write_scan_result_to_db` (line 539 of `warrior_scanner_service.py`). Two options:

### Option A: Guard against default values in the write method
```python
# In _write_scan_result_to_db:
gap_pct=float(ctx.gap_pct) if ctx and ctx.gap_pct and float(ctx.gap_pct) != 0.0 else None,
rvol=float(ctx.rvol) if ctx and ctx.rvol and float(ctx.rvol) != 0.0 else None,
price=float(ctx.last_price) if ctx and ctx.last_price and float(ctx.last_price) != 0.0 else None,
```

### Option B: Change `EvaluationContext` defaults to `None`
```python
# In EvaluationContext:
rvol: Optional[Decimal] = None        # was Decimal("0")
gap_pct: Optional[Decimal] = None     # was Decimal("0")
last_price: Optional[Decimal] = None  # was Decimal("0")
```
> [!WARNING]
> Option B requires auditing all 1833 lines of `warrior_scanner_service.py` to ensure nothing does arithmetic on these fields without a `None` check first.

### Recommendation: **Option A** — least disruptive, targeted fix at the write boundary.

---

## Evidence Trail

| Claim | File | Line | Verification |
|-------|------|------|-------------|
| `EvaluationContext.rvol` defaults to `Decimal("0")` | `warrior_scanner_service.py` | 446 | `rvol: Decimal = Decimal("0")` |
| `EvaluationContext.gap_pct` defaults to `Decimal("0")` | `warrior_scanner_service.py` | 457 | `gap_pct: Decimal = Decimal("0")` |
| `_write_scan_result_to_db` uses `is not None` check | `warrior_scanner_service.py` | 564 | `if ctx and ctx.gap_pct is not None` |
| Float pillar rejection writes before RVOL enrichment | `warrior_scanner_service.py` | 1240 | `self._write_scan_result_to_db(ctx.symbol, False, ctx, rejection_reason="float_too_high")` |
| NAC Scans reads from file, not DB | `data_routes.py` | 232-296 | `get_scan_history_logger()` → `scan_history.json` |
| `NACScanResult` model has no writers | codebase-wide search | N/A | No results for `NACScanResult(` outside tests/definition |
| `EntryValidationLogModel` uses `str(v) if v else None` | `warrior_db.py` | 1038-1043 | Verified `str(expected_target) if expected_target else None` pattern |
| `QuoteAuditModel` all strings, no defaults | `models.py` | 473-526 | All price columns `Column(String(20), nullable=True)` |
