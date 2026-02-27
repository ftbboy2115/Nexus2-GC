# Research Report: NDRA Catalyst Detection Gap (2026-02-26)

> **Date:** 2026-02-27  
> **Agent:** Backend Planner  
> **Type:** READ-ONLY investigation — no code changes  
> **Status:** Complete

---

## Executive Summary

**Root cause: Classification Gap (both regex AND AI)**

NDRA headlines WERE fetched (4 sources queried: FMP, Alpaca/Benzinga, Yahoo, Finviz), but ALL 7 headlines were classified as FAIL by *both* the regex classifier and the Gemini Flash-Lite AI model. This is a dual classification gap, not a source gap.

---

## Q1: What Headlines Were Available for NDRA on Feb 26?

**Finding:** 7 headlines were fetched and evaluated. All are visible in the `catalyst_audits` table.

**Verified with:** `ssh root@100.113.178.7 "curl -s 'http://localhost:8000/data/catalyst-audits?symbol=NDRA&limit=50&date_from=2026-02-26&date_to=2026-02-26'"`

| # | Headline | Confidence | Method |
|---|----------|-----------|---------|
| 1 | "Endra Life Sciences commences staking of HYPE digital asset holdings" | consensus | Both regex & Flash agreed: FAIL |
| 2 | "ENDRA Life Sciences Recaps Major Milestones and New Strategic Initiatives, Announces Third Quarter 2025 Financial Results" | consensus | Both regex & Flash agreed: FAIL |
| 3 | "ENDRA Feasibility Study Demonstrates TAEUS Accurately Quantifies Liver Fat Fraction, a Key MASLD/MASH Biomarker" | tiebreaker | Regex & Flash disagreed; Pro broke tie: FAIL |
| 4 | "ENDRA's TAEUS Liver Matches MRI-PDFF Performance at Key Clinical Thresholds, Positioning Device for MASLD/MASH Trial Use" | tiebreaker | Regex & Flash disagreed; Pro broke tie: FAIL |
| 5 | "ENDRAs TAEUS Liver Device Demonstrates High-Level Consistency in Clinical Study, Delivering MRI-Level Results at the Point of Patient Care" | tiebreaker | Regex & Flash disagreed; Pro broke tie: FAIL |
| 6 | "ENDRA Life Sciences Announces Results From Study Evaluating TAEUS Live Device" | tiebreaker | Regex & Flash disagreed; Pro broke tie: FAIL |
| 7 | "ENDRA's TAEUS® Liver Device Demonstrates High-Level Consistency in Clinical Study..." (with BusinessWire URL) | tiebreaker | Regex & Flash disagreed; Pro broke tie: FAIL |

**Key observation:** Headlines #3–7 all went to `tiebreaker` — meaning regex and Flash-Lite **disagreed**. In all 5 cases, Flash-Lite likely classified them as PASS (clinical study results), but regex said FAIL. The Pro model (tiebreaker) sided with FAIL in all cases.

---

## Q2: Did the Catalyst Classifier Actually Run?

**Finding:** YES — the full pipeline ran for NDRA. Evidence:  

- 7 `catalyst_audits` records exist (see table above)
- 12 `warrior_scan_results` records exist, all with `reason=no_catalyst`, `catalyst=none`

**Verified with:** `ssh root@100.113.178.7 "curl -s 'http://localhost:8000/data/warrior-scan-history?symbol=NDRA&limit=20&date_from=2026-02-26&date_to=2026-02-26' | python3 -m json.tool"`

Scan results show NDRA was evaluated 12 times between 14:40 and 15:08 UTC (9:40–10:08 AM ET):
- Gap ranged from 26.5% to 53.0%
- RVOL ranged from 67x to 1303x
- Float: 681.8K (sub-1M — ideal)
- **All other pillars PASSED** — only catalyst failed

---

## Q3: Source Gap vs. Classification Gap — Root Cause Analysis

