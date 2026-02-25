# Handoff: Backfill 10s Bar Data for All Test Cases

**Agent:** Backend Specialist
**Priority:** P1 — required before pipeline fix can be tested
**Date:** 2026-02-25
**Reference:** `nexus2/reports/2026-02-25/spec_10s_data_fidelity.md`

---

## Problem

Only 3 of 35 test cases have 10s bar data (bctx, gri, hind). The remaining 32 need 10s aggregates from Polygon before patterns can use finer-grained data.

## Verified Facts

**Existing 10s files (3):**
- `nexus2/tests/test_cases/intraday/bctx_20260127_10s.json` (161 KB)
- `nexus2/tests/test_cases/intraday/gri_20260128_10s.json` (179 KB)
- `nexus2/tests/test_cases/intraday/hind_20260127_10s.json` (71 KB)

**Auto-discovery mechanism:**
- File: `historical_bar_loader.py:332-344`
- Pattern: `{symbol}_{YYYYMMDD}_10s.json` in `tests/test_cases/intraday/`
- Loader auto-discovers sidecar files — no config change needed per case

**Polygon API:**
- Endpoint: `/v2/aggs/ticker/{ticker}/range/10/second/{from}/{to}`
- Data available for all test dates (Jan-Feb 2026)
- Rate limit: 5 calls/min on free tier

## Task

Write a backfill script (`scripts/backfill_10s_bars.py`) that:

1. Reads `warrior_setups.yaml` (or whatever defines test case symbols/dates)
2. For each case without an existing `*_10s.json` file:
   - Fetch 10s aggregates from Polygon for the full trading day (6:00 AM – 8:00 PM ET)
   - Format as `{"bars": [{"t": "HH:MM:SS", "o": float, "h": float, "l": float, "c": float, "v": int}, ...]}`
   - Match the format of existing 10s files (check bctx/gri/hind for reference)
   - Save as `{symbol}_{YYYYMMDD}_10s.json` in `tests/test_cases/intraday/`
3. Rate-limit API calls (1 per 15s to stay within free tier)
4. Print progress and summary

### Open Questions (Investigate)

- Where is the master list of test case symbols/dates? (Check `warrior_setups.yaml` or scan `ross_*.json` files)
- What Polygon API key env var does the project use? (Check existing Polygon adapter code)
- Do existing 10s files include premarket bars? (Check time range in bctx_10s.json)

## Output

- Script: `scripts/backfill_10s_bars.py`
- Run the script to backfill all 32 missing cases
- Write status to: `nexus2/reports/2026-02-25/backend_status_10s_backfill.md`
- Include: count of files created, total size, any failures
