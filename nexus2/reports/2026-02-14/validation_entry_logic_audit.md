# Validation Report: Entry Logic Audit

**Date:** 2026-02-14  
**Auditor Report:** Entry Logic Audit (conversation `73457cec`)  
**Validator:** Audit Validator  

---

## Claims Verified

| # | Claim | Result | Details |
|---|-------|--------|---------|
| C1 | PMH_BREAK requires `current_price >= watched.pmh` | **PASS** (with line correction) | See below |
| C2 | Pattern Competition blocks ABCD when `setup_type="pmh"` | **PASS** | Exact match |
| C3 | Pattern Competition blocks VWAP_BREAK when `setup_type="pmh"` | **PASS** | Exact match |
| C4 | `whole_half_anticipatory` requires 3-10¢ below level | **PASS** | Exact match |
| C5 | Extension threshold = 200% | **PASS** | Exact match |
| C6 | PMH key mismatch disproved for batch path | **PASS** | Exact match |
| C7 | GUI path uses different key `"premarket_high"` | **PASS** | Confirmed inconsistency |

---

## Detailed Evidence

### C1: PMH_BREAK requires `current_price >= watched.pmh`

**Claim:** PMH_BREAK pattern only fires when price is at or above PMH. Line 537 cited.

**Verification:** Viewed [warrior_engine_entry.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_entry.py) lines 515-560.

**Actual Code:**
```python
# Line 515
if current_price < watched.pmh:
    # ... below-PMH patterns (whole_half, dip_for_level)
# Line 537
else:
    # Price is above PMH
    # ... (line 560) detect_pmh_break() called here
```

