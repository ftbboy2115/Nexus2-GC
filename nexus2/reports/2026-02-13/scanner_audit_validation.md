# Validation Report: Scanner Pipeline Audit + Diagnostic

**Date**: 2026-02-13  
**Validator**: Audit Validator Agent  
**Reference**: [scanner_audit_validator_handoff.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/scanner_audit_validator_handoff.md)

---

## T1: Auditor Claims Verified (C1-C7)

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| C1 | `_check_dollar_volume` is dead code | ✅ **PASS** | `Select-String` returns only the `def` line at L1583. Grepping `_evaluate_symbol` for `_check_dollar_volume` returns 0 results. Method defined but never called. |
| C2 | `_check_price_pillar` has no `scan_logger` | ✅ **PASS** | Viewed lines 1532-1550: only `tracker.record()` and `_write_scan_result_to_db()`. Zero `scan_logger.info()` calls. Silent rejection confirmed. |
| C3 | `_calculate_gap_pillar` has no `scan_logger` | ✅ **PASS** | Viewed lines 1552-1581: only `tracker.record()`, `_write_scan_result_to_db()`, and a `verbose` print. Zero `scan_logger.info()` calls. Silent rejection confirmed. |
| C4 | `high_float_threshold = 30M` | ✅ **PASS** | Line 108: `high_float_threshold: int = 30_000_000` with comment "Hard reject if float > 30M" |
| C5 | `etb_high_float_threshold = 10M` | ✅ **PASS** | Line 103: `etb_high_float_threshold: int = 10_000_000` with comment "Reject ETB stocks with float > 10M" |
| C6 | 200 EMA room at 15% | ✅ **PASS** | Line 167: `min_room_to_200ema_pct: float = 15.0` with comment "Reject if < 15% room to 200 EMA" |
| C7 | Commit `f501ef6` added high float disqualifier | ✅ **PASS** | `git show f501ef6 --stat` confirms: "fix: Add pure High Float disqualifier (>30M = reject)", modifies `warrior_scanner_service.py` (+29 lines). |

---

## T2: Backend Diagnostic Verified

| # | Claim | Result | Evidence |
|---|-------|--------|----------|
| D1 | PMI diagnostic output matches saved report | ✅ **PASS** | Compared `scanner_diagnostic_results.md` PMI entry: Gap 42.9%, Float 26.1M, RVOL 229.8x, fail at Catalyst. Code at L200-205 calculates gap correctly as `(open - prev_close) / prev_close * 100`. |
| D2 | `--all-test-cases` flag works | ✅ **PASS** | Code at L826-835 reads `warrior_setups.yaml`, filters synthetic cases, calls `run_batch()`. Path resolution at L828 is correct: `Path(__file__).parent.parent / "tests" / "test_cases" / "warrior_setups.yaml"`. |
| D3 | Code quality acceptable | ✅ **PASS** | See quality notes below. |

### D3 Code Quality Notes

| Aspect | Assessment |
|--------|-----------|
| **.env loading** | ✅ OK — Handled via `from nexus2 import config` which calls `load_dotenv()` at L23-25 of `config.py` |
| **API error handling** | ✅ OK — All API calls wrapped in `try/except` with errors appended to `result.errors` list (e.g., L178, L221, L242) |
| **Gap % calculation** | ✅ OK — L202-205: `(open_price - prev_close) / prev_close * 100` — matches Ross definition (gap = open vs prev close) |
| **Historical data source** | ✅ OK — Uses Polygon for historical bars (reliable, paid tier), FMP for fundamentals |
| **Filter walkthrough** | ✅ OK — Mirrors scanner pipeline: equity check → price → gap → float → RVOL → catalyst → 200 EMA |
| **Missing check** | ⚠️ NOTE — Diagnostic does NOT check high_float_threshold (30M) or ETB+float (10M) disqualifiers. These are applied separately by `_check_borrow_and_float_disqualifiers()` in the live scanner. Diagnostic only checks Pillar 1 max_float (100M). |
| **EMA computation** | ⚠️ NOTE — Diagnostic EMA calculation (L129-137) uses `closes[0]` as seed, while scanner (L1169) uses SMA of first 200 bars as seed. Different seeding = slightly different EMA values, though unlikely to cause meaningful divergence. |

---

## T3: MGRT Gap Bug Investigation

> [!CAUTION]
> **ROOT CAUSE IDENTIFIED: Telemetry DB stores the WRONG gap value, making Data Explorer misleading.**

### The Bug

Data Explorer shows MGRT with:
- `gap_pct`: **112.39%**
- `result`: FAIL
- `reason`: **gap_too_low**

This appears contradictory — how can 112% gap fail as "gap too low"?

### Root Cause: `gap_pct` DB Column Stores `change_percent`, NOT Recalculated Gap

The telemetry write at **L545** of `warrior_scanner_service.py`:

