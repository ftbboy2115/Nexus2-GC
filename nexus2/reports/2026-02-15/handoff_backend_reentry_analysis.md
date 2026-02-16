# Backend Planner Handoff: Re-Entry Quality Gate Analysis

## Task
Analyze ALL 14 cases affected by re-entries and propose **quality gates** that allow good re-entries while blocking bad ones.

## Context & A/B Data

Current state: re-entries are unrestricted (`max_reentry_count=99` in `warrior_types.py:108`).
An `entry_attempt_count` is incremented in `enter_position` (`warrior_engine_entry.py:1053`) and
a gate exists at the top of `enter_position` (`warrior_engine_entry.py:980-986`) but is inactive.

### Cases HURT by blocking re-entries (re-entries are GOOD here):
| Case | With Re-Entry | No Re-Entry | Delta |
|------|--------------|-------------|-------|
| BATL_0127 | $2,485 | -$434 | -$2,919 |
| VERO | $966 | $121 | -$845 |
| ROLR | $1,539 | $820 | -$719 |
| TNMG | $215 | -$12 | -$228 |
| EVMN | $386 | $170 | -$216 |
| DCX | $327 | $118 | -$209 |
| BNAI | $257 | $67 | -$190 |
| BNKK | $177 | $37 | -$140 |

### Cases HELPED by blocking re-entries (re-entries are BAD here):
| Case | With Re-Entry | No Re-Entry | Delta |
|------|--------------|-------------|-------|
| GWAV | $216 | $631 | +$415 |
| MNTS | -$704 | -$317 | +$388 |
| LRHC | -$98 | $178 | +$276 |
| PAVM | -$146 | $27 | +$174 |
| MLEC | -$100 | $65 | +$166 |
| BATL_0126 | -$176 | $67 | +$243 |

## Investigation Steps

For EACH of the 14 cases above:

1. **Load the test case JSON** from `nexus2/tests/test_cases/intraday/ross_<case_id>.json`
2. **Identify re-entry timing**: When did Trade 1 exit? When did Trade 2 enter?
3. **Check conditions at re-entry time**:
   - Was price above/below VWAP?
   - What was MACD signal (bullish/bearish)?
   - Volume trend (expanding or contracting)?
   - Price vs HOD (% off high)?
   - Time of re-entry (early morning vs late day)?
4. **Classify** each re-entry: GOOD (adds P&L) vs BAD (loses P&L)
5. **Find the discriminating features** — what separates good re-entries from bad ones?

## Key Files
- Re-entry gate: `nexus2/domain/automation/warrior_engine_entry.py:977-986`
- Entry count increment: `warrior_engine_entry.py:1053`
- Config: `nexus2/domain/automation/warrior_types.py:108` (`max_reentry_count`)
- `_handle_profit_exit`: `nexus2/domain/automation/warrior_engine.py:224-231`
- PMH crossover reset: `warrior_engine_entry.py:548-554`
- Test cases: `nexus2/tests/test_cases/intraday/`
- Entry patterns: `warrior_engine_entry.py` (detect_* functions)
- Entry guards: `nexus2/domain/automation/warrior_entry_guards.py`

## Deliverable
Write findings to: `nexus2/reports/2026-02-15/analysis_reentry_quality.md`

Structure:
1. **Per-case analysis table** (re-entry time, conditions, outcome)
2. **Discriminating features** (what separates good from bad)
3. **Proposed quality gates** with specific implementation details
4. **Expected P&L impact** of proposed gates
