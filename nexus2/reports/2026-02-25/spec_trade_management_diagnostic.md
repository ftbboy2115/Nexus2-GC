# Trade Management Diagnostic Specification

> **Purpose**: Design a diagnostic tool that compares WB's trade management against Ross Cameron's actual behavior for each test case, highlighting differences in stops, exits, scaling, and timing.

---

## 1. Problem Statement

The existing `gc_batch_diagnose.py` provides **aggregate-level** comparison (total P&L, entry timing, guard blocks) but does not surface **trade management differences** — the actions taken *after* entry. When WB enters at the same price as Ross but produces different P&L, the current diagnostics show the P&L gap but not **why** (early stop, missed partial, over-held position, wrong exit mode, etc.).

We need a diagnostic tool that, for each test case, reconstructs a **side-by-side timeline** of WB's trade management actions vs. Ross's known behavior.

---

## 2. Data Source Inventory

### 2.1 Ross Cameron Data (from `warrior_setups.yaml`)

| Field | Type | Coverage | Notes |
|-------|------|----------|-------|
| `ross_pnl` | float | 100% | Actual P&L per case |
| `ross_entry_time` | string | ~70% | e.g., "09:33" |
| `expected.entry_near` | float | ~80% | Ross's approximate entry price |
| `expected.stop_near` | float | ~60% | Ross's approximate stop price |
| `ross_chart_timeframe` | string | ~50% | "1min" or "5min" |
| `notes` | text | ~90% | Rich prose describing Ross's actions: partials, adds, stops, exit reasoning |

> [!WARNING]
> **Ross exit data is unstructured.** There is no `ross_exit_time`, `ross_exit_price`, `ross_partial_at`, or `ross_stop_adjusted_to` field. These must be extracted from `notes` text using pattern matching or manual annotation.

### 2.2 WB Trade Data (from concurrent batch runner `_run_single_case_async`)

Per-trade fields returned in the `trades[]` array:

| Field | Type | Notes |
|-------|------|-------|
| `entry_price` | float | Actual fill price |
| `exit_price` | float | **Final** exit price (may miss partials) |
| `avg_exit_price` | float | VWAP across all exits (partials + final) |
| `shares` | int | Original position size |
| `pnl` | float | From `warrior_db.realized_pnl` |
| `entry_trigger` | string | `pmh_break`, `orb`, `vwap_break`, etc. |
| `exit_mode` | string | `base_hit` or `home_run` |
| `exit_reason` | string | `mental_stop`, `profit_target`, `candle_under_candle`, `time_stop`, `eod_close`, etc. |
| `entry_time` | datetime | Sim clock time |
| `exit_time` | datetime | Sim clock time |
| `stop_price` | string | **Initial** stop price |
| `stop_method` | string | `vwap`, `candle_low`, `fallback_15c`, etc. |
| `target_price` | string | Initial target |
| `support_level` | string | Support used for technical stop |
| `partial_taken` | bool | Whether a partial exit occurred |
| `remaining_quantity` | int | Shares remaining after partial |

### 2.3 Guard Block Data (from concurrent batch runner)

| Field | Type | Notes |
|-------|------|-------|
| `guard_blocks[]` | array | Each: `{guard, reason, symbol, blocked_price, blocked_time}` |
| `guard_analysis` | dict | Counterfactual: `{total_blocks, correct_blocks, missed_opportunities, by_guard_type}` |
| Per-block detail | dict | `{price_5m, price_15m, price_30m, mfe, mae, outcome, hypothetical_pnl_15m}` |

### 2.4 Entry Validation Log (from `entry_validation_log` table)

| Field | Type | Notes |
|-------|------|-------|
| `mfe` | float | Max favorable excursion (high - entry) |
| `mae` | float | Max adverse excursion (entry - low) |
| `ross_entry` | string | Ross's entry price for comparison |
| `ross_pnl` | string | Ross's P&L |
| `entry_delta` | string | bot_entry - ross_entry |
| `target_hit` | bool | Did price reach expected target? |
| `stop_hit` | bool | Did price hit expected stop? |

---

## 3. Telemetry Gaps