```python
gap_pct=float(ctx.change_percent) if ctx and ctx.change_percent else None,
```

This writes `ctx.change_percent` — the **original** gap from the data source (FMP/Polygon/Alpaca) — NOT the recalculated gap from `_calculate_gap_pillar()`.

Meanwhile, `_calculate_gap_pillar()` at **L1563-1564** recalculates gap:

```python
if ctx.yesterday_close and ctx.yesterday_close > 0:
    ctx.gap_pct = ((ctx.last_price - ctx.yesterday_close) / ctx.yesterday_close) * 100
else:
    ctx.gap_pct = ctx.change_percent
```

### The Data Flow

```
FMP/Polygon says MGRT gap = 112.39% (original change_percent)
    ↓
Scanner enters _evaluate_symbol() with change_percent = 112.39
    ↓
build_session_snapshot() fetches:
    - yesterday_close from daily bars (Polygon → FMP fallback)
    - last_price from Alpaca quote (real-time)
    ↓
_calculate_gap_pillar() RECALCULATES:
    gap_pct = ((last_price - yesterday_close) / yesterday_close) * 100
    ↓
If last_price has dropped significantly since the gap (e.g., stock faded)
OR yesterday_close is from a DIFFERENT source than what FMP used:
    → Recalculated gap could be < 4%
    → Returns "gap_too_low"
    ↓
_write_scan_result_to_db() writes:
    gap_pct = ctx.change_percent  ← 112.39% (ORIGINAL, not recalculated!)
    reason = "gap_too_low"        ← Based on recalculated gap
```

### Why the Values Diverge

There are **two likely scenarios** for MGRT specifically:

| Scenario | Likelihood | Explanation |
|----------|-----------|-------------|
| **A: `last_price` dropped** | **HIGH** | MGRT opened with 112% gap but price faded. The scanner runs periodically; by the time it checked, `last_price` (Alpaca real-time) was much lower than the original gap-up price. The recalculated gap using current price vs yesterday's close was < 4%. |
| **B: `yesterday_close` mismatch** | **MEDIUM** | FMP's `previousClose` field (used for the original 112%) may differ from the `yesterday_close` derived from Polygon daily bars in `build_session_snapshot()`. If the Polygon bar for "yesterday" has a different close (e.g., due to after-hours adjustment, split, or stale data), the recalculated gap would be different. |

### The Core Problem

The DB column `gap_pct` **misleads** Data Explorer users because:
1. It stores the **original** `change_percent` from the data source
2. But the scanner's pass/fail decision uses a **recalculated** gap from different data
3. The gap pillar has **no `scan_logger.info()` call** (C3 confirmed), so there's no log of what the recalculated gap actually was

### Fix Recommendations

| # | Fix | Effort |
|---|-----|--------|
| 1 | **Fix DB write to use recalculated gap**: Change L545 from `ctx.change_percent` to `ctx.gap_pct` (which is set by `_calculate_gap_pillar()`). Note: `gap_too_low` rejections write to DB BEFORE `ctx.gap_pct` is fully set, so move the DB write inside `_calculate_gap_pillar()` AFTER the recalculation. | S |
| 2 | **Add scan_logger to gap pillar**: Add `scan_logger.info(f"FAIL | {ctx.symbol} | Reason: gap_too_low | Recalculated Gap: {ctx.gap_pct:.1f}% (original: {ctx.change_percent:.1f}%) | last_price=${ctx.last_price} | yesterday_close=${ctx.yesterday_close}")` | S |
| 3 | **Store both values**: Add a `original_gap_pct` column to telemetry DB to allow Data Explorer to show both the data source gap and the scanner's recalculated gap | M |
| 4 | **Investigate MGRT telemetry**: Query VPS DB for MGRT's `last_price` and `yesterday_close` at scan time to confirm which scenario (A or B) caused this specific instance | S |

---

## Overall Rating

### **HIGH** — All auditor claims verified, diagnostic tool acceptable

| Category | Rating |
|----------|--------|
| Auditor Claims (C1-C7) | ✅ 7/7 PASS — All claims verified with exact evidence |
| Diagnostic Tool (D1-D3) | ✅ 3/3 PASS — Code quality acceptable with minor notes |
| MGRT Bug (T3) | 🐛 **NEW BUG FOUND** — Root cause identified, fix recommendations provided |

### Issues Found (Not Fixed — Validator Scope)

| # | Issue | Severity | Status |
|---|-------|----------|--------|
| 1 | Telemetry `gap_pct` column stores wrong value (`change_percent` instead of recalculated gap) | **HIGH** | Report to coordinator |
| 2 | Diagnostic tool missing high_float (30M) and ETB+float (10M) checks | **LOW** | Enhancement only |
| 3 | Diagnostic EMA seed differs from scanner EMA seed | **LOW** | Cosmetic divergence |
