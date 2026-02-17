# Handoff: Trace Why Bot Shows $0 P&L on Profitable Ross Trades

## Objective
For each case where Ross traded profitably but the bot produced $0 P&L (never entered),
trace the exact code path to find **what specifically blocked entry**. Cite file:line and
paste the exact guard condition or logic branch that prevented the trade.

---

## Target Cases

| # | Symbol | Date | Ross P&L | Case ID | Why $0 Matters |
|---|--------|------|----------|---------|----------------|
| 1 | HIND | 2026-01-27 | +$55,252 | ross_hind_20260127 | Biggest $0 gap |
| 2 | CMCT | 2025-12-22 | +$10,806 | cmct_2025_12_22 | ~$11K left on table |
| 3 | PRFX | 2026-02-11 | +$5,971 | ross_prfx_20260211 | ~$6K left on table |
| 4 | OPTX | 2026-01-06 | +$3,605 | optx_2026_01_06 | ~$3.6K left on table |

**Total gap from non-entries: $75,634**

---

## Investigation Method

For EACH case:

### Step 1: Check if the case loads successfully
- Is the case included in the batch run? (check `warrior_setups.yaml` status field)
- Does the sim engine pick it up? (check `sim_context.py` filtering logic)

### Step 2: Check if entry triggers fire
- `warrior_engine_entry.py` — does `check_entry_triggers()` ever consider this symbol?
- What trigger type would this case match? (PMH break, HOD break, VWAP break, etc.)
- Does the price data reach the trigger level?

Key files:
- `nexus2/domain/automation/warrior_engine_entry.py` — entry trigger logic
- `nexus2/domain/automation/warrior_entry_guards.py` — guard clauses that block entries
- `nexus2/domain/automation/warrior_engine.py` — main engine loop

### Step 3: Check if guards block entry
If the trigger fires but entry is blocked, which guard?
- `check_macd_gate` — MACD histogram/crossover check
- `check_position_guard` — max positions check  
- `check_sim_cooldown` — sim-specific cooldown
- `check_reentry_loss` — re-entry after loss block
- Other guards in `warrior_entry_guards.py`

### Step 4: Check the TML log
Search `data/warrior_trade.log` for each symbol. If the symbol appears in GUARD_BLOCK events, that tells us what blocked it. If the symbol doesn't appear at all, it means the trigger never fired.

```powershell
Select-String -Path "data\warrior_trade.log" -Pattern "HIND"
Select-String -Path "data\warrior_trade.log" -Pattern "CMCT"
Select-String -Path "data\warrior_trade.log" -Pattern "PRFX"
Select-String -Path "data\warrior_trade.log" -Pattern "OPTX"
```

### Step 5: Check premarket data
- Does the YAML case have valid premarket data?
- Is the `premarket_high` set correctly?
- Does the intraday data contain the expected price action?

Intraday files (if they exist):
- `nexus2/tests/test_cases/intraday/ross_hind_20260127.json`
- `nexus2/tests/test_cases/intraday/ross_prfx_20260211.json`
- For CMCT and OPTX: check if intraday files exist at all

---

## Output

Write findings to: `nexus2/reports/2026-02-16/findings_zero_pnl_cases.md`

For EACH case, document:
1. **Root cause**: What specifically blocked entry (guard name, file:line, code snippet)
2. **TML evidence**: What appeared (or didn't) in the trade log
3. **Price data check**: Did the expected entry price actually occur in the bar data?
4. **Fixability**: Is this a bug, a missing feature, or working-as-designed?

**CRITICAL: Paste actual code snippets and command outputs. No claims without evidence.**
