# Audit Validator Handoff: Adversarial Review of Dynamic Scoring

**Date:** 2026-03-03 12:14 ET  
**From:** Coordinator  
**To:** Audit Validator  
**Source Reports:**
- `nexus2/reports/2026-03-03/backend_status_dynamic_scoring.md`
- `nexus2/reports/2026-03-03/backend_status_scoring_timing_fix.md`
**Output:** `nexus2/reports/2026-03-03/validation_dynamic_scoring_adversarial.md`

---

## Mission

Two Backend Specialist runs modified 4+ files to add dynamic scoring and fix timing. Both reported $0 batch regression. We need adversarial verification that the implementation actually works — not just that it doesn't break.

---

## Challenge 1: "Zero extra computation" — Is MACD actually reusing existing data?

**Claim:** `update_candidate_technicals()` in `warrior_entry_helpers.py` now caches MACD histogram "from its existing snapshot (zero extra computation)."

**Investigate:**
```powershell
Select-String -Path "C:\Dev\Nexus\nexus2\domain\automation\warrior_entry_helpers.py" -Pattern "macd|histogram|cached_macd" -Context 3,3
```

**What to prove:** Does it pull MACD from data already fetched, or does it make a new API/data call? If there's a new fetch, quantify the performance impact.

---

## Challenge 2: Are ALL 6 dynamic factors flowing with real values, or just MACD?

**Claim:** Dynamic scoring adds 6 factors. The timing fix addressed MACD. But the status reports don't confirm the other 5 are populated.

**Investigate each factor in `warrior_engine_entry.py`:**
```powershell
Select-String -Path "C:\Dev\Nexus\nexus2\domain\automation\warrior_engine_entry.py" -Pattern "_macd_histogram|_ema_trend|_reentry_count|_vwap_distance|_vol_expansion|_extension_pct" -Context 1,3
```

For each factor, trace whether it reads from a populated source or falls through to `None` (→ 0.5 neutral):
- `macd_histogram` — Should now read from `watched.cached_macd_histogram`
- `ema_trend` — Should read from `watched.is_above_ema_9` / `watched.is_above_ema_20`
- `reentry_count` — Should read from `watched.entry_attempt_count`
- `vwap_distance_pct` — Should compute from `watched.current_vwap`
- `volume_expansion` — What does this read from? Is the source populated?
- `price_extension_pct` — Should compute from `watched.pmh`

**Key question:** Run a batch test with verbose scoring output. Do the `PatternCandidate.factors` show real values or `None`/`0.5` for each factor?

Create a quick test script:
```python
# tmp_check_factors.py — run one case and check factor values
import subprocess, json
result = subprocess.run(
    ["python", "scripts/gc_quick_test.py", "--case", "ross_cmct_20260109", "--verbose"],
    capture_output=True, text=True
)
# Look for "factors=" in output
for line in result.stdout.split('\n'):
    if 'factor' in line.lower() or 'score=' in line.lower():
        print(line)
```

---

## Challenge 3: Is $0 P&L change actually expected?

**Claim:** "MACD gate blocks < -0.02, so surviving entries always have favorable MACD. The scoring delta is only ±0.01 to ±0.05."

**Math check:** With 10% weight and MACD scores from 0.4-1.0:
- Best case delta from neutral: (1.0 - 0.5) × 0.10 = +0.05
- Worst case delta from neutral: (0.4 - 0.5) × 0.10 = -0.01
- Can -0.01 total score change push ANY case below the 0.40 threshold?

**Verify:** Find the lowest-scoring entries in the batch test. If any case has a score near 0.41-0.45, even a small MACD penalty could block it and change P&L.

```powershell
Select-String -Path "C:\Dev\Nexus\nexus2\domain\automation\warrior_entry_scoring.py" -Pattern "MIN_SCORE_THRESHOLD"
```

---

## Challenge 4: Scoring sensitivity — is the MACD curve right?

Clay tested and found:
- `compute_macd_score(0) = 0.4`
- `compute_macd_score(0.01) = 0.6`

That's a 50% jump for MACD going from 0.00 to 0.01. Is this the right sensitivity?

**Investigate:** What are typical MACD histogram values for the test cases? If most entries have histogram between -0.01 and 0.05, the scoring curve might be too coarse.

```powershell
Select-String -Path "C:\Dev\Nexus\nexus2\domain\automation\warrior_entry_scoring.py" -Pattern "def compute_macd_score" -Context 0,20
```

---

## Validation Report Format

```markdown
## Adversarial Validation: Dynamic Scoring

### Challenges
| # | Challenge | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Zero extra computation | PASS/FAIL | [command + output] |
| 2 | All 6 factors populated | PASS/FAIL/PARTIAL | [per-factor status] |
| 3 | $0 P&L change expected | PASS/SUSPICIOUS | [math + edge cases] |
| 4 | MACD sensitivity curve | APPROPRIATE/NEEDS_TUNING | [typical values + curve] |

### Overall Assessment
- Is the implementation actually exercising dynamic scoring?
- Or is it a no-op dressed up as a feature?
```
