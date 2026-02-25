# Backend Status: Trade Management Diagnostic Script (Phase 1)

**Date:** 2026-02-25
**Agent:** Backend Specialist
**Reference:** `nexus2/reports/2026-02-25/handoff_backend_trade_diagnostic.md`

---

## Summary

Built `scripts/gc_trade_management_diagnostic.py` implementing Phase 1 of the trade management diagnostic spec. The script runs batch tests, loads Ross data from `warrior_setups.yaml`, extracts structured data from Ross's freeform notes via regex, and produces per-case diagnostic reports with diagnosis categories and summary statistics.

**No backend code was modified.** Phase 1 is read-only.

---

## What Was Built

### Script: `scripts/gc_trade_management_diagnostic.py`

**CLI Interface:**
```
python scripts/gc_trade_management_diagnostic.py                 # Top 10 by P&L gap
python scripts/gc_trade_management_diagnostic.py --top 5         # Top 5
python scripts/gc_trade_management_diagnostic.py --case ross_npt_20260203
python scripts/gc_trade_management_diagnostic.py --all           # All cases
python scripts/gc_trade_management_diagnostic.py --no-run        # Reload from saved JSON
```

**Features:**
1. Calls `POST /warrior/sim/run_batch_concurrent` with `include_trades: true`
2. Loads Ross data from `warrior_setups.yaml` (expected entry/stop, ross_pnl, ross_entry_time)
3. Extracts structured data from Ross `notes` via regex (exit type, partial, added, stop price, exit price)
4. Per-case diagnostic report with entry comparison, trade management comparison, diagnosis categories
5. Summary statistics across all cases
6. Saves detailed JSON to `nexus2/reports/gc_diagnostics/trade_management_diagnostic.json`
7. `--no-run` flag to reload from saved JSON without re-running batch

**Diagnosis Categories:**
- `BETTER_MANAGEMENT` / `WORSE_MANAGEMENT` — WB P&L vs Ross P&L
- `WRONG_STOP` — WB stopped out, Ross exited differently
- `EARLY_EXIT` — WB captured <30% of Ross P&L on a winner
- `STOP_TOO_TIGHT` — WB stopped out on a trade Ross survived to profit
- `STOP_TOO_WIDE` — WB loss deeper than Ross loss
- `MISSED_PARTIAL` — Ross took partial profit, WB didn't
- `GUARD_BLOCKED` / `NO_ENTRY` — WB didn't enter

---

## Run Output (abbreviated)

```
Cases analyzed:          32
Both entered:            32
WB no entry:             0

TOTAL P&L:
  WB:    $+131,987.25
  Ross:  $+432,999.62
  Delta: $-301,012.37

MANAGEMENT QUALITY:
  Better than Ross:  8 cases  ($+74,360.75)
  Worse than Ross:   24 cases  ($-375,373.12)

DIAGNOSIS BREAKDOWN:
  Stop too tight:    5 (WB stopped, Ross survived)
  Stop too wide:     1 (WB loss > Ross loss)
  Wrong stop:        10 (WB stopped, Ross exited differently)
  Guard blocked:     0
  Early exit:        10 (WB captured <30% of Ross P&L)
  Missed partial:    0
```

---

## Testable Claims

1. **Claim:** Script exists at `scripts/gc_trade_management_diagnostic.py`
   **Verify:** `Test-Path scripts\gc_trade_management_diagnostic.py`

2. **Claim:** Script runs without errors with `--top 5`
   **Verify:** `.venv\Scripts\python scripts\gc_trade_management_diagnostic.py --top 5`

3. **Claim:** Script produces JSON output file
   **Verify:** `Test-Path nexus2\reports\gc_diagnostics\trade_management_diagnostic.json`

4. **Claim:** `--no-run` flag works (loads saved JSON without API call)
   **Verify:** `.venv\Scripts\python scripts\gc_trade_management_diagnostic.py --no-run --top 3`

5. **Claim:** `--case` flag works for single case analysis
   **Verify:** `.venv\Scripts\python scripts\gc_trade_management_diagnostic.py --case ross_npt_20260203`

6. **Claim:** Script uses `urllib.request` for API calls (no new dependencies)
   **Verify:** `Select-String -Path scripts\gc_trade_management_diagnostic.py -Pattern "import requests"` should return nothing

7. **Claim:** No backend files were modified
   **Verify:** `git diff --name-only nexus2/` should show zero files

8. **Claim:** Ross notes regex extraction covers exit type, partial, added, stop price, exit price
   **Verify:** `Select-String -Path scripts\gc_trade_management_diagnostic.py -Pattern "ross_exit_type|ross_partial|ross_added|ross_stop_price|ross_exit_price"`

---

## Key Findings from Run

The top P&L gap cases reveal these patterns:

| Rank | Case | WB P&L | Ross P&L | Δ | Top Diagnosis |
|------|------|--------|----------|---|---------------|
| 1 | NPT | ~$0 | $81,000 | -$81K | EARLY_EXIT |
| 2 | HIND | ~$0 | $55,252 | -$55K | EARLY_EXIT/WRONG_STOP |
| 3 | PAVM | ~$0 | $43,950 | -$44K | EARLY_EXIT |
| 4 | MLEC 0213 | ~$0 | $43,000 | -$43K | EARLY_EXIT |
| 5 | GRI | ~$0 | $31,600 | -$32K | EARLY_EXIT |

**Pattern:** The largest P&L gaps are on the biggest winners where Ross scaled in aggressively (adding at $5→$5.50→$6→... etc.) while WB takes a single base_hit entry and exits early. Trade management improvements should focus on:
1. **Scale-in logic** — Ross frequently adds on strength; WB does not
2. **Home run mode detection** — These huge moves warrant home_run exits, not base_hit
3. **Stop placement** — 10 cases show WRONG_STOP where WB stopped out but Ross exited differently
