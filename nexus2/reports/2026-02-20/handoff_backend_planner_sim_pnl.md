# Handoff: Backend Planner — Sim Engine P&L Investigation

## Verified Facts

**Finding:** Route handler for batch sim is `run_batch_concurrent_endpoint`
**File:** `nexus2/api/routes/warrior_sim_routes.py:1611`
**Code:** `@sim_router.post("/sim/run_batch_concurrent")`
**Verified with:** `Select-String -Path "nexus2\api\routes\*.py" -Pattern "run_batch_concurrent" -Recurse`
**Conclusion:** Route handler exists and calls `run_batch_concurrent` from `sim_context.py:643`

---

**Finding:** Core batch function lives in sim_context
**File:** `nexus2/adapters/simulation/sim_context.py:643`
**Code:** `async def run_batch_concurrent(cases: list, yaml_data: dict) -> list:`
**Verified with:** Same grep command above
**Conclusion:** This is the entry point for the sim engine batch runs

---

**Finding:** P&L is calculated in trade_management.py via accumulated `realized_pnl`
**File:** `nexus2/domain/positions/trade_management.py:147` and `:291`
**Code:** `trade.realized_pnl += pnl` (L147) and `trade.realized_pnl += final_pnl` (L291)
**Verified with:** `Select-String -Path "nexus2\domain\positions\trade_management.py" -Pattern "realized_pnl"`
**Conclusion:** P&L is accumulated incrementally, possibly across multiple partial exits. The displayed entry/exit prices may not match the actual fills used for P&L.

---

**Finding:** MLEC batch test reports positive P&L with entry > exit price
**Verified with:** `Invoke-RestMethod -Method POST -Uri "http://localhost:8000/warrior/sim/run_batch_concurrent" -ContentType "application/json" -Body '{"case_ids": ["ross_mlec_20260220"], "include_trades": true}'`
**Output:**
```json
{
  "entry_price": 19.96,
  "exit_price": 18.91,
  "shares": 1302,
  "pnl": 244.2,
  "entry_trigger": "whole_half_anticipatory",
  "exit_mode": "base_hit",
  "exit_reason": "mental_stop",
  "entry_time": "2026-02-20T23:16:57Z",
  "exit_time": "2026-02-20T23:16:58Z",
  "stop_price": "19.46",
  "stop_method": "consolidation_low"
}
```
**Conclusion:** (19.96 - 18.91) × 1302 = +$1,367 if short, -$1,367 if long. Neither matches +$244.19. P&L source is unknown.

---

**Finding:** Timestamps are wall-clock, not simulated market time
**Verified with:** Same command output above
**Output:** `entry_time: 2026-02-20T23:16:57Z` = 6:16 PM ET, well after market close
**Conclusion:** The sim engine appears to stamp trades with `datetime.utcnow()` at execution time rather than the simulated bar timestamp.

---

**Finding:** MLEC test case JSON structure uses `premarket` dict for metadata
**Verified with:** `python -c "import json; d=json.load(open('nexus2/tests/test_cases/intraday/ross_mlec_20260220.json')); print(list(d.keys()))"`
**Output:** `['symbol', 'date', 'premarket', 'continuity_bars', 'bars', 'source']`
**Conclusion:** Test case data structure is valid, issue is in sim engine processing, not input data.

## Open Questions

> [!IMPORTANT]
> These are investigation questions. Do NOT accept the coordinator's framing as fact.
> Verify everything independently through code research.

1. **Where is `realized_pnl` calculated?** Trace from the `/warrior/sim/run_batch_concurrent` route handler to the actual P&L math. What numbers feed into the final `realized_pnl` value?

2. **What populates the trade detail fields?** Where do `entry_price`, `exit_price`, `entry_time`, `exit_time` get set? Are they the same values used for P&L calculation, or are they serialized separately?

3. **Could the trade be a short position?** The math for a short (entry 19.96, exit 18.91) would be +$1,367 — but reported P&L is +$244. Investigate whether there's a short-selling path in the sim, and if so, what accounts for the remaining discrepancy.

4. **Why does exit_price ($18.91) differ from stop_price ($19.46)?** The stop is at $19.46 consolidation_low, but the exit is $18.91. What logic determines the actual exit price? Is there gap-down or bar-low logic?

5. **Are there multiple fills being averaged or aggregated?** Could entry_price/exit_price show only the first/last fill while P&L uses all fills?

6. **Is the +$244.19 P&L actually correct, and the displayed prices wrong?** Or vice versa?

## Verified Starting Points
- Route handler: `nexus2/api/routes/warrior_sim_routes.py:1611` → `run_batch_concurrent_endpoint`
- Core batch function: `nexus2/adapters/simulation/sim_context.py:643` → `run_batch_concurrent`
- P&L accumulation: `nexus2/domain/positions/trade_management.py:147` and `:291`
- Trade model: `nexus2/domain/positions/trade_models.py:126` → `realized_pnl: Decimal`

## Output
Write findings to: `nexus2/reports/2026-02-20/spec_sim_pnl_investigation.md`