### Gap 1: No Stop Adjustment History
**Current state**: `warrior_db` stores only the **initial** `stop_price`. The monitor adjusts stops at runtime (`candle_trail_stop`, breakeven moves, home_run trailing) but none of these adjustments are persisted.

**Impact**: Cannot compare "where was WB's stop at minute X?" vs "where was Ross's stop?"

**Fix**: Add a `stop_events` table or append stop adjustments to `trade_events` via `trade_event_service`.

### Gap 2: No Ross Exit Data in Structured Form
**Current state**: Ross's exit behavior exists only in freeform `notes` text (e.g., "Ross took partial at $5.50, stopped out remainder at $5.20").

**Impact**: Cannot programmatically compare WB exit timing/price vs Ross exit timing/price.

**Fix**: Add structured fields to `warrior_setups.yaml`: `ross_exit_time`, `ross_exit_price`, `ross_partials: [{price, shares_pct, time}]`, `ross_stop_adjustments: [{time, new_stop}]`.

### Gap 3: No Per-Tick Price/Position Snapshot
**Current state**: Only entry and exit points are recorded. No bar-by-bar snapshot of WB's position state (current_stop, unrealized P&L, candle_trail_stop, R-multiple).

**Impact**: Cannot render a timeline comparison or identify the exact bar where WB diverged from Ross.

**Fix**: Add optional per-bar telemetry logging to `evaluate_position` (sim mode only, performance-gated).

### Gap 4: `high_since_entry` Not in Batch Results
**Current state**: `high_since_entry` is tracked in `warrior_db` and updated during monitoring, but not included in the batch result `trades[]` output.

**Impact**: Cannot compute MFE from batch results (must query `entry_validation_log` separately).

**Fix**: Add `high_since_entry` to the trade dict in `_run_single_case_async`.

---

## 4. Proposed Diagnostic Script Design

### 4.1 Script: `scripts/gc_trade_management_diagnostic.py`

```
Usage: python scripts/gc_trade_management_diagnostic.py [--case CASE_ID] [--all] [--output-dir DIR]
```

### 4.2 Data Collection Pipeline

```mermaid
graph LR
    A[warrior_setups.yaml] -->|Ross data| D[Diagnostic Engine]
    B[/sim/run_batch_concurrent] -->|WB results| D
    C[entry_validation_log] -->|MFE/MAE| D
    D --> E[Per-Case Report]
```

### 4.3 Per-Case Diagnostic Report Fields

For each test case, the diagnostic produces:

#### Section A: Identity
- `case_id`, `symbol`, `date`

#### Section B: Entry Comparison
| Metric | Ross | WB | Delta |
|--------|------|-----|-------|
| Entry price | `expected.entry_near` | `entry_price` | diff |
| Entry time | `ross_entry_time` | `entry_time` | minutes late/early |
| Entry trigger | manual | `entry_trigger` | match? |

#### Section C: Trade Management Comparison
| Metric | Ross (from notes) | WB | Diagnosis |
|--------|-------------------|-----|-----------|
| Initial stop | `expected.stop_near` | `stop_price` | tighter/wider |
| Stop method | notes-derived | `stop_method` | match? |
| Exit mode | notes-derived | `exit_mode` | match? |
| Partial taken? | notes-derived | `partial_taken` | yes/no |
| Exit reason | notes-derived | `exit_reason` | category match? |
| Exit price | notes-derived | `exit_price` / `avg_exit_price` | diff |
| Exit time | notes-derived | `exit_time` | minutes early/late |
| P&L | `ross_pnl` | `pnl` | diff |

#### Section D: Excursion Analysis
| Metric | Value |
|--------|-------|
| MFE (High - Entry) | from `entry_validation_log` |
| MAE (Entry - Low) | from `entry_validation_log` |
| MFE captured % | `pnl / (MFE × shares)` |
| MAE exposure % | `mae / initial_risk` |
| R at exit | from exit signal |

#### Section E: Diagnosis Category

Based on comparing WB vs Ross for each case:

