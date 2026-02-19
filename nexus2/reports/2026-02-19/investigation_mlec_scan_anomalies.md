# Investigation: MLEC Scan Data Inconsistencies

**Date:** 2026-02-19  
**Scope:** ETB flip and catalyst flip for MLEC in Warrior Scans (Data Explorer)  
**Investigator:** Code Auditor Agent

---

## Executive Summary

Both anomalies share **the same root cause**: when a symbol is rejected by an early pillar check, `_write_scan_result_to_db` writes `EvaluationContext` defaults for fields that haven't been evaluated yet. Early scans that pass all pillars get real values; later scans that fail early get defaults.

---

## Root Cause: Evaluation Order vs. DB Write Timing

### The Evaluation Pipeline

The `_evaluate_symbol` method (L805–L1057) evaluates pillars in this order:

```
1. Chinese stock check           (L859)
2. Pillar 1: Float               (L879)  — _check_float_pillar
3. Pillar 2: RVOL                (L885)  — _calculate_rvol_pillar
4. Pillar 3: Price               (L891)  — _check_price_pillar
5. Pillar 4: Gap                 (L897)  — _calculate_gap_pillar
6. Pillar 5: Catalyst            (L909)  — _evaluate_catalyst_pillar
7. Multi-model catalyst          (L913)
8. Legacy AI fallback            (L916)
9. Catalyst requirement check    (L919)
10. Dilution check               (L939)
11. 200 EMA check                (L961)
12. Former runner check          (L968)
13. Borrow/ETB check             (L973)  — _check_borrow_and_float_disqualifiers
14. Reverse split check          (L979)
15. Build candidate              (L984)
```

Each pillar that rejects a symbol calls `_write_scan_result_to_db`, which always writes **all** context fields — including ones that haven't been evaluated yet.

### The Defaults

**Finding:** `EvaluationContext` defaults cause misleading DB values for unevaluated fields.

**File:** [warrior_scanner_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py):L451,L468

**Code:**
```python
# L451 — catalyst
catalyst_type: str = "none"

# L468 — borrow status  
easy_to_borrow: bool = True
```

**Verified with:** `view_file` at lines 414–485

**Conclusion:** When a symbol fails Pillars 1–4, these defaults are written to the DB without any actual data lookup.

---

## Anomaly 1: ETB Flip (`False` → `True`)

### Root Cause

The borrow status check (`_check_borrow_and_float_disqualifiers`) runs at step 13 in the pipeline — **after all 5 pillars and the 200 EMA check**.

**Finding:** ETB is only populated from Alpaca if the symbol passes all preceding checks.

**File:** [warrior_scanner_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py):L1694-L1705

**Code:**
```python
# Get borrow status from Alpaca
if self.alpaca_broker:
    try:
        asset_info = self.alpaca_broker.get_asset_info(ctx.symbol)
        ctx.hard_to_borrow = asset_info.get("hard_to_borrow", False)
        ctx.easy_to_borrow = asset_info.get("easy_to_borrow", True)
        ...
    except Exception as e:
        scan_logger.debug(f"Could not get HTB status for {ctx.symbol}: {e}")
else:
    scan_logger.debug(f"BROKER MISSING | {ctx.symbol} | No alpaca_broker wired")
```

**DB write code at L560:**
```python
is_etb=str(ctx.easy_to_borrow) if ctx else None,
```

**Verified with:** `view_file` at lines 1683–1741 and 542–566

### Mechanism

| Scan Time | What Happens | `is_etb` Written |
|-----------|-------------|-----------------|
| ~09:46–10:11 | MLEC passes all pillars → reaches L1694 → Alpaca returns `easy_to_borrow=False` | `"False"` ✅ |
| ~10:13+ | MLEC fails an earlier pillar (RVOL/gap/etc.) → rejected at L1284 or similar → `_write_scan_result_to_db` called → `ctx.easy_to_borrow` is still default `True` | `"True"` ❌ (misleading) |

**Conclusion:** The ETB flip is caused by the evaluation short-circuit. When MLEC fails early, the borrow check is never executed, and the default `True` is written to the DB.

---

## Anomaly 2: Catalyst Flip (`earnings` → `none`)

### Root Cause

The catalyst evaluation (`_evaluate_catalyst_pillar`) runs at step 6 — Pillar 5. All preceding pillars (Float, RVOL, Price, Gap) can reject the symbol before catalyst is ever checked.

**Finding:** Catalyst type is only populated if the symbol passes Pillars 1–4.

**File:** [warrior_scanner_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py):L1385-L1396

**Code:**
```python
# Check for recent earnings as backup (L1385-1396)
if not ctx.has_catalyst:
    has_earnings, earnings_date = self.market_data.fmp.has_recent_earnings(
        ctx.symbol, days=s.catalyst_lookback_days
    )
    if has_earnings:
        ctx.has_catalyst = True
        ctx.catalyst_type = "earnings"
        ctx.catalyst_desc = f"Earnings {earnings_date}"
        ctx.catalyst_confidence = 0.9
```

