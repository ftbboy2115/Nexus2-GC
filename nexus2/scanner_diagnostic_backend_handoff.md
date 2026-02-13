# Backend Handoff: Retroactive Scan Diagnostic Tool

## Objective

Build a CLI diagnostic tool that takes a symbol + date and shows exactly what the scanner would see — which data sources include it, what metrics they report, and which filter would reject it.

## Context

Ross's symbols never appear in scan logs. We need a tool to retroactively check: was the problem at the data source level (symbol never appeared in gainers feeds) or at the filter level (appeared but got rejected)?

## Architecture

### File: `nexus2/cli/scan_diagnostic.py`

Usage:
```bash
python -m nexus2.cli.scan_diagnostic EVMN 2026-02-10
python -m nexus2.cli.scan_diagnostic --all-test-cases
```

### Data Sources to Check

The live scanner uses 3 data sources. The diagnostic should check each:

1. **FMP Gainers** — `stock_market/gainers` and `pre_post_market/gainers`
   - Check: `nexus2/adapters/market_data/fmp_adapter.py` for the API calls
   - Note: Historical gainers may not be available, so document this limitation

2. **Polygon Gainers** — snapshot API
   - Check: how polygon gainers are fetched in the scanner

3. **Alpaca Movers** — market movers API
   - Check: how alpaca movers are fetched

### Metrics to Report

For the given symbol + date, the tool should fetch and display:

```
=== EVMN on 2026-02-10 ===

DATA SOURCE PRESENCE:
  FMP Gainers: [YES/NO/UNAVAILABLE]
  Polygon Gainers: [YES/NO/UNAVAILABLE]
  Alpaca Movers: [YES/NO/UNAVAILABLE]

MARKET DATA (from available sources):
  Price: $X.XX
  Gap %: X.X%
  Float: X.XM shares
  RVOL: X.Xx
  Premarket Volume: X
  Catalyst: [type or NONE]
  200 EMA: $X.XX (room: X.X%)

SCANNER FILTER WALKTHROUGH:
  [1] Tradeable equity check: PASS/FAIL
  [2] Price range ($1-$20): PASS/FAIL ($X.XX)
  [3] Gap % (min X%): PASS/FAIL (X.X%)
  [4] Float (max 100M): PASS/FAIL (X.XM)
  [5] RVOL (min 2.0x): PASS/FAIL (X.Xx)
  [6] Catalyst check: PASS/FAIL (type)
  [7] MACD check: PASS/FAIL
  [8] 200 EMA room: PASS/FAIL
  
  VERDICT: Would PASS/FAIL at stage [X]
```

### Implementation Notes

- Use existing adapters where available (`fmp_adapter.py`, Polygon adapter, Alpaca adapter)
- For historical data lookups, use Polygon historical bars API (1-min or daily)
- Load `.env` for API keys
- The tool does NOT need to run the actual scanner — just check data availability and apply the same filter logic manually
- If historical gainers data isn't available, note the limitation and use current market data APIs to get float, price, etc.

### Bonus: Batch Mode

`--all-test-cases` flag should read `nexus2/tests/test_cases/warrior_setups.yaml` and run the diagnostic for every test case symbol + date, producing a summary table:

```
| Symbol | Date | In Sources? | Gap% | Float | RVOL | Would Pass? | Fail Stage |
|--------|------|-------------|------|-------|------|------------|------------|
| EVMN   | 2026-02-10 | Polygon only | 45% | 2.1M | 3.2x | FAIL | MACD |
| ...    | ... | ... | ... | ... | ... | ... | ... |
```

## Deliverable

1. `nexus2/cli/scan_diagnostic.py` — working CLI tool
2. Run it for these 6 symbols and capture output:
   - EVMN 2026-02-10
   - VELO 2026-02-10
   - BNRG 2026-02-11
   - PRFX 2026-02-11
   - PMI 2026-02-12
   - RDIB 2026-02-12
3. Save output to `nexus2/reports/2026-02-13/scanner_diagnostic_results.md`
