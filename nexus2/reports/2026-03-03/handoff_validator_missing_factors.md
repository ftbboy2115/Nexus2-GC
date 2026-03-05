# Audit Validator Handoff: Missing Factors Fix

**Date:** 2026-03-03 13:32 ET  
**From:** Coordinator  
**To:** Audit Validator  
**Source:** `nexus2/reports/2026-03-03/backend_status_missing_factors_fix.md`  
**Output:** `nexus2/reports/2026-03-03/validation_missing_factors_fix.md`

---

## Mission

Third round of dynamic scoring changes. Verify volume expansion and HOD proximity are actually working — not another no-op. **$0 P&L change for the 3rd time is suspicious.** Challenge hard.

---

## Challenge 1: Is volume expansion actually computing real values now?

**Claim:** `cached_vol_expansion_ratio` is computed in `update_candidate_technicals()` using already-fetched candles.

**Verify:**
```powershell
Select-String -Path "C:\Dev\Nexus\nexus2\domain\automation\warrior_entry_helpers.py" -Pattern "vol_expansion|cached_vol" -Context 3,3
Select-String -Path "C:\Dev\Nexus\nexus2\domain\automation\warrior_engine_entry.py" -Pattern "vol_expansion" -Context 1,3
```

**Key questions:**
- Does the computation actually execute, or is it guarded by a condition that's rarely true?
- What candle data does it use? Are those candles populated in batch mode?
- Create a test: run one case verbose and check if `vol_expansion` shows a real value (not None/0.5)

---

## Challenge 2: Is HOD proximity computing real values?

**Claim:** `watched.recent_high` is used to compute HOD proximity percentage.

**Verify:**
```powershell
Select-String -Path "C:\Dev\Nexus\nexus2\domain\automation\warrior_engine_entry.py" -Pattern "hod_proximity|recent_high" -Context 1,3
```

**Key questions:**
- Is `watched.recent_high` populated in batch mode? When is it first set?
- If `recent_high` is None or 0 on first entry, does HOD default to neutral again?

---

## Challenge 3: Why is P&L STILL $0 after 3 rounds of changes?

This is the third time we've gotten exactly $0 change. The explanations have been:
1. Round 1: "Dynamic factors default to neutral" — fixed in Round 2
2. Round 2: "MACD range too narrow to cross threshold" — plausible
3. Round 3: ???

**Run a single case with trade details:**
```powershell
python scripts/gc_quick_test.py ross_cmct_20260109 --trades
```

**What to look for:** Are the dynamic factor values in the PatternCandidate.factors dict showing real numbers, or are they all None/0.5/neutral?

Note: `gc_quick_test.py` does NOT have `--case` or `--verbose` flags. Use positional case name + `--trades` for detail. If trade-level scoring output isn't logged, add temporary debug prints to `warrior_engine_entry.py` to capture factor values.

---

## Challenge 4: Weight math sanity check

**Claim:** Weights rebalanced to 53/47 static/dynamic.

**Verify:** Read `score_pattern()` and sum ALL weights. They must equal 1.0 (100%).
```powershell
Select-String -Path "C:\Dev\Nexus\nexus2\domain\automation\warrior_entry_scoring.py" -Pattern "\* 0\." -Context 0,0
```

---

## Challenge 5: Are ALL 8 dynamic factors flowing with real values?

Complete audit — for EACH factor, confirm it's reading real data:

| Factor | Variable | Expected Source |
|--------|----------|----------------|
| MACD | `cached_macd_histogram` | `update_candidate_technicals` |
| EMA trend | `is_above_ema_9` + `is_above_ema_20` | `update_candidate_technicals` |
| Re-entry | `entry_attempt_count` | `WatchedCandidate` counter |
| VWAP | `current_vwap` | `update_candidate_technicals` |
| Vol expansion | `cached_vol_expansion_ratio` | `update_candidate_technicals` |
| Price extension | `pmh` vs `current_price` | Computed inline |
| HOD proximity | `recent_high` vs `current_price` | Computed inline |
| (check for others) | | |

---

## Report Format

```markdown
## Validation: Missing Factors Fix

### Per-Factor Status
| Factor | Real Value? | Evidence |
|--------|------------|----------|
| MACD | YES/NO | [value seen in test] |
| EMA | YES/NO | [value seen in test] |
| ... | | |

### Is this feature a no-op?
YES / NO — with evidence from a verbose batch test case

### Weight Sum
Total: [X] (must be 1.0)
```
