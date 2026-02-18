# Diagnosis: Strategy-Sensitive Test Failures

> Generated: 2026-02-18

These 3 failures are NOT infrastructure issues — they reveal real gaps between the scanner's rigid filter logic and Ross Cameron's flexible, discretionary trading approach.

---

## BNRG Scanner Rejection

- **Test file:** `tests/test_scanner_validation.py:233`
- **Test case ID:** `ross_bnrg_20260211`
- **What failed:** `assert candidate is not None` — Scanner returned `None` (rejected)
- **Scanner criteria failed:** Gap pillar — `gap_percent: -7.0%`, minimum required: `4.0%`
- **Ross P&L:** +$271.74

### Root Cause

BNRG had a **negative gap** (-7.0%). The YAML test case documents this as a **VWAP reclaim** setup, not a traditional gap-up:

> "Sub-1M float, recent reverse split, Israeli company. Below VWAP at 6:45 — Ross thought if it reclaims VWAP and breaks $4, could go back to $4.50."

The scanner's `_calculate_gap_pillar` (line 1596) requires `ctx.gap_pct >= s.min_gap` (4.0%). A stock trading **below** its previous close cannot pass this check.

### Is the scanner correct?

**YES, for gap-up detection.** The scanner correctly identifies that BNRG did not gap up. However, Ross traded it as a **VWAP reclaim** — a different setup type that the scanner doesn't currently support.

### Proposed Fix (DO NOT IMPLEMENT)

Two options:
1. **Exclude from `get_ross_traded_winners()`** — VWAP reclaim setups (`setup_type: vwap_reclaim`) should not be validated against the gap-up scanner. Filter test cases to only include `setup_type: pmh` or gap-positive setups.
2. **Add VWAP reclaim scanner** — A separate scanner module for red-to-green / VWAP reclaim setups that don't require a positive gap.

**Recommendation:** Option 1 (filter the test). The scanner is working correctly; the test case is testing the wrong capability.

---

## VHUB Scanner Rejection

- **Test file:** `tests/test_scanner_validation.py:233`
- **Test case ID:** `ross_vhub_20260217`
- **What failed:** `assert candidate is not None` — Scanner returned `None` (rejected)
- **Scanner criteria failed:** Gap pillar — `opening_gap=3.3% live_gap=3.3% min=4.0%`
- **Ross P&L:** +$1,600.00

### Root Cause

VHUB's gap was `3.3%` — just below the scanner's `min_gap` of `4.0%`. The `_calculate_gap_pillar` at line 1596 rejects with `gap_too_low`.

The YAML notes describe this as an **icebreaker trade** on a cold market day:

> "Icebreaker trade. VHUB recent IPO with blue sky above $40. News headline at ~7:30 AM. Popped to $3.45, dipped, curled back up."

Ross entered with 20K shares at $3.33 with a tight 13-cent risk for a quick $1,600 profit.

### Is the scanner correct?

**PARTIALLY.** The 4% minimum gap is a valid Ross methodology rule. However, Ross himself traded VHUB with a 3.3% gap because:
- It had **news catalyst** (headline at 7:30 AM)
- **Blue sky** above $40 (recent IPO, no overhead resistance)
- **Low float** with high squeeze potential
- Cold market day where the best available setup was sub-threshold

This represents Ross's **discretionary override** of his own rules.

### Proposed Fix (DO NOT IMPLEMENT)

Two options:
1. **Lower `min_gap` to 3.0%** — Captures VHUB-type setups but introduces noise.
2. **Add "icebreaker" exemption** — If other pillar scores are exceptionally high (catalyst + blue sky + low float), reduce gap threshold to 3%. This matches Ross's actual behavior of taking sub-threshold setups when quality is high.

**Recommendation:** Option 2, but this requires a design decision from Clay. The gap threshold exists for a reason.

---

## Timezone Compliance

- **Test file:** `tests/test_timezone_compliance.py:73`
- **What failed:** `assert False` — 4 violations detected (3 real, 1 contextual)

### Violations Found

| # | File | Line | Code | Real? |
|---|------|------|------|-------|
| 1 | `scan_diagnostic.py` | 740 | `datetime.now().strftime(...)` | **YES** — diagnostic output |
| 2 | `catalyst_search_service.py` | 53 | `self._cache_loaded_at = datetime.now()` | **YES** — cache timing |
| 3 | `warrior_scanner_service.py` | 513 | `now = datetime.now()` | **YES** — cache TTL check |
| 4 | `warrior_scanner_service.py` | 545 | Comment text matches regex | **FALSE POSITIVE** — line uses `now_utc()` but comment text `datetime.now()` triggers regex |

### Proposed Fix (DO NOT IMPLEMENT)

**Violations 1-3:** Replace `datetime.now()` with `now_et()` from `nexus2.utils.time_utils`:
```python
# scan_diagnostic.py:740
lines.append(f"Generated: {now_et().strftime('%Y-%m-%d %H:%M:%S')}")

# catalyst_search_service.py:53
self._cache_loaded_at = now_et()

# warrior_scanner_service.py:513
now = now_et()
```

**Violation 4 (false positive):** Update the regex or add the line to exclusions. The actual code at line 545 is:
```python
timestamp=now_utc(),  # IMPORTANT: Use now_utc() not datetime.now()
```
The comment text `datetime.now()` triggers the regex pattern `datetime\.now\(\s*\)`.

### Trading Impact

- **Violations 1 (diagnostic) and 2 (cache timing):** **NO** — cosmetic/internal timing only.
- **Violation 3 (scanner cache):** **LOW** — affects cache expiration timing. Using naive `datetime.now()` vs `now_et()` could cause off-by-hours cache TTL during DST transitions, but this is unlikely to affect trading decisions in practice.
- All 3 are safe to fix.

---

## Summary

| Failure | Root Cause | Fix Approach |
|---------|-----------|-------------|
| BNRG | Red-to-green VWAP reclaim ≠ gap-up | Filter test (wrong setup type for gap scanner) |
| VHUB | Gap 3.3% < 4% min (Ross discretionary override) | Design decision: icebreaker exemption logic |
| Timezone | 3 `datetime.now()` in production code | Replace with `now_et()` (safe, no trading impact) |
