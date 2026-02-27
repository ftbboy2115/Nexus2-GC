# Handoff: Backend Planner — Catalyst Detection Gap Investigation (NDRA)

> **Date:** 2026-02-27  
> **From:** Coordinator  
> **To:** Backend Planner  
> **Priority:** Medium  
> **Type:** READ-ONLY investigation — no code changes

---

## Objective

Investigate why the scanner's catalyst detection returned `no_catalyst` for **NDRA on 2026-02-26**, despite the stock having real breaking news. Determine whether this is a **headline source gap** (FMP/Benzinga didn't return NDRA news) or a **classification gap** (headlines were fetched but misclassified).

---

## Verified Facts (from Mock Market agent)

1. **NDRA had real news** — test case notes say *"8am news, sub-1M float, healthcare sector, 300x relative volume"* (file: `warrior_setups.yaml:1306`)
2. **Scanner rejected NDRA 12 times** — all `result=FAIL`, `reason=no_catalyst`, via telemetry DB
3. **All other pillars passed** — gap=26-53%, rvol=67-1303x, float=681.8K
4. **Reverse split ≠ catalyst** — per `.agent/strategies/warrior.md:19`, reverse split is Pillar 5 (Technical Setup), not Pillar 4 (Catalyst). Scanner was correct to not use that.

---

## Open Questions (YOU must investigate these)

### Q1: What headlines were available for NDRA on Feb 26?

**Investigation approach:**
- Check FMP news API for NDRA headlines around 2026-02-26
- Check if Benzinga was queried (look for Benzinga references in the catalyst pipeline)
- Starting point: `_evaluate_catalyst_pillar()` in `nexus2/domain/scanner/warrior_scanner_service.py:1308-1441`

### Q2: Did the catalyst classifier actually run for NDRA?

**Investigation approach:**
- Check the `catalyst_audits` table in the telemetry DB for NDRA records
- The `/data/catalyst-audits` endpoint is at `nexus2/api/routes/data_routes.py:485-590` — review its query structure
- If audit records exist: what headline was passed and what classification was returned?
- If NO audit records: the pipeline likely never found a headline to classify

### Q3: Source gap vs. classification gap?

Based on Q1 and Q2, determine which scenario applies:

| Scenario | Evidence | Implication |
|----------|----------|-------------|
| **Source gap** — No headlines returned from FMP/Benzinga | No `catalyst_audits` records, or audit shows empty headline | Need additional news sources or earlier fetching |
| **Classification gap** — Headlines found but misclassified | `catalyst_audits` records exist with a headline but `result=none` | Classifier logic or AI prompt needs improvement |

### Q4: Is this systemic or a one-off?

**Investigation approach:**
- Review other Feb 2026 test cases in `warrior_setups.yaml` that had real catalysts
- Cross-reference against scanner telemetry to find other `no_catalyst` false negatives
- The `scanner_pulse_check.py` script can query the VPS for scan results by symbol/date

---

## Key Files to Read

| File | What to look for |
|------|-----------------|
| `nexus2/domain/scanner/warrior_scanner_service.py:1308-1441` | `_evaluate_catalyst_pillar()` — how headlines are fetched & scored |
| `nexus2/domain/scanner/warrior_scanner_service.py:1443-1538` | `_run_multi_model_catalyst_validation()` — AI classification logic |
| `nexus2/api/routes/data_routes.py:485-590` | `GET /data/catalyst-audits` — how to query audit records |
| `.agent/strategies/warrior.md:18-19` | Pillar 4 (Catalyst) definition |

---

## Expected Deliverable

A report at `nexus2/reports/2026-02-27/research_catalyst_gap_ndra.md` containing:

1. **Findings per question** — with evidence (file paths, line numbers, code snippets)
2. **Root cause classification** — source gap, classification gap, or both
3. **Recommendations** — what could fix this (new news source? classifier tuning? keyword expansion?)
4. **Scope assessment** — one-off (NDRA-specific) or systemic (affects many stocks)

> [!IMPORTANT]
> This is READ-ONLY research. Do NOT modify any production code.
> All findings must include file paths, line numbers, and copy-pasted code evidence.
