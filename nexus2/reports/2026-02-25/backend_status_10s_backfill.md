# Backend Status: 10s Bar Data Backfill

**Date:** 2026-02-25
**Handoff:** `handoff_backend_10s_backfill.md`

---

## Result

✅ **All 35 test cases now have 10-second bar data.**

| Metric | Value |
|--------|-------|
| Files created | 32 (was 3, now 35) |
| Total 10s data size | ~10 MB |
| Failures | 0 |
| Script | `scripts/backfill_10s_bars.py` |

---

## Script Created

**`scripts/backfill_10s_bars.py`** — reusable backfill tool:
- Discovers test cases by scanning `ross_*.json` files in `intraday/`
- Skips cases that already have `*_10s.json` sidecar files
- Fetches 10s aggregates from Polygon (`/v2/aggs/ticker/{ticker}/range/10/second/{date}/{date}`)
- Converts UTC timestamps to ET `HH:MM:SS` format
- Outputs in the exact format expected by `historical_bar_loader.py`
- Flags: `--dry-run`, `--symbol SYMBOL`, `--force`

---

## Open Questions Resolved

| Question | Answer |
|----------|--------|
| Master test case list? | `ross_*.json` filenames in `intraday/` (35 files) |
| Polygon API key env var? | `POLYGON_API_KEY` in `.env`, loaded via `nexus2/config.py` |
| Do existing 10s files include premarket? | Yes — BCTX starts at `04:00:00` ET, ends at `19:59:40` ET |
| Rate limiting needed? | No — Developer tier ($200/mo) has unlimited API calls |

---

## Testable Claims

1. **Claim:** 35 `*_10s.json` files exist in `nexus2/tests/test_cases/intraday/`
   - **Verify:** `(Get-ChildItem "nexus2\tests\test_cases\intraday\*_10s.json").Count` → 35

2. **Claim:** Each file has correct JSON structure with keys: `symbol`, `date`, `timeframe`, `timezone`, `bar_count`, `bars`
   - **Verify:** `python -c "import json; d=json.load(open('nexus2/tests/test_cases/intraday/rolr_20260114_10s.json')); print(list(d.keys()))"` → `['symbol', 'date', 'timeframe', 'timezone', 'bar_count', 'bars']`

3. **Claim:** Bar timestamps are in ET `HH:MM:SS` format (matching existing bctx/gri/hind format)
   - **Verify:** `python -c "import json; d=json.load(open('nexus2/tests/test_cases/intraday/rolr_20260114_10s.json')); print(d['bars'][0]['t'])"` → time string like `04:00:00`

4. **Claim:** `bar_count` matches actual number of bars in each file
   - **Verify:** `python -c "import json; d=json.load(open('nexus2/tests/test_cases/intraday/rolr_20260114_10s.json')); print(d['bar_count'] == len(d['bars']))"`→ `True`

5. **Claim:** Script exists at `scripts/backfill_10s_bars.py` with `--dry-run` flag
   - **Verify:** `python scripts/backfill_10s_bars.py --dry-run` → shows "Already have 10s data: 35, Need to fetch: 0"
