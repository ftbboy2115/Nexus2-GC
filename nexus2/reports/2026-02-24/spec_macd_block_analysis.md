# MACD Block Bucket Analysis — Technical Spec

**Agent:** Backend Planner  
**Date:** 2026-02-24  
**Output:** `nexus2/reports/2026-02-24/spec_macd_block_analysis.md`

---

## A. Existing Infrastructure Analysis

The MACD block analysis is feasible **without production code changes** using existing infrastructure. Here's what's already in place:

### A1. MACD Gate Implementation

**File:** [warrior_entry_guards.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py#L174-L240)

The gate blocks when BOTH conditions are true:
```python
# Line 216
if histogram < tolerance and snapshot.macd_crossover != "bullish":
```

- `tolerance` = `engine.config.macd_histogram_tolerance` (default **-0.02**)
- `crossover` detection: only "bullish" when `prev_hist < 0 AND curr_hist > 0` on the immediately preceding bar (line 194 of technical_service.py)

> [!IMPORTANT]  
> All 8,884 blocks therefore have **histogram < -0.02** AND **crossover ≠ "bullish"**.  
> The buckets must classify within the `histogram < -0.02` range, not `< 0`.

### A2. Guard Block Data Already Captured

**File:** [sim_context.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L708-L761)

Each batch result already includes per-block detail:
```python
guard_blocks = [{
    "guard": "macd",                    # guard type (line 721)
    "reason": "MACD GATE - blocking entry (histogram=-0.0847 < tolerance=-0.02, crossover=neutral)...",
    "blocked_price": 5.42,              # from metadata (line 729)
    "blocked_time": "09:35",            # from metadata (line 730)
}]
```

**Key finding:** The histogram value is embedded in the `reason` string, parseable via regex:
```
histogram=(-?\d+\.\d+) < tolerance=(-?\d+\.\d+), crossover=(\w+)
```

### A3. Counterfactual Analysis Already Exists

**File:** [sim_context.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L774-L904)

`analyze_guard_outcomes()` already computes for each block:
- `price_5m`, `price_15m`, `price_30m` — price at future horizons
- `mfe` / `mae` — max favorable/adverse excursion over next 30 bars
- `outcome` — "CORRECT_BLOCK" or "MISSED_OPPORTUNITY" (based on price_15m)
- `hypothetical_pnl_15m` — per-share P&L if the trade had been taken

This data is already available in the `guard_analysis` field per case result.

### A4. Crossover Detection (Limitation)

**File:** [technical_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/indicators/technical_service.py#L191-L197)

```python
# Lines 192-197 — crossover detection
if len(macd_df) >= 2:
    prev_hist = float(macd_df[hist_col].iloc[-2])
    if prev_hist < 0 and macd_hist > 0:
        crossover = "bullish"
    elif prev_hist > 0 and macd_hist < 0:
        crossover = "bearish"
```

> [!WARNING]
> Crossover is **point-in-time only** — it's "bullish" only on the exact bar where histogram flips from negative to positive. If histogram was positive 3 bars ago but dipped back to -0.03 on a pullback candle, crossover = "neutral". This is the root cause of Bucket C over-blocking.

### A5. What's NOT Captured

The current system does **not** log:
1. MACD histogram trajectory (last 5 bars' histogram values) at block time
2. Whether the histogram was positive within the last N bars
3. MACD line vs signal line values (only histogram)

Bucket C classification requires this trajectory data. Two approaches to get it:
- **Approach 1 (offline script):** Re-run MACD calculation on bar data at each block timestamp
- **Approach 2 (instrument gate):** Add histogram history to metadata at block time

---

## B. Bucket Classification Criteria

All 8,884 blocks have `histogram < -0.02`. The buckets subdivide this range:

| Bucket | Histogram Range | Recent History | Interpretation |
|--------|----------------|----------------|----------------|
| **A** (Deeply Negative) | `< -0.10` | Any | Stock in clear downtrend on 1-min chart. Ross would NOT trade. **Legitimate block.** |
| **B** (Near-Zero Oscillation) | `-0.10` to `-0.02` | No positive hist in last 5 bars | MACD consolidating near zero line. Tolerance tuning candidate. |
| **C** (Recently-Crossed-Then-Dipped) | `-0.10` to `-0.02` | Histogram was `> 0` within last 5 bars | MACD had crossed bullish but pulled back. Ross would likely still consider this "green light." **Over-blocking candidate.** |

### Classification Logic (Pseudocode)

```python
def classify_macd_block(histogram_value, recent_5_bar_histograms):
    if histogram_value < -0.10:
        return "A"  # Deeply negative — legitimate

    # histogram between -0.10 and tolerance (-0.02)
    if any(h > 0 for h in recent_5_bar_histograms):
        return "C"  # Recently crossed, now dipped — over-blocking
    else:
        return "B"  # Near-zero oscillation — tolerance tuning
```

---

## C. Recommended Implementation: Standalone Analysis Script

### Why a Script (Not Code Changes)

1. This is a **one-time analysis** to inform a design decision
2. All data needed is already in the batch API response
3. The only missing piece (Bucket C trajectory) can be computed offline from bar data
4. No risk of production regression

### Script Design

#### Step 1: Run Batch Test via API

```python
# POST /warrior/sim/run_batch_concurrent
# Response includes guard_blocks[] and guard_analysis per case
```

#### Step 2: Filter MACD Blocks

```python
macd_blocks = []
for result in batch_results:
    for block in result["guard_blocks"]:
        if block["guard"] == "macd":
            # Parse histogram from reason string
            match = re.search(r"histogram=(-?[\d.]+)", block["reason"])
            histogram = float(match.group(1)) if match else None
            
            match2 = re.search(r"crossover=(\w+)", block["reason"])
            crossover = match2.group(1) if match2 else "unknown"
            
            macd_blocks.append({
                "case_id": result["case_id"],
                "symbol": result["symbol"],
                "histogram": histogram,
                "crossover": crossover,
                "blocked_price": block.get("blocked_price"),
                "blocked_time": block.get("blocked_time"),
            })
```

#### Step 3: Compute Bucket C (Recent History)

For each block where `-0.10 <= histogram < -0.02`:

```python
# Load bars for this case up to block_time
# Compute MACD for the preceding 5 bars using TechnicalService
# Check if any of those 5 bars had histogram > 0
# If yes → Bucket C; if no → Bucket B
```

> [!NOTE]
> This requires importing `TechnicalService` and the `HistoricalBarLoader` to replay MACD for each block's timestamp. The sim infrastructure already supports this — see `sim_get_intraday_bars()` at [sim_context.py:370-393](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L370-L393).

#### Step 4: Merge with Counterfactual P&L

Cross-reference each MACD block with the existing `guard_analysis.details[]` outcomes:

```python
for block in macd_blocks:
    # Find matching entry in guard_analysis.details by blocked_time + guard type
    # Extract: outcome (CORRECT_BLOCK / MISSED_OPPORTUNITY), hypothetical_pnl_15m, mfe, mae
```

#### Step 5: Aggregate and Report

```python
# Per bucket:
#   count, avg_histogram, SAVED count, COST count, NEUTRAL count, net_pnl_impact
# Plus histogram distribution (text-based chart)
```

### Change Surface for the Script

| # | File | Change | Purpose |
|---|------|--------|---------|
| 1 | **[NEW]** `scripts/analyze_macd_blocks.py` | New standalone script | Runs batch, classifies blocks, outputs report |

**No production code modifications required.**

### Script Dependencies

- `urllib.request` (already used by `gc_batch_diagnose.py`)
- `re` (stdlib — for parsing histogram from reason strings)
- `pandas_ta` (already installed — for MACD trajectory computation)
- `HistoricalBarLoader` + `TechnicalService` (imported from nexus2, for Bucket C trajectory)

---

## D. Implementation for Backend Specialist

### File: `scripts/analyze_macd_blocks.py`

**Template to follow:** `scripts/gc_batch_diagnose.py` (same API pattern, same fetch_json helper)

**Structure:**
1. `fetch_json()` — reuse from gc_batch_diagnose.py
2. `parse_macd_from_reason(reason: str) -> (float, str)` — extract histogram + crossover
3. `compute_macd_trajectory(case_id, symbol, block_time) -> list[float]` — compute 5-bar MACD history at block time
4. `classify_block(histogram, trajectory) -> str` — return "A", "B", or "C"
5. `main()` — orchestrate: run batch → filter MACD blocks → classify → cross-reference counterfactual → report

### Key Implementation Notes

1. **The histogram value regex pattern is:**
   ```
   MACD GATE - blocking entry (histogram=(-?[\d.]+) < tolerance=(-?[\d.]+), crossover=(\w+))
   ```
   Verified from the gate's reason format at [warrior_entry_guards.py:217-221](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py#L217-L221).

2. **For Bucket C trajectory computation**, the script needs to:
   - Load the test case bar data for each symbol (using `HistoricalBarLoader`)
   - Compute MACD at each of the 5 bars preceding `blocked_time`
   - Check if any histogram was > 0

3. **For counterfactual cross-reference**, the `guard_analysis.details[]` already contains per-block outcomes. Match by `blocked_time` and `guard == "macd"`.

4. **Bucket C "COST" metric is the key output.** If Bucket C blocks show more MISSED_OPPORTUNITY than CORRECT_BLOCK, we have methodology-grounded evidence to add a "recently-crossed buffer."

---

## E. Expected Output Format

```
MACD Block Bucket Analysis (N cases, 8,884 blocks)
===================================================

Histogram Distribution:
  < -0.50:  ████████████  1,234 blocks
  -0.50 to -0.30:  ██████  678 blocks
  -0.30 to -0.10:  ████████████████  2,345 blocks
  -0.10 to -0.05:  ██████████  1,567 blocks
  -0.05 to -0.02:  ████████  1,234 blocks
  (Note: -0.02 to 0 = tolerance zone, not blocked)

Bucket Classification:
| Bucket | Count | % of Total | Avg Histogram | SAVED | COST | NEUTRAL | Net P&L/share |
|--------|-------|-----------|---------------|-------|------|---------|---------------|
| A (deeply negative)       | ? | ?% | ? | ? | ? | ? | ? |
| B (near-zero oscillation) | ? | ?% | ? | ? | ? | ? | ? |
| C (recently-crossed-dipped)| ? | ?% | ? | ? | ? | ? | ? |

Recommendation:
[Based on data: widen tolerance, add recently-crossed buffer, or keep as-is]
```

---

## F. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Histogram parsing fails (reason format changed) | Low | Blocks unclassified | Fallback: log unparseables, verify against current code |
| Bucket C trajectory computation is slow | Medium | Script takes >10 min | Only compute for blocks in B/C range (not A) |
| 8,884 count includes non-MACD blocks | Low | Over-count | Filter by `guard == "macd"` |
| Counterfactual P&L not available for all blocks | Medium | Incomplete analysis | Report coverage % |

---

## G. Answers to Handoff Open Questions

### Q1: Does the batch test currently log individual MACD block histogram values, or just the count?

**Answer: Yes, but embedded in the reason string, not as a structured field.**

**Finding:** At [warrior_entry_guards.py:217-221](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py#L217-L221), the block reason includes `histogram=X.XXXX`. This is stored in the `reason` field of each guard block entry, which is extracted from DB at [sim_context.py:720-733](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L720-L733). Parseable via regex.

**Verified:** Reason format string:
```python
reason = (
    f"MACD GATE - blocking entry "
    f"(histogram={histogram:.4f} < tolerance={tolerance}, "
    f"crossover={snapshot.macd_crossover}) - MACD too negative for entry"
)
```

### Q2: Can we access the historical MACD trajectory (last 5 bars) at time of block without significant code changes?

**Answer: Yes, but offline only (not from existing logged data).**

The trajectory is NOT currently logged. However, the script can reconstruct it:
1. Load bar data for each case via `HistoricalBarLoader` (already used by sim)
2. For each block's `blocked_time`, get bars up to that time
3. Compute MACD via `TechnicalService.get_snapshot()` for each of the preceding 5 bars
4. Check if any had histogram > 0

This requires no production code changes — just import the existing classes in a script.

### Q3: Is the guard block logging (with blocked_time and blocked_price) from the recent guard analysis work sufficient?

**Answer: Yes, for Buckets A and B. Insufficient for Bucket C without trajectory computation.**

The existing data provides:
- ✅ `blocked_price` — for counterfactual P&L (already computed by `analyze_guard_outcomes()`)
- ✅ `blocked_time` — for timeline analysis and bar lookup
- ✅ `histogram` value — parseable from reason string
- ✅ `crossover` state — parseable from reason string
- ❌ Recent histogram trajectory — must be computed offline from bar data

---

## H. Wiring Checklist (for Backend Specialist)

- [ ] Create `scripts/analyze_macd_blocks.py`
- [ ] Implement `parse_macd_from_reason()` with regex
- [ ] Implement `compute_macd_trajectory()` using `HistoricalBarLoader` + `TechnicalService`
- [ ] Implement `classify_block()` with A/B/C logic
- [ ] Run batch via API, filter MACD blocks
- [ ] Cross-reference with `guard_analysis.details[]` for counterfactual outcomes
- [ ] Generate text-based histogram distribution chart
- [ ] Generate per-bucket summary table with SAVED/COST/NEUTRAL counts
- [ ] Write recommendation based on Bucket C data
- [ ] Output report as both stdout and markdown file
