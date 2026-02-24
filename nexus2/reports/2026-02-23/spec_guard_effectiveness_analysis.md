# Guard Effectiveness Analysis — Implementation Spec

**Date:** 2026-02-23  
**Context:** Batch diagnosis shows GUARD_BLOCKED as P1 issue (~$223K P&L gap, 7,382 blocks across 12 cases). We need to determine whether guards are protecting bad entries or being overly aggressive.

---

## Phase 1: A/B Batch Runs (Quick Win)

**Goal:** Run the same test cases with guards disabled and compare total P&L to understand the net impact of guards.

### Changes Required

#### 1. Add `skip_guards` param to `BatchTestRequest`

**File:** [warrior_sim_routes.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py)

```python
class BatchTestRequest(BaseModel):
    case_ids: list[str] | None = None
    include_trades: bool = False
    skip_guards: bool = False  # NEW: Run without entry guards for A/B comparison
```

#### 2. Thread `skip_guards` through sim pipeline

**File:** [sim_context.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py)

- `run_batch_concurrent(cases, yaml_data, skip_guards=False)` → pass to each worker
- `_run_case_sync(case, yaml_data, skip_guards=False)` → pass to engine config
- The `WarriorEngine` instance in sim context needs a `skip_guards` flag

#### 3. Respect `skip_guards` in entry guards

**File:** [warrior_entry_guards.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py)

```python
async def check_entry_guards(engine, watched, current_price, trigger_type):
    # NEW: If guards are disabled (A/B testing mode), allow entry
    if getattr(engine, 'skip_guards', False):
        logger.info(f"[Guard A/B] {watched.symbol}: Guards SKIPPED (A/B test mode)")
        return True, ""
    # ... existing guard logic ...
```

> [!WARNING]
> `skip_guards` must ONLY be available in sim mode. Never expose to live trading.
> Add assertion: `assert engine.is_sim_mode, "skip_guards only allowed in simulation"`

#### 4. Add comparison endpoint or script

**Option A:** New endpoint `POST /warrior/sim/run_batch_ab_comparison`
- Runs batch twice (guards on, guards off), returns side-by-side comparison
- Downside: Takes 2x time (~4-10 min)

**Option B (recommended):** Add `skip_guards` to existing endpoint, let the diagnosis script run twice
- Simpler, no new endpoint
- Script handles comparison logic

### Expected Output

```
A/B Guard Comparison (35 cases)
─────────────────────────────────
                 Guards ON    Guards OFF    Delta
Bot Total:       $136,993     $???          +/- $???
Ross Total:      $432,999     $432,999      (same)
Capture:         31.6%        ???%          +/- ???%

Per-Case Deltas (cases where guards made a difference):
  PAVM: Guards ON $105 vs OFF $??? (guards cost/saved $???)
  HIND: Guards ON $14,110 vs OFF $??? (guards cost/saved $???)
```

---

## Phase 2: Counterfactual Guard Analysis (Surgical Precision)

**Goal:** For each blocked entry, determine what would have happened if the guard had NOT blocked it, using the actual bar data.

### Design

When a guard blocks an entry during simulation, we already log the event with:
- `guard`: guard type (e.g., "MACD_GATE", "VWAP_BELOW")
- `reason`: human-readable explanation
- `symbol`: stock symbol

**We need to additionally capture:**
- `blocked_price`: the entry price that would have been used
- `blocked_time`: the sim clock time when the block occurred
- `bar_index`: which bar we're on (for later lookback)

Then, **after the sim day completes**, we retroactively check:
- What was the price 5 min, 15 min, 30 min after the block?
- What was the max favorable excursion (MFE) before the next block/entry?
- What was the max adverse excursion (MAE)?

### Changes Required

#### 1. Enrich guard block events with price/time context

**File:** [trade_event_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/trading/trade_event_service.py)

Add `blocked_price` and `blocked_time` to the guard block log event metadata. These can go in the existing `reason` field as structured JSON, or as new columns.

**Recommended:** Use the `metadata` JSON field pattern:
```python
metadata = {
    "blocked_price": float(entry_price),
    "blocked_time": sim_clock.now().isoformat(),
    "guard_type": guard_name,
    "reason": reason_text,
}
```