| Category | Trigger Condition |
|----------|-------------------|
| `BETTER_MANAGEMENT` | WB P&L > Ross P&L and both entered |
| `WORSE_MANAGEMENT` | WB P&L < Ross P&L and both entered |
| `EARLY_EXIT` | WB exited before peak, MFE >> realized P&L |
| `LATE_EXIT` | WB held past peak, MAE > 50% of MFE |
| `WRONG_STOP` | WB stopped out but Ross survived (stop too tight) |
| `MISSED_PARTIAL` | Ross took partial profit, WB did full exit or vice versa |
| `OVER_HELD` | WB exit > 5 min after Ross exit, with declining price |
| `NO_ENTRY` | WB didn't enter but Ross did |
| `GUARD_BLOCKED` | WB blocked by entry guard |
| `STOP_TOO_WIDE` | WB's stop was wider than Ross's, leading to larger loss |

### 4.4 Summary Statistics

Across all cases:

```
=== Trade Management Diagnostic Summary ===
Cases analyzed:        30
Cases where both entered: 22

MANAGEMENT QUALITY:
  Better than Ross:    8 cases  (+$12,340)
  Worse than Ross:     14 cases (-$18,550)
  
EXIT TIMING:
  Early exits:         6 cases  (avg $450 left on table per case)
  Late exits:          3 cases  (avg $280 given back per case)
  
STOP ANALYSIS:
  Stop too tight:      4 cases  (stopped out, Ross survived)
  Stop too wide:       2 cases  (larger loss than Ross)
  Stop matched:        16 cases
  
MFE CAPTURE:
  Average MFE capture: 42%  (capturing 42¢ of every $1 potential)
  Ross benchmark:      ~65% (estimated from notes)
```

### 4.5 Implementation Phases

**Phase 1 (No code changes, immediate):**
- Parse existing batch results + `warrior_setups.yaml`
- Compute entry/timing/P&L deltas
- Extract structured data from Ross `notes` via regex patterns
- Output per-case and summary report

**Phase 2 (Minor telemetry additions):**
- Add `high_since_entry` to batch trade output (Gap 4 fix)
- Integrate `entry_validation_log` data for MFE/MAE

**Phase 3 (Structured Ross data):**
- Add structured exit fields to `warrior_setups.yaml`
- Enable full exit timing/price comparison

**Phase 4 (Runtime telemetry):**
- Add stop adjustment event logging (Gap 1 fix)
- Add per-bar position snapshots for timeline view (Gap 3 fix, sim only)

---

## 5. Ross Notes Extraction Patterns

Many diagnostic fields for Ross can be extracted from the `notes` text in `warrior_setups.yaml` using these patterns:

```python
# Examples from actual notes:
# "Ross took small profit, exited quickly"
# "3 trades on ROLR... Ross added on the first 1min candle making a new high"
# "Ross stopped out ~$6.40"
# "Ross took partial near $5.50"
# "Ross used 1-min for entry, ABCD pattern"

PATTERNS = {
    "ross_exit_type": r"Ross (stopped out|took .* profit|exited|sold|cut)",
    "ross_partial": r"Ross took partial",
    "ross_added": r"Ross added",
    "ross_stop_price": r"stopped out [~$]*(\d+\.?\d*)",
    "ross_exit_price": r"sold [~$]*(\d+\.?\d*)|exited [~$]*(\d+\.?\d*)",
}
```

---

## 6. Dependencies & Prerequisites

| Dependency | Status | Notes |
|------------|--------|-------|
| Batch test endpoint | ✅ Ready | `POST /warrior/sim/run_batch_concurrent` |
| `warrior_setups.yaml` | ✅ Ready | Has Ross data for ~30 cases |
| `gc_batch_diagnose.py` | ✅ Ready | Has `deep_analyze_case` logic to reuse |
| `entry_validation_log` | ✅ Ready | Has MFE/MAE per trade |
| Structured Ross exit data | ❌ Missing | Requires manual annotation (Phase 3) |
| Stop event telemetry | ❌ Missing | Requires code change (Phase 4) |

---

## 7. Open Questions for Clay

1. **Priority**: Should Phase 1 focus on the cases with the largest P&L gaps, or cover all cases equally?
2. **Ross notes extraction**: Should we invest in automated extraction from `notes`, or manually annotate a structured `ross_exits` field for the ~30 cases?
3. **Output format**: Markdown report per-case, single summary report, or both?
4. **Scope**: Should the diagnostic also compare **number of trades** per case (Ross often takes 2-3 trades on the same symbol vs WB's behavior)?
