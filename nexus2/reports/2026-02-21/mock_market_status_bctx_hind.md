# Mock Market Status: BCTX Test Case + HIND 10s Data

**Date:** 2026-02-21
**Agent:** Mock Market Specialist
**Tasks:** BCTX test case creation + HIND/BCTX 10s bar data

---

## Task 1: BCTX Test Case — ✅ COMPLETE

### Data Fetch
- **Script:** `fetch_ross_test_cases.py BCTX 2026-01-27 news`
- **Source:** Polygon
- **Result:** 517 bars (130 premarket, 387 market, 50 continuity)
- **File:** `nexus2/tests/test_cases/intraday/ross_bctx_20260127.json`

### Data Quality Verification
| Check | Result |
|-------|--------|
| Price range | $3.90–$6.03 ✅ matches transcript ($5 entry, $6 peak) |
| PMH | $6.03 ✅ (single-bar wick at 07:31 — sub-minute spike) |
| Gap | -1.7% (stock was already trading ~$4.68 premarket) |
| Volume | 1.37M premarket bars ✅ significant |
| Ticker collision | None — price range consistent with Canadian biotech |

### YAML Entry
Added `ross_bctx_20260127` to `warrior_setups.yaml`:
- `ross_pnl: 4500.00`
- `ross_entry_time: "07:30"`
- `ross_chart_timeframe: "10s"`
- `catalyst: "news"` (Phase 2 breast cancer trial)
- `entry_near: 5.00` / `stop_near: 4.75`

### Batch Test
```
Invoke-RestMethod -Method POST -Uri "http://localhost:8000/warrior/sim/run_batch_concurrent" -Body '{"case_ids": ["ross_bctx_20260127"]}'
```

| Metric | Value |
|--------|-------|
| Sim P&L | $4,352.97 |
| Ross P&L | $4,500.00 |
| Delta | -$147.03 (96.7% match) |
| Guard Blocks | 3 (max scale #2 limit) |
| Runtime | 8.18s |

---

## Task 2: 10s Bar Data — ✅ COMPLETE

### HIND 10s Bars
- **Script:** `fetch_10s_bars.py HIND 2026-01-27`
- **Result:** 552 bars, 08:00–09:32 ET
- **File:** `nexus2/tests/test_cases/intraday/hind_20260127_10s.json`
- **YAML:** Added `ross_chart_timeframe: "10s"` to `ross_hind_20260127`

### BCTX 10s Bars
- **Script:** `fetch_10s_bars.py BCTX 2026-01-27`
- **Result:** 1,264 bars, 04:00–19:59 ET
- **File:** `nexus2/tests/test_cases/intraday/bctx_20260127_10s.json`

### Existing 10s Pattern Reference
GRI (`ross_gri_20260128`) already had 10s data at `gri_20260128_10s.json`. HIND and BCTX follow the same naming pattern.

---

## Task 3: Transcript Vault — ✅ COMPLETE

Jan 27 entry already existed in vault (line 20). Added BCTX-specific deep dive section alongside existing HIND deep dive.

---

## Files Modified/Created

| File | Action |
|------|--------|
| `nexus2/tests/test_cases/intraday/ross_bctx_20260127.json` | NEW — 1-min bar data |
| `nexus2/tests/test_cases/intraday/hind_20260127_10s.json` | NEW — 10s bar data |
| `nexus2/tests/test_cases/intraday/bctx_20260127_10s.json` | NEW — 10s bar data |
| `nexus2/tests/test_cases/warrior_setups.yaml` | MODIFIED — added BCTX entry + HIND 10s flag |
| `transcript_vault.md` | MODIFIED — added BCTX deep dive |
| `fetch_10s_bars.py` | MODIFIED — added HIND/BCTX to default fetch list |

---

## Open Questions for Coordinator

1. **10s Bar Integration:** The 10s bar files exist but are not yet referenced in `warrior_setups.yaml` via an `intraday_10s_file` field. Should a new YAML field be added, or is the naming convention (`{symbol}_{date}_10s.json`) sufficient for the sim engine to discover them?
2. **BCTX Previous Close:** The gap is -1.7% because the first premarket bar open is $4.68. The actual previous close may differ — should we verify via Polygon's daily bars?