#### 2. Post-sim counterfactual analysis

**File:** New function in [sim_context.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py)

After the sim run completes, iterate through guard blocks and check the bar data:

```python
def analyze_guard_outcomes(guard_blocks, bars, symbol):
    """For each guard block, check what price did after the block."""
    outcomes = []
    for block in guard_blocks:
        block_time = block["blocked_time"]
        block_price = block["blocked_price"]
        
        # Find bars after the block
        future_bars = [b for b in bars if b.timestamp > block_time]
        
        if not future_bars:
            continue
        
        # Check price at +5, +15, +30 min
        price_5m = find_price_at_offset(future_bars, minutes=5)
        price_15m = find_price_at_offset(future_bars, minutes=15)
        price_30m = find_price_at_offset(future_bars, minutes=30)
        
        # MFE/MAE
        highs = [b.high for b in future_bars[:30]]  # Next 30 bars
        lows = [b.low for b in future_bars[:30]]
        mfe = max(highs) - block_price if highs else 0
        mae = block_price - min(lows) if lows else 0
        
        outcome = "CORRECT_BLOCK" if price_15m < block_price else "MISSED_OPPORTUNITY"
        
        outcomes.append({
            "guard": block["guard"],
            "blocked_price": block_price,
            "blocked_time": block_time,
            "price_5m": price_5m,
            "price_15m": price_15m,
            "price_30m": price_30m,
            "mfe": mfe,
            "mae": mae,
            "outcome": outcome,
            "hypothetical_pnl_15m": price_15m - block_price,  # Simplified
        })
    
    return outcomes
```

#### 3. Add counterfactual results to batch output

Include `guard_analysis` in each case result:
```json
{
    "case_id": "PAVM_2025-12-19",
    "guard_analysis": {
        "total_blocks": 47,
        "correct_blocks": 28,
        "missed_opportunities": 19,
        "guard_accuracy": 0.596,
        "hypothetical_pnl_saved": 1250.00,
        "hypothetical_pnl_missed": -3400.00,
        "net_guard_impact": -2150.00,
        "by_guard_type": {
            "MACD_GATE": {"blocks": 22, "accuracy": 0.45, "net_impact": -1800.00},
            "VWAP_BELOW": {"blocks": 15, "accuracy": 0.80, "net_impact": 650.00},
            "COOLDOWN": {"blocks": 10, "accuracy": 0.60, "net_impact": -1000.00}
        }
    }
}
```

### Key Design Decisions

1. **"Correct" threshold**: Block is "correct" if price is lower than block price within 15 min. This is simplified — could also use a risk-adjusted measure.

2. **Hypothetical P&L**: Uses a simple `price_Xm - block_price` calculation. Not perfectly realistic (ignores stop placement, position sizing), but directionally accurate.

3. **Position sizing assumption**: For hypothetical P&L, assume the same position size the bot was going to use (from the entry sizing logic).

---

## Implementation Order

| Phase | Feature | Effort | Specialist |
|-------|---------|--------|------------|
| 1a | `skip_guards` param in `BatchTestRequest` | Small | Backend |
| 1b | Thread through sim pipeline | Small | Backend |
| 1c | A/B comparison in diagnosis script | Small | Backend |
| 2a | Enrich guard blocks with price/time | Medium | Backend |
| 2b | Post-sim counterfactual analysis | Medium | Backend |
| 2c | Add to batch output + diagnosis report | Medium | Backend |

**Phase 1 total: ~1 Backend Specialist session**  
**Phase 2 total: ~1-2 Backend Specialist sessions**

---

## Verification Plan

### Phase 1 (A/B)
1. Run `POST /warrior/sim/run_batch_concurrent` with `skip_guards: false` (baseline)
2. Run `POST /warrior/sim/run_batch_concurrent` with `skip_guards: true`
3. Compare total P&L across all cases
4. If guards-off P&L is significantly higher → guards too aggressive
5. If guards-off P&L is similar/worse → guards are doing their job

### Phase 2 (Counterfactual)
1. Run batch with counterfactual analysis enabled
2. Check per-guard-type accuracy rates
3. Identify guards with <50% accuracy as candidates for relaxation
4. Validate that "MISSED_OPPORTUNITY" blocks align with Ross's profitable re-entries
