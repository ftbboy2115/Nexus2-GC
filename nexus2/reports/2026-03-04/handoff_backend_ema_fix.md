# Backend Specialist Handoff: EMA Bar Reversal Fix + Health Metrics

**Date:** 2026-03-04 11:54 ET  
**From:** Coordinator  
**To:** Backend Specialist  
**Research:** `nexus2/reports/2026-03-04/research_vcig_ema_health.md`  
**Validation:** `nexus2/reports/2026-03-04/validation_vcig_ema_health.md`  
**Output:** `nexus2/reports/2026-03-04/backend_status_ema_fix.md`

---

## Context

VCIG is trading at ~$9. Scanner shows EMA 200 = $665,900.34. Three validated bugs:

1. Bar reversal in `_get_200_ema` computes EMA backward
2. No sanity check on EMA values
3. Health metrics (room_to_ema, position health) don't gate entries

---

## Bug 1: Fix Bar Reversal (CRITICAL)

**File:** `warrior_scanner_service.py` ~line 1195-1196

**Problem:** Code reverses Polygon bars assuming they're newest-first, but Polygon returns oldest-first (`sort: "asc"`). The reversal makes them newest-first, computing EMA backward.

**Fix:** Remove the `bars.reverse()` call. Also fix the misleading comment at ~line 1183 that says "most recent first."

---

## Bug 2: Add EMA Sanity Check (HIGH)

**Problem:** No validation on EMA values. A $665K EMA for a $9 stock passes silently.

**Fix:** After computing EMA, add a ratio check:
```python
if ema_value > current_price * 10 or ema_value < current_price * 0.01:
    logger.warning(f"[Scanner] {symbol}: EMA 200 sanity check failed (EMA=${ema_value:.2f}, price=${price:.2f})")
    ema_value = None  # Treat as unavailable
```

---

## Bug 3: Health Metrics History Investigation (IMPORTANT)

**Question from Clay:** When did the entry path stop checking health metrics? Was it ever different?

**Investigate:** Check git history for `compute_position_health` and `room_to_ema`:
```powershell
cd "C:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus"
git log --all --oneline -- nexus2/domain/automation/warrior_engine_entry.py | Select-Object -First 20
git log -p --all -S "compute_position_health" -- "*.py" | Select-Object -First 100
git log -p --all -S "room_to_ema" -- "*.py" | Select-Object -First 100
```

Document findings: was health ever checked in the entry path? If so, when was it removed and why?

---

## Verification

```powershell
# Batch test — EMA fix may change results for some cases
python scripts/gc_quick_test.py --all --diff
```

Report any P&L changes from the EMA correction.
