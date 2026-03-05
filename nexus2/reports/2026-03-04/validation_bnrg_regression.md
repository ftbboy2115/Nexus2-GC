# Validation Report: BNRG Regression Claims

**Date:** 2026-03-04 14:55 ET  
**Validator:** Audit Validator  
**Source:** `research_bnrg_regression.md`  
**Strategy:** `warrior.md` §8.1

---

## Claim Verification Table

| # | Claim | Result | Summary |
|---|-------|--------|---------|
| 1 | `relative_volume` defaults to 0 in sim | **FAIL** | Hardcoded to `Decimal("10.0")` |
| 2 | RVOL bypass disables MACD gate in sim | **FAIL** | RVOL=10.0 ≥ 5.0 → bypass never triggers |
| 3 | Regressions from RVOL bypass, not falling knife | **FAIL** | Root cause is wrong (bypass doesn't fire) |
| 4 | MACD gate is unconditional; 5x RVOL is for entry signals only | **PASS** | Correct interpretation of warrior.md §8.1 |
| 5 | Fix: remove RVOL bypass block | **PARTIAL** | Logic is wrong, but removal is moot for regressions |

## Overall Rating: **LOW** — Major factual error invalidates root cause analysis

> [!CAUTION]
> **The entire root cause theory is built on a false premise.** The research claims that
> `relative_volume` defaults to 0 in sim, causing the RVOL bypass to disable the MACD gate
> for ALL test cases. In fact, both sim paths hardcode `relative_volume=Decimal("10.0")`,
> so the bypass block **never executes** in sim. The BNRG/NPT regressions must have a
> different root cause.

---

## Detailed Verifications

### Claim 1: "relative_volume is never populated in sim — defaults to 0 via getattr(..., 0)"

**Claim:** `relative_volume` is never populated for sim candidates, so `getattr(watched.candidate, 'relative_volume', 0) or 0` always returns `0.0` in sim.

**Verification Command 1:** `Select-String -Path "nexus2\tests\test_cases\intraday\ross_bnrg_20260211.json" -Pattern "relative_volume"`  
**Actual Output:** (empty — no match)  
**Notes:** Correct that test case JSON files don't contain `relative_volume`.

**Verification Command 2:** `grep_search` for `relative_volume` in `sim_context.py`  
**Actual Output:**
```
sim_context.py:283:  relative_volume=Decimal("10.0"),
```

**Verification Command 3:** `grep_search` for `relative_volume` in `warrior_sim_routes.py`  
**Actual Output:**
```
warrior_sim_routes.py:651:  relative_volume=Decimal("10.0"),
warrior_sim_routes.py:800:  relative_volume=Decimal("10.0"),
```

**Code Evidence:** [sim_context.py:278-283](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L278-L283):
```python
candidate = WarriorCandidate(
    symbol=symbol,
    name=symbol,
    price=Decimal(str(entry_price)),
    gap_percent=Decimal(str(gap_pct)),
    relative_volume=Decimal("10.0"),  # ← HARDCODED TO 10.0
```

**Additional evidence:** `WarriorCandidate.relative_volume` is a **required** `Decimal` field (line 262 of `warrior_scanner_service.py`), NOT optional. The `getattr` at line 294 of `warrior_entry_guards.py` is a safety fallback that would never fire since the attribute always exists and is always `Decimal("10.0")`.

**Result:** **FAIL**  
The report's table showing "Sim routes → ❌ No — never touches `relative_volume`" is factually wrong. `load_case_into_context()` explicitly creates the `WarriorCandidate` with `relative_volume=Decimal("10.0")`.

---

### Claim 2: "The code bypasses the MACD defensive gate when RVOL < 5x"

**Claim:** Since RVOL defaults to 0 in sim, the `if rvol < 5.0` at line 295 is always True, causing the MACD gate to be bypassed for every test case.

**Code Evidence:** [warrior_entry_guards.py:294-309](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_guards.py#L294-L309):
```python
rvol = float(getattr(watched.candidate, 'relative_volume', 0) or 0)
if rvol < 5.0:
    logger.info(...)  # BYPASSES the gate!
elif histogram < tolerance and snapshot.macd_crossover != "bullish":
    return False, reason
```

**Analysis:**
- With `relative_volume=Decimal("10.0")`: `rvol = float(Decimal("10.0"))` = `10.0`
- `10.0 < 5.0` → **False**
- Code falls through to `elif` → MACD gate runs **normally**

**Result:** **FAIL**  
The code structure IS capable of bypassing the MACD gate (if RVOL were < 5x), but in sim it **never triggers** because RVOL is always 10.0. The MACD gate runs for every sim test case.

---

### Claim 3: "Both BNRG and NPT regressions are from the RVOL bypass, not falling knife extension"

**Claim:** The RVOL prerequisite change (#2) is catastrophic while the falling knife extension (#1) is fine.

**Analysis:** Since the RVOL bypass never fires in sim (Claim 2 = FAIL), the BNRG (-$10,065) and NPT (-$5,614) regressions **cannot** be caused by the RVOL bypass. The root cause must be elsewhere — possibly the falling knife extension, or another concurrent change.

**Result:** **FAIL**  
Root cause attribution is wrong. The RVOL bypass is not the culprit because it never executes in sim. Further investigation is needed to find the true root cause.

---

### Claim 4: "Ross's rule is that MACD is a hard gate regardless of volume. The 5x prerequisite is for MACD entry signals, not the defensive blocker."

**Verification:** Read warrior.md §8.1 (lines 313-338).

**Evidence from warrior.md:**

Line 320:
> **"Red light, green light"** — MACD negative = DO NOT TRADE

Line 322:
> Requires **5x RVOL** as a prerequisite for MACD signals to be meaningful

Line 333:
> **Summary:** MACD is a **hard binary gate** for entries (negative = don't trade), a **crossover signal** for re-entries (neg→pos = valid entry), and a **defensive warning** against entering weak setups.

**Analysis:**
- Line 320 states the defensive rule: MACD negative = don't trade. **No RVOL exception.**
- Line 322 says 5x RVOL is a prerequisite for "MACD *signals* to be meaningful" — this refers to MACD **crossover entry signals** (line 323: "Entry: Wait for first pullback when MACD is positive"), not the defensive gate.
- Line 333 explicitly says MACD is a "hard binary gate" — no conditions.

The planner's interpretation is correct: these are two separate rules:
1. **Defensive gate** (unconditional): MACD negative = DO NOT TRADE
2. **Entry signal prerequisite**: Only trust MACD crossover signals when RVOL ≥ 5x

**Result:** **PASS**  
The methodology interpretation is well-supported by warrior.md. The two rules serve different purposes.

---

### Claim 5: "Fix: Remove the RVOL bypass block (lines 291-301)"

**Claim:** Delete the RVOL bypass block so the MACD gate always runs.

**Analysis:**
- The code at lines 291-301 IS architecturally wrong per the strategy (Claim 4 confirms this)
- The RVOL prerequisite should NOT bypass the defensive gate
- **However**, removing this code will have **zero effect on sim/batch test results** because the bypass never triggers (RVOL=10.0 ≥ 5.0)
- The fix is correct from a methodology standpoint but will NOT address the BNRG/NPT regressions
- This fix protects against future live-mode bugs if a stock has RVOL < 5x

**Result:** **PARTIAL PASS**  
Removing the bypass is the right code cleanup, but it will not fix the regressions. The true root cause of BNRG/NPT regressions remains unidentified.

---

## Key Finding: True Root Cause Unknown

The research report builds its entire analysis on the premise that `relative_volume=0` in sim causes the MACD gate bypass to fire. This premise is false. The true cause of the BNRG and NPT regressions must be investigated separately.

**Possible actual causes (not verified — for next investigation):**
1. The falling knife extension (change #1) may be the culprit after all
2. Another concurrent code change
3. Non-determinism in test execution (timing, concurrency)

---

## Quality Rating: **LOW** — Requires Rework

The root cause analysis is fundamentally flawed. While the methodology interpretation (Claim 4) is correct and the code cleanup recommendation (Claim 5) is valid, the core regression explanation is wrong.