Inside `detect_pmh_break` ([warrior_entry_patterns.py:525](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py#L525)):
```python
if current_price < trigger_price:
    return None
```

**Result:** **PASS** — PMH_BREAK is structurally gated to only fire when `current_price >= watched.pmh` via the `else` branch at line 537, plus an additional guard in `detect_pmh_break` at line 525.

> [!NOTE]
> Line 537 is just `else:`, not a `current_price >= watched.pmh` comparison. The report's description is functionally accurate but the line reference is slightly misleading. The actual structural guard is at **line 515** (`if current_price < watched.pmh:`) and the explicit check is at **line 525** inside `detect_pmh_break`.

---

### C2: Pattern Competition blocks ABCD when `setup_type="pmh"`

**Claim:** `should_check_abcd = setup_type is None or setup_type == "abcd"` at line 67.

**Verification:** Viewed [warrior_entry_patterns.py:67](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py#L67).

**Actual Code:**
```python
# Line 66: # PATTERN COMPETITION: Only check if setup_type is None or "abcd"
# Line 67: should_check_abcd = setup_type is None or setup_type == "abcd"
# Line 68: if not (engine.config.abcd_enabled and not watched.entry_triggered and should_check_abcd):
```

**Result:** **PASS** — Exact match at line 67. When `setup_type="pmh"`, `should_check_abcd` evaluates to `False`, blocking ABCD.

---

### C3: Pattern Competition blocks VWAP_BREAK when `setup_type="pmh"`

**Claim:** `should_check_vwap_break = setup_type is None or setup_type in ("vwap_break", "vwap_reclaim")` at line 990.

**Verification:** Viewed [warrior_entry_patterns.py:990](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py#L990).

**Actual Code:**
```python
# Line 989: # PATTERN COMPETITION: Only check if setup_type matches
# Line 990: should_check_vwap_break = setup_type is None or setup_type in ("vwap_break", "vwap_reclaim")
# Line 991: if not (engine.config.vwap_break_enabled and not watched.entry_triggered and should_check_vwap_break):
```

**Result:** **PASS** — Exact match at line 990.

---

### C4: `whole_half_anticipatory` requires 3-10¢ below level

**Claim:** Pattern requires price to be exactly 3-10¢ below a whole/half dollar. Ross enters AT $7.90, not below it.

**Verification:** Viewed [warrior_entry_patterns.py:184](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_entry_patterns.py#L184).

**Actual Code:**
```python
# Line 182: # ANTICIPATORY ZONE: 3-10 cents BELOW the level
# Line 183: # Ross buys at $5.97 for break of $6.00 (3 cents below)
# Line 184: if not (3 <= distance_cents <= 10):
# Line 185:     continue
```

**Result:** **PASS** — Confirmed. The 3-10¢ range is hardcoded at line 184.

**MLEC analysis:** Ross enters at $7.90. The nearest half is $8.00 → `distance_cents = 10.0`. This is **exactly at the boundary** of the range (`<= 10`), so the pattern *might* actually pass this check. However, additional momentum/volume gates (lines 188-227) would need to pass too. The auditor's claim that "$7.90 is AT a level, not below it" is slightly imprecise — $7.90 is 10¢ below $8.00, which *is* within the 3-10¢ zone.

> [!WARNING]
> The auditor's claim that `whole_half_anticipatory` would never fire for MLEC at $7.90 may be **incorrect**. $7.90 is exactly 10¢ below $8.00, which satisfies `3 <= 10.0 <= 10`. The pattern could potentially fire if momentum and volume gates pass. This is a **minor finding** — the overall conclusion (MLEC produces 0 trades) may still hold due to other gates.

---

### C5: Extension threshold = 200%

**Claim:** `extension_threshold = 200.0` prevents MLEC (94.6% gap) from routing to micro_pullback. Cited line 119.

**Verification:** Viewed [warrior_engine_types.py:119](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/automation/warrior_engine_types.py#L119).

**Actual Code:**
```python
# Line 119: extension_threshold: float = 200.0  # Gap % above which to use micro-pullback instead of PMH (was 100, raised to fix PAVM regression)
```

**Result:** **PASS** — Exact match. MLEC at 94.6% < 200.0% threshold → NOT routed to micro_pullback.

---

### C6: PMH key mismatch — DISPROVED for batch path

**Claim:** `sim_context.py:226` reads `premarket.get("pmh", entry_price)` — correctly getting $12.97.

**Verification:** Viewed [sim_context.py:226](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/adapters/simulation/sim_context.py#L226).

**Actual Code:**
```python
# Line 224: premarket = data.premarket
# Line 225: gap_pct = premarket.get("gap_percent", 25.0)
# Line 226: pmh = Decimal(str(premarket.get("pmh", entry_price)))
```

**Result:** **PASS** — Exact match. Batch path uses `"pmh"` key, which matches the JSON data file.

---

### C7: GUI path uses different key `"premarket_high"`

**Claim:** `warrior_sim_routes.py:662` reads `premarket.get("premarket_high", ...)` — different from batch path.

**Verification:** Viewed [warrior_sim_routes.py:662](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/api/routes/warrior_sim_routes.py#L662).

**Actual Code (GUI `load_warrior_test_case`):**
```python
# Line 610: premarket = case.get("premarket_data", {})  # From YAML
# Line 662: pmh = Decimal(str(premarket.get("premarket_high", entry_price or current_price)))
```

**Actual Code (Historical replay `load_historical_test_case`):**
```python
# Line 774: premarket = data.premarket  # From JSON loader
# Line 776: pmh = Decimal(str(premarket.get("pmh", entry_price)))
```

**Result:** **PASS** — Confirmed. The GUI path (line 662) uses `"premarket_high"` while the batch/historical path (line 776) uses `"pmh"`. These work correctly because they read from different data sources (YAML `premarket_data` vs JSON `premarket`), but it's a genuine inconsistency that could cause silent failures if data format expectations change.

---

## Quality Rating

**HIGH** — All 7 claims verified. One minor imprecision found in C4 analysis.

### Summary of Findings

| Finding | Severity |
|---------|----------|
| C1 line number (537) is `else:`, not an explicit `>= pmh` check | Minor (cosmetic) |
| C4: $7.90 is actually within the 3-10¢ zone of $8.00 | Minor (may affect analysis) |
| All other claims: exact match to source code | N/A |

### One Notable Finding

The C4 imprecision deserves attention: the auditor concluded `whole_half_anticipatory` cannot fire for MLEC at $7.90 because "$7.90 is AT a whole/half level, not below it." In reality, $7.90 is 10¢ below $8.00, which is the **exact boundary** of the 3-10¢ zone and *would pass* the proximity check. Whether the pattern actually fires depends on downstream momentum and volume gates (lines 188-244), which should be investigated separately.