**DB write code at L554:**
```python
catalyst_type=ctx.catalyst_type if ctx else None,
```

**Verified with:** `view_file` at lines 1290–1406 and 542–566

### Mechanism

| Scan Time | What Happens | `catalyst_type` Written |
|-----------|-------------|------------------------|
| ~09:46–10:11 | MLEC passes Pillars 1–4 → reaches L1385 → FMP returns earnings data | `"earnings"` ✅ |
| ~10:13+ | MLEC's RVOL/gap decays → fails an earlier pillar → rejected before catalyst check → `ctx.catalyst_type` is still default `"none"` | `"none"` ❌ (misleading) |

**Conclusion:** The catalyst flip is the same structural problem as the ETB flip. Early rejection short-circuits the evaluation, and the default `"none"` is written to the DB.

---

## Why MLEC Might Fail Later in the Day

The likely reason MLEC started failing on earlier pillars after ~10:13:

1. **RVOL decay:** As the market opens and more volume data comes in, the time-adjusted RVOL projection changes. Pre-market projections (L1257–L1266) use a `daily_equivalent_factor = 10.0` multiplier. After market open (L1250–L1256), the projection formula changes and may yield a lower RVOL.

2. **Gap fade:** The dual-gate gap check (L1560–L1634) uses the higher of opening gap and live gap. If the stock's live price faded significantly, `change_percent` from the screener source may have also decreased.

3. **Price drift:** If MLEC's price drifted outside the $1.50–$20 range.

Without checking the actual rejection reasons in the DB for MLEC in the later scan cycles, this is a hypothesis — but the structural bug is proven regardless.

---

## Recommended Fix

### Option A: Use `None` for Unevaluated Fields (Preferred)

Mark context fields as "not yet evaluated" by using `None` instead of misleading defaults:

```diff
 # L451 — catalyst
-catalyst_type: str = "none"
+catalyst_type: Optional[str] = None

 # L468 — borrow status
-easy_to_borrow: bool = True
+easy_to_borrow: Optional[bool] = None
```

Then in `_write_scan_result_to_db`, these will naturally be written as `None` (NULL in DB) for unevaluated fields, which the UI can display as "-" or "N/A".

**Impact:** Requires updating all code that checks `ctx.catalyst_type == "none"` to also handle `None`. The `_evaluate_catalyst_pillar` already sets it to `"none"` explicitly when no catalyst is found, so the only change is the default before evaluation runs.

> [!WARNING]
> Changing `easy_to_borrow` from `bool` to `Optional[bool]` requires auditing all downstream consumers: `_check_borrow_and_float_disqualifiers` (L1725: `if ctx.easy_to_borrow`), `_build_candidate` (L1782), and `WarriorCandidate.quality_score`.

### Option B: Move DB Writes to a Single Post-Evaluation Point

Instead of writing to DB from each rejection handler, collect the result and write once at the end of `_evaluate_symbol` — after all evaluable fields have been populated regardless of pass/fail.

**Pros:** Cleaner architecture, single DB write point  
**Cons:** Larger refactor, must run all checks even for rejected symbols (performance cost)

### Recommendation

**Option A** is the minimum-viable fix — it makes the data honestly reflect what was evaluated. The UI should show "N/A" instead of displaying misleading defaults.

---

## Verification Commands

To confirm the evaluation order and defaults:

```powershell
# Verify EvaluationContext defaults
Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern "easy_to_borrow.*=|catalyst_type.*=" | Where-Object { $_.LineNumber -ge 414 -and $_.LineNumber -le 485 }

# Verify _check_borrow_and_float_disqualifiers position in pipeline
Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern "_check_borrow_and_float_disqualifiers|_evaluate_catalyst_pillar|_check_float_pillar|_calculate_rvol_pillar|_check_price_pillar|_calculate_gap_pillar" | Where-Object { $_.LineNumber -ge 870 -and $_.LineNumber -le 980 }

# Verify DB write uses ctx defaults
Select-String -Path "nexus2\domain\scanner\warrior_scanner_service.py" -Pattern "is_etb=|catalyst_type=" | Where-Object { $_.LineNumber -ge 542 -and $_.LineNumber -le 566 }
```

To check MLEC rejection reasons in the DB (confirms the hypothesis):

```powershell
# Check what reasons MLEC was rejected for after 10:13
python -c "from nexus2.db.telemetry_db import get_telemetry_session, WarriorScanResultDB; s=get_telemetry_session(); r=s.__enter__().query(WarriorScanResultDB).filter(WarriorScanResultDB.symbol=='MLEC').order_by(WarriorScanResultDB.timestamp.desc()).limit(20).all(); [print(f'{x.timestamp} | {x.result} | reason={x.reason} | catalyst={x.catalyst_type} | etb={x.is_etb}') for x in r]"
```
