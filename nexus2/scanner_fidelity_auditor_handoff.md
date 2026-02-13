# Code Auditor Handoff: Scanner Pipeline Audit

## Objective

Trace the full Warrior scanner pipeline and identify exactly where/why Ross Cameron's traded symbols get eliminated. The scanner currently has **zero PASS results**.

## Context

Ross's recent traded symbols (EVMN, VELO, BNRG, PRFX, PMI) **do not appear anywhere** in scan logs — not even in the pre-filtered candidate list. Only RDIB appeared in the pre-filtered list on Feb 12 but was never fully evaluated.

### Scanner Architecture

```
Data Sources (FMP gainers + Polygon gainers + Alpaca movers)
  → Merge & dedup (~110 symbols)
  → Pre-filter → ~16-19 symbols
  → Detailed eval (warrior_scanner_service.py):
      Float (max 100M), RVOL (min 2.0x), Catalyst AI, MACD/EMA
  → PASS/FAIL → 0 candidates
```

### Key Files

- `nexus2/domain/scanner/warrior_scanner_service.py` — 1785 lines, main Warrior scanner (5 Pillars)
- `nexus2/domain/automation/unified_scanner.py` — orchestrator
- `nexus2/settings/scanner_settings.py` — configurable thresholds

### Key Data Sources

- **Scan History JSON** (primary): `/root/Nexus2/data/scan_history.json` — 1478 lines, structured by date, goes back to Jan 21. Keys are dates, values are arrays of scan result objects with fields like `symbol`, `gap_percent`, etc. **Start here.**
- **Scan Logs** (secondary): `/root/Nexus2/data/warrior_scan.log` (and .1 through .7 rotated)
- **Data Explorer API**: The Warrior Scans tab in the frontend queries these results — check what API endpoint it calls.

## Tasks

### T1: Scan History Analysis
Query `scan_history.json` to answer:
- How many total PASS symbols per date since Jan 21?
- Were any of Ross's symbols (EVMN, VELO, BNRG, PRFX, PMI, RDIB, NPT, ROLR, PAVM, BATL) in the scan history?
- What's the trend in daily PASS counts?
```powershell
ssh root@100.113.178.7 "cat /root/Nexus2/data/scan_history.json | python3 -c 'import json,sys; d=json.load(sys.stdin); [print(k, len(v)) for k,v in sorted(d.items())]'"
```

### T2: Pre-filter Pipeline Trace
Trace the code path from data source ingestion to the pre-filtered list. Document:
- What gap%, price, and volume thresholds eliminate symbols before detailed eval?
- Where is the "Pre-filtered: 19" count determined? What criteria must pass?
- Why do only 3 of 19 get FAIL log lines while the other 16 are silently skipped?

### T3: PASS Count Collapse Analysis
The PASS count in logs dropped 778 → 44 → 13 → 0 across rotations. Determine:
- Was there a code change or settings change responsible?
```powershell
cd "c:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus"
git log --oneline --since="2026-01-20" -- nexus2/domain/scanner/warrior_scanner_service.py nexus2/settings/scanner_settings.py
```

### T4: Filter Chain Documentation
Document every filter in `warrior_scanner_service.py` with its threshold value:

| Filter | Threshold | Stage | Source |
|--------|-----------|-------|--------|
| Float | max 100M | Detailed eval | WarriorScanSettings |
| RVOL | min 2.0x | Detailed eval | WarriorScanSettings |
| ... | ... | ... | ... |

### T5: Silent Rejection Analysis
Of the 19 pre-filtered symbols on Feb 12, only RUBI, MGRT, and RIG generated FAIL log entries. The other 16 were silently skipped. Why? Is there a fast-path rejection that doesn't log?

## Deliverable

Write report to `nexus2/reports/2026-02-13/scanner_pipeline_audit.md`
