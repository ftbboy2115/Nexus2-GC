# Validation Report: VCIG EMA + Health Metrics Research

**Date:** 2026-03-04 11:55 ET  
**Validator:** Audit Validator  
**Source:** `nexus2/reports/2026-03-04/research_vcig_ema_health.md`  
**Handoff:** `nexus2/reports/2026-03-04/handoff_validator_vcig_ema.md`

---

## Claim Verification Table

| # | Claim | Result | Key Evidence |
|---|-------|--------|--------------|
| 1 | Bar Reversal Bug | **PASS** | Line 1196 reverses already-chronological bars; Polygon returns `sort: "asc"` at line 530 |
| 2 | Health Metrics Are Display-Only | **PASS** | Zero references to `health`, `ema_200`, `room_to_ema`, or `position_health` in entry engine |
| 3 | No Sanity Checks on EMA | **PASS** | `ema.*sanity` search returns 0 results; no bounds check anywhere in pipeline |
| 4 | Scanner Gate Passes Absurd EMA | **PASS** | Line 1729 logic confirmed: -99.998% fails `> -15` check → not rejected |

---

## Detailed Verification

### Claim 1: Bar Reversal Bug

**Claim:** `_get_200_ema` (line 1195-1196) assumes Polygon bars are newest-first and reverses them, but Polygon returns `sort: "asc"` (oldest-first). The reversal computes EMA backward.

**Verification Command:** `view_file` on `warrior_scanner_service.py` lines 1166-1210  
**Actual Output (lines 1195-1196):**
```python
# Note: bars are typically most recent first, so we need to reverse
closes_chronological = closes[::-1]  # Oldest to newest
```

**Verification Command:** `view_file` on `polygon_adapter.py` lines 502-550  
**Actual Output (line 530):**
```python
params={"limit": limit, "sort": "asc"}
```

**Result:** **PASS**  
**Notes:** The comment "bars are typically most recent first" is factually wrong for `get_daily_bars`. Daily bars are fetched with `sort: "asc"` (oldest first) — confirmed at `polygon_adapter.py:530`. The reversal at line 1196 flips them to newest-first, making the EMA run backward through time. Notably, `get_intraday_bars` (line 419) uses `sort: "desc"` for minute bars, which is likely the source of the misleading comment — but daily bars use `"asc"`.

---

### Claim 2: Health Metrics Are Display-Only

**Claim:** `compute_position_health` is ONLY called from the `/positions/health` API endpoint. The entry engine never checks health metrics.

**Verification Command:** `grep_search` for `compute_position_health` across `C:\Dev\Nexus`  
**Actual Output:**
| File | Line | Context |
|------|------|---------|
| `indicator_service.py` | 235 | Definition: `def compute_position_health(` |
| `indicator_service.py` | 373, 390 | Internal helper calls `compute_position_health()` |
| `warrior_positions.py` | 137, 184 | API endpoint callers |

**Verification Command:** `grep_search` for `health` in `warrior_engine_entry.py` → **0 results**  
**Verification Command:** `grep_search` for `room_to_ema` in `warrior_engine_entry.py` → **0 results**  
**Verification Command:** `grep_search` for `ema_200` in `warrior_engine_entry.py` → **0 results**  
**Verification Command:** `grep_search` for `position_health` in `warrior_engine_entry.py` → **0 results**

**Result:** **PASS**  
**Notes:** `compute_position_health` is defined in `indicator_service.py` and called exclusively from the `warrior_positions.py` API route (lines 137, 184). There is also an internal helper at line 390. Zero references to any health-related terms exist in the entry engine (`warrior_engine_entry.py`). The dashboard health indicators are purely visual and have no influence on trade entry decisions.

---

### Claim 3: No Sanity Checks on EMA

**Claim:** Zero validation on EMA values anywhere in the pipeline.

**Verification Command:** `grep_search` for `ema.*sanity` (case-insensitive) across `C:\Dev\Nexus\nexus2` → **0 results**  

**Verification via code inspection:** Examined `_check_200_ema` (lines 1710-1753) and `_get_200_ema` (lines 1166-1210):
- `_get_200_ema`: Returns raw computed EMA, no bounds check
- `_check_200_ema`: Only checks `room_to_ema_pct` range — no check for absurd EMA magnitude
- No `if ema > X * price` or ratio check exists anywhere

**Result:** **PASS**  
**Notes:** Confirmed. The computed EMA is used directly with no sanity gate. A $665,900 EMA for a $9 stock passes through without any warning or rejection.

---

### Claim 4: Scanner Gate Passes Absurd EMA

**Claim:** `_check_200_ema` paradoxically PASSES a $665K EMA because -99.998% room is interpreted as "lots of room below the ceiling."

**Verification Command:** `view_file` on `warrior_scanner_service.py` lines 1710-1753  
**Actual Output (line 1729):**
```python
if ctx.room_to_ema_pct < 0 and ctx.room_to_ema_pct > -s.min_room_to_200ema_pct:
```

**Logic trace with `min_room_to_200ema_pct = 15`:**
- `room_to_ema_pct = ((9 - 665900) / 665900) * 100 = -99.998%`
- `-99.998 < 0` → True ✅
- `-99.998 > -15` → **False** ❌
- Combined (AND): **False** → Gate does NOT reject

**Result:** **PASS**  
**Notes:** The gate only rejects stocks with room between 0% and -15% (meaning the EMA is slightly above the price). An absurd -99.998% room means "price is massively below EMA" which the gate interprets as safe. This is correct behavior for valid data (far below EMA = lots of room) but catastrophically wrong for garbage EMA data.

---

## Quality Rating

**HIGH** — All 4 claims verified. The research report is accurate and well-evidenced. The bar reversal bug, display-only health metrics, missing sanity checks, and paradoxical gate pass are all confirmed with code evidence.

---

## Additional Finding

The comment at `warrior_scanner_service.py:1183` reads:
```python
# Extract closing prices (most recent first in the bars list)
```
This is **also wrong** — bars from `get_daily_bars` are oldest-first. This reinforces that the developer who wrote this function assumed all bar data comes newest-first, which is only true for `get_intraday_bars` (minute bars use `sort: "desc"`, then get reversed to chronological at line 446).