### Answer: **Classification Gap (both tiers)**

The pipeline has TWO classification tiers, and BOTH failed for NDRA's legitimate headlines:

### Tier 1: Regex Classifier

**File:** [catalyst_classifier.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/catalyst_classifier.py#L112-L189)

Tested each NDRA headline against the regex positive patterns:

| Headline | Closest Regex Pattern | Why It Missed |
|----------|-----------------------|---------------|
| "commences **staking** of HYPE **digital asset** holdings" | None | **No crypto/blockchain/digital asset pattern exists** in either positive or tier2 patterns |
| "Recaps **Major Milestones**... **Third Quarter 2025 Financial Results**" | `earnings`: `\b(earnings\|q[1-4]\s+results\|eps\|revenue...)` | ⚠️ This SHOULD have matched! "Third Quarter 2025 Financial Results" contains "results" but not in the specific form `q[1-4]\s+results`. The headline says "Third Quarter" instead of "Q3". |
| "Feasibility Study Demonstrates TAEUS **Accurately Quantifies**..." | `clinical_advance`: `phase\s+[1-3]\s+(study\|trial)` | **No "phase" keyword.** Regex requires `phase X study` or `first patient dosed`; a feasibility study demonstrating clinical results doesn't match. |
| "TAEUS Liver Matches **MRI-PDFF Performance** at Key **Clinical Thresholds**" | `clinical_advance` or `fda` | No "FDA", no "phase X", no "clinical trial results". Device performance data doesn't match any pattern. |
| "Demonstrates **High-Level Consistency in Clinical Study**" | `clinical_advance`: needs `phase\s+[1-3]` prefix | The word "Clinical Study" alone is not enough — regex requires specific phase/trial language. |
| "Announces **Results** From Study Evaluating TAEUS" | `clinical_advance` or `earnings` | "Results From Study" is too generic; `fda` pattern requires "clinical trial results" or "positive results". Earnings pattern requires `q[1-4]\s+results`. |

### Tier 2: AI Multi-Model Validator

**File:** [ai_catalyst_validator.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/ai_catalyst_validator.py#L848-L957)

For the 5 headlines that went to tiebreaker:
- **Regex** said FAIL (no pattern match)
- **Flash-Lite** likely said PASS (clinical device results ARE news)
- **Pro** (tiebreaker) said FAIL — sided with regex's conservative interpretation

For the 2 headlines that got consensus FAIL:
- Both regex and Flash-Lite agreed these weren't valid catalysts:
  - "staking of HYPE digital asset" — crypto staking is genuinely ambiguous
  - "Recaps Major Milestones... Q3 2025 Financial Results" — the earnings pattern missed it, and Flash-Lite possibly saw this as a recap (stale) rather than fresh news

### Three Specific Gaps Identified

1. **Missing crypto/blockchain pattern category** — No regex pattern matches "staking", "digital asset", "blockchain", "cryptocurrency treasury", or "crypto holdings". Ross explicitly mentions "crypto treasury" as a valid catalyst type in the strategy file (line 18: `"Specific catalysts valued: partnerships, FDA data, prediction markets, crypto treasury"`)

2. **Earnings regex too narrow for spelled-out quarters** — The pattern `q[1-4]\s+results` only matches "Q3 results", not "Third Quarter 2025 Financial Results". This exact missed-format has likely affected other stocks.

3. **Clinical study/device data not recognized** — The `clinical_advance` pattern requires specific language like "Phase 3 Study" or "first patient dosed". A medical device data publication (e.g., feasibility study results, MRI-level accuracy) has no matching pattern. This is a gap for healthcare/medtech stocks. The `fda` pattern only matches "clinical trial results" with the word "results" preceded by "clinical trial" — but NDRA's headlines say "Clinical Study" not "Clinical Trial".

---

## Q4: Is This Systemic or a One-Off?

### Assessment: **Partially systemic (gaps #1 and #3 likely affect other stocks)**

**Gap #1 (Crypto/blockchain):** Ross explicitly calls out "crypto treasury" as a catalyst in `.agent/strategies/warrior.md:18`. Any stock moving on crypto-related news (e.g., Bitcoin treasury, staking programs, DeFi adoption) would be missed by the regex tier. This is a KNOWN gap based on the strategy document.

**Gap #2 (Spelled-out quarters):** Headlines commonly use both "Q3 2025" and "Third Quarter 2025" formats. The regex only catches the abbreviated form. This likely causes intermittent false negatives for earnings-driven stocks.

**Gap #3 (Clinical study/device data):** Healthcare stocks frequently move on clinical study data publications that don't explicitly use FDA language. The `clinical_advance` pattern is too narrow — it was designed for drug development milestones (Phase 1/2/3), not for medical device clinical data.

> [!NOTE]
> Interestingly, the tiebreaker results suggest Flash-Lite understood the clinical headlines were valid catalysts (it likely voted PASS, forcing a tiebreaker). The Pro model was more conservative. This means the AI *can* recognize these catalysts — but the current consensus logic gives Pro the deciding vote when regex and Flash disagree.

---

## Recommendations

### Fix 1: Add Crypto/Blockchain Pattern (High priority)

Add a new positive pattern category `crypto_catalyst` to the regex classifier:
```
Pattern: \b(crypto|bitcoin|btc|blockchain|digital\s+asset|staking|defi|token\s+holdings?|crypto\s+treasury)\b
Category: crypto_catalyst
Confidence: 0.9 (Tier 1)
```
**Justification:** Ross explicitly lists "crypto treasury" as a valued catalyst.

### Fix 2: Expand Earnings Pattern (Medium priority)

Extend the `earnings` regex to match spelled-out quarter names:
```
Add: (first|second|third|fourth)\s+quarter\s+\d{4}\s+(financial\s+)?results?
```

### Fix 3: Broaden Clinical/Device Data Pattern (Medium priority)

Expand `clinical_advance` or create a new `clinical_data` pattern:
```
Pattern: \b(clinical\s+study|feasibility\s+study|clinical\s+data|demonstrated?\s+\w+\s+in\s+clinical|device\s+demonstrates?|mri[- ]level|biomarker|clinical\s+thresholds?)\b
Category: clinical_data
Confidence: 0.9 (Tier 1)
```

### Fix 4: Reconsider Tiebreaker Logic (Low priority, investigate)

In 5 of 7 NDRA headlines, the tiebreaker voted FAIL when Flash-Lite likely voted PASS. If Flash-Lite recognizes a clinical study result as valid news but Pro doesn't, the tiebreaker logic currently gives Pro the final say. Consider:
- Logging which model voted PASS/FAIL in the catalyst_audits table (currently only the final result is stored)
- Evaluating whether Pro is being too conservative for clinical/biotech news

---

## Evidence Summary

| Data | Source | Command |
|------|--------|---------|
| Catalyst audits (7 records) | VPS telemetry.db | `curl -s 'http://localhost:8000/data/catalyst-audits?symbol=NDRA&...'` |
| Scan results (12 records) | VPS telemetry.db | `curl -s 'http://localhost:8000/data/warrior-scan-history?symbol=NDRA&...'` |
| Regex patterns | [catalyst_classifier.py:112-189](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/catalyst_classifier.py#L112-L189) | `view_file` |
| Multi-model validator | [ai_catalyst_validator.py:848-957](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/domain/automation/ai_catalyst_validator.py#L848-L957) | `view_code_item` |
| Headline sources | [unified.py:860-932](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/nexus2/adapters/market_data/unified.py#L860-L932) | `view_code_item` |
| Strategy definition | [warrior.md:18](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20%28sync%27d%29/Development/Nexus/.agent/strategies/warrior.md#L18) | Pillar 4 catalyst types |
