# Handoff: Scanner Catalyst Detection Gap — NDRA False Negative

> **Date:** 2026-02-27  
> **From:** Coordinator (Clay's session)  
> **Priority:** Medium — scanner coverage gap for real Ross trades

---

## Problem

The scanner pulse check (`scripts/scanner_pulse_check.py`) revealed that **NDRA on 2026-02-26 was scanned 12 times but FAILED every scan** due to `no_catalyst`, despite having actual breaking news.

**Scanner output:**
```
❌ FAIL | score=None | gap=26-53% | rvol=67-1303x | float=681.8K | catalyst=none
   └─ reason: no_catalyst
```

Every other pillar was excellent: sub-1M float, massive gap, extreme RVOL. The ONLY failure was catalyst detection.

---

## Verified Facts

**NDRA had real news on Feb 26:**
- Test case notes (verified via `Select-String`): *"8am news, sub-1M float, healthcare sector, 300x relative volume"*
- File: `warrior_setups.yaml:1306`
- Ross traded it (entered ~$4.58 PMH break, squeezed to halt at $4.95)

**Scanner saw NDRA but rejected it:**
- 12 scan results in telemetry DB, all `result=FAIL`, `reason=no_catalyst`
- Verified via `scanner_pulse_check.py NDRA 2026-02-26` hitting VPS `/data/warrior-scan-history`

**Reverse split is NOT a catalyst in Ross's methodology:**
- Strategy file `.agent/strategies/warrior.md:19` — reverse split is under **Pillar 5 (Technical Setup)**, not Pillar 4 (Catalyst)
- Pillar 4 requires *"Breaking news strongly preferred"*
- So the scanner was correct to not treat "reverse split" as a catalyst — but it should have detected the actual news headline

---

## Open Questions (for Backend Planner/Specialist)

1. **What headlines were available for NDRA on Feb 26?** Check FMP/Benzinga news API responses for that date. Did any headlines come back?

2. **Did the catalyst classifier run?** Check if there's a corresponding `catalyst_audits` record for NDRA in the telemetry DB. Was the headline fetched but misclassified, or was no headline found at all?

3. **Is this a headline source gap or a classification gap?**
   - If no headlines found → FMP/Benzinga didn't have NDRA news in time (source gap)
   - If headlines found but classified as `none` → classifier/regex/AI needs improvement (classification gap)

4. **How many other test case symbols had `no_catalyst` rejections?** Run the pulse check against all Feb 2026 test cases to identify the pattern.

---

## Suggested Investigation

Assign **Backend Planner** to:
1. Query `catalyst_audits` table for NDRA on Feb 26
2. Check FMP news API for NDRA headlines around that date
3. Review the catalyst classification pipeline in `_evaluate_catalyst_pillar()` and `_run_multi_model_catalyst_validation()`
4. Determine if this is a one-off or systemic gap

---

## Reference Files

| File | Purpose |
|------|---------|
| `nexus2/domain/scanner/warrior_scanner_service.py:1308-1441` | `_evaluate_catalyst_pillar()` |
| `nexus2/domain/scanner/warrior_scanner_service.py:1443-1538` | `_run_multi_model_catalyst_validation()` |
| `nexus2/api/routes/data_routes.py:303-428` | `GET /data/warrior-scan-history` endpoint |
| `nexus2/api/routes/data_routes.py:485-590` | `GET /data/catalyst-audits` endpoint |
| `.agent/strategies/warrior.md:18-19` | Pillar 4 (Catalyst) and Pillar 5 (Technical Setup) |
| `scripts/scanner_pulse_check.py` | New pulse check script |
