# Handoff: Build Trade Management Diagnostic Script (Phase 1)

**Agent:** Backend Specialist
**Priority:** P1 — identifying where WB loses money vs Ross
**Date:** 2026-02-25
**Reference:** `nexus2/reports/2026-02-25/spec_trade_management_diagnostic.md`

---

## Problem

WB captures $155K from 35 test cases where Ross captured $433K — a **-$277K delta**. Entry logic works (28 winners), but trade management (stops, exits, scaling) is where the money is lost. We need a diagnostic script that shows **per-trade: what WB did vs what Ross did**.

## Task

Build `scripts/gc_trade_management_diagnostic.py` implementing **Phase 1** from the spec. This requires **zero code changes to the backend** — it uses existing data sources only.

### Data Sources (all existing)

1. **`warrior_setups.yaml`** — Ross's data: `ross_pnl`, `ross_entry_time`, `expected.entry_near`, `expected.stop_near`, `notes` (freeform text)
2. **Batch test results** — from `POST /warrior/sim/run_batch_concurrent`: per-trade `entry_price`, `exit_price`, `exit_reason`, `exit_mode`, `stop_price`, `stop_method`, `partial_taken`, `entry_time`, `exit_time`, `pnl`
3. **`entry_validation_log`** (if available in results) — MFE/MAE data

### Script Requirements

```
Usage: python scripts/gc_trade_management_diagnostic.py [--case CASE_ID] [--all] [--top N]
  --case CASE_ID   Analyze a single case
  --all            Analyze all cases
  --top N          Analyze top N cases by P&L gap (default: 10)
```

### Step 1: Run a batch test to get WB trade data
- Call `POST /warrior/sim/run_batch_concurrent` (no overrides, default config)
- Collect per-trade data from the response

### Step 2: Load Ross data from warrior_setups.yaml
- Parse `ross_pnl`, `ross_entry_time`, `expected.entry_near`, `expected.stop_near`
- Extract structured data from `notes` using regex patterns (see spec Section 5):
  - Ross exit type (stopped out, took profit, etc.)
  - Ross partial taken
  - Ross added
  - Ross stop/exit prices if mentioned

### Step 3: Produce per-case diagnostic

For each case, output a comparison table like the one in spec Section 4.3:
- Entry comparison (price, time, delta)
- Trade management comparison (stop, exit mode, partial, exit reason, exit price, P&L)
- Diagnosis category: `EARLY_EXIT`, `WRONG_STOP`, `MISSED_PARTIAL`, etc. (see spec Section 4.3 Section E)

### Step 4: Produce summary statistics

Aggregate across all cases (see spec Section 4.4):
- Cases better/worse than Ross
- Exit timing analysis (early/late)
- Stop analysis (too tight/wide/matched)
- MFE capture rate if available

### Output Requirements

- Print per-case reports to stdout (markdown formatted)
- Print summary statistics at the end
- Save detailed JSON to `nexus2/reports/gc_diagnostics/trade_management_diagnostic.json`
- **Focus on the largest P&L gap cases first** — sort by `abs(ross_pnl - wb_pnl)` descending

### Design Decisions

- **Do NOT modify any backend code.** Phase 1 is read-only.
- Use `urllib.request` for API calls (same pattern as `gc_param_sweep.py`)
- Parse YAML with `yaml.safe_load`
- Ross notes regex extraction can be approximate — flag cases where extraction confidence is low

### Handling Missing Ross Exit Data

Many cases won't have clear Ross exit details in `notes`. For each extracted field, track confidence:
- `DIRECT` — exact price/action stated (e.g., "stopped out at $6.40")
- `INFERRED` — implied but not explicit (e.g., "took small profit" with no price)
- `UNKNOWN` — notes don't mention exit behavior at all

When Ross exit data is missing:
- Show `"N/A"` for that comparison column
- **Still compute WB-only diagnostics**: MFE capture %, entry timing, exit reason analysis — these don't need Ross data
- Flag the case with `INCOMPLETE_ROSS_DATA` in the diagnosis
- Do NOT skip the case — partial comparisons are still valuable

## Output

- Script: `scripts/gc_trade_management_diagnostic.py`
- Run the script with `--top 10` and include the output in the status report
- Write status to: `nexus2/reports/2026-02-25/backend_status_trade_diagnostic.md`
- Include testable claims
