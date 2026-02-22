# Handoff: Mock Market Specialist — BCTX Test Case + HIND 10s Data

**Date:** 2026-02-21
**From:** Coordinator
**To:** Mock Market Specialist (`@agent-mock-market-specialist.md`)
**Priority:** MEDIUM

---

## Objective

Two tasks from the Jan 27 Ross Cameron video:

### Task 1: Create BCTX Test Case

Ross traded BCTX on 2026-01-27. We have the HIND test case from this video but NOT BCTX.

**Trade details from transcript** (`.agent/knowledge/warrior_trading/2026-01-27_transcript_RAJXknk-VI4.md`):
- **Symbol:** BCTX
- **Date:** 2026-01-27
- **Catalyst:** Phase 2 metastatic breast cancer trial news (breaking news flame)
- **Exchange:** Canadian
- **Float:** Low
- **Entry:** Break of $5.00
- **Adds:** $5.39, $5.41, $5.46
- **Peak:** $6.00
- **Exit:** Sold on pullback (disappointed it didn't hold $6)
- **Setup:** Breaking news + micro pullback on 10s chart
- **Ross's chart timeframe:** 10s (stated in transcript)

**Follow the `/create-test-cases` workflow:**
1. Fetch 1-min bars using `fetch_ross_test_cases.py`
2. Verify data quality with `scripts/peek_bars.py`
3. Add entry to `warrior_setups.yaml` with `ross_chart_timeframe: "10s"`
4. Update Transcript Vault (HIND is likely already there; just ensure BCTX is covered)

### Task 2: Fetch 10s Historical Data for HIND

HIND already has a test case (`ross_hind_20260127`) but does NOT have 10s bar data. Ross used the 10s chart for HIND entries.

**Follow the same pattern as GRI:**
- GRI test case (`ross_gri_20260128`) has `ross_chart_timeframe: "10s"` in `warrior_setups.yaml`
- Check how GRI's 10s data was fetched and stored
- Apply the same approach to HIND

---

## Verified Facts

- HIND test case exists: `ross_hind_20260127` in `warrior_setups.yaml` (line 574)
- GRI 10s pattern exists: `ross_gri_20260128` with `ross_chart_timeframe: "10s"` (line 587)
- Transcript location: `.agent/knowledge/warrior_trading/2026-01-27_transcript_RAJXknk-VI4.md`

---

## Open Questions

1. Does BCTX have available 1-min and 10s bar data from Alpaca/Polygon for Jan 27?
2. Is there a ticker collision risk for BCTX? (Canadian company — verify price range matches ~$5)
3. How was GRI's 10s data fetched? Is there a separate script or flag?

---

## Deliverable

1. New test case file: `nexus2/tests/test_cases/intraday/ross_bctx_20260127.json`
2. Updated `warrior_setups.yaml` with BCTX entry
3. HIND 10s bar data (if fetchable)
4. Updated Transcript Vault
5. Status report: `nexus2/reports/2026-02-21/mock_market_status_bctx_hind.md`
