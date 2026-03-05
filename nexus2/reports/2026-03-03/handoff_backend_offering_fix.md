# Backend Specialist Handoff: Fix Offering False-Positive (3 Bugs)

**Date:** 2026-03-03 15:39 ET  
**From:** Coordinator  
**To:** Backend Specialist  
**Research:** `nexus2/reports/2026-03-03/research_offering_false_positive.md`  
**Output:** `nexus2/reports/2026-03-03/backend_status_offering_fix.md`

---

## Context

NPT 2026-03-03 was rejected by the scanner with `negative_catalyst:offering`. Ross made +$8,312 on it. Three compounding bugs caused this.

---

## Bug 1: Finviz Headlines Have No Date Filtering (P0)

**File:** Find `get_finviz_headlines()` in the FMP/market data adapter layer.

**Problem:** The Finviz headline scraper returns headlines from any date. The `catalyst_lookback_days` setting is NOT applied. Months-old headlines (NPT's IPO from late 2025) are included.

**Fix:** Apply `catalyst_lookback_days` filtering to Finviz headlines. Only return headlines from the last N days. The planner's report has details on where the Date column is available but ignored.

---

## Bug 2: "Initial Public Offering" Hits Negative Regex (P0)

**File:** `nexus2/domain/automation/catalyst_classifier.py` lines 178-181, 232-240

**Problem:** The `offering` regex at line 179-181 matches the word "offering" in "Announces Closing of $9.5 Million **Initial Public Offering**". The negative patterns are checked FIRST (line 233), so this matches before the positive `ipo` pattern (line 137) gets checked.

**Fix (choose one, recommend A):**

**A) Add exclusion to negative offering pattern:**
```python
"offering": re.compile(
    r"(?!.*\binitial\s+public\b)\b(offerings?|public\s+offering|registered\s+direct|at-the-market|atm\s+offering|dilution)\b",
    re.IGNORECASE,
),
```

**B) Check positive patterns first, skip negative if positive matched:**
In `classify()`, reorder to check positive before negative. If a headline matches a positive pattern, return immediately without checking negatives.

> [!WARNING]  
> Option B changes the overall classifier behavior for ALL headlines. Option A is more surgical — only excludes "initial public offering" from the negative offering pattern.

---

## Bug 3: Negative Catalyst Bypasses AI Tiebreaker (P1)

**File:** `nexus2/domain/scanner/warrior_scanner_service.py` lines 1380-1430

**Problem:** When `has_negative_catalyst()` returns True, the function returns `"negative_catalyst"` at line 1430, exiting before `_run_multi_model_catalyst_validation()` (line 1443+) ever runs. The AI tiebreaker was designed to catch regex mistakes — but it only covers positive disputes, not negative false-positives.

**Fix:** Before returning `"negative_catalyst"`, check if the AI disagrees:

```python
# After has_negative_catalyst returns True (line 1381):
if has_negative:
    # NEW: Check if AI thinks this is actually positive (tiebreaker)
    if s.enable_multi_model_comparison and headlines:
        # Run AI on the specific negative headline to get a second opinion
        # If AI says it's positive (e.g., IPO), override the regex negative
        # ... implementation details up to specialist
    
    # existing bypass logic continues...
```

**Scope note:** This is a structural improvement. If the specialist judges this too complex for this PR, fix bugs 1+2 first (they solve the immediate NPT problem) and flag bug 3 as a follow-up.

---

## Verification

### Automated
```powershell
# Run existing scanner tests
python -m pytest nexus2/tests/unit/scanners/test_warrior_scanner.py -v

# Run batch test to confirm no regression
python scripts/gc_quick_test.py --all --diff
```

### Manual
```powershell
# Verify NPT is no longer rejected
python scripts/scanner_pulse_check.py NPT 2026-03-03
```
Expected: NPT should either PASS or fail for a different reason (e.g., no positive catalyst found), NOT `negative_catalyst:offering`.

---

## CLI Reference (verified)
```
scanner_pulse_check.py <symbol> <date>    # positional args
gc_quick_test.py [cases...] --all --diff  # positional case names, no --case flag
```
