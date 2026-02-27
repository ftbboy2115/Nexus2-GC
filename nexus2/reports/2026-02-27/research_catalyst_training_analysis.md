# Catalyst Classifier Training Analysis

> **Date:** 2026-02-27  
> **Type:** READ-ONLY research — Backend Planner  
> **Data source:** VPS `ai_comparisons` table via `GET /data/ai-comparisons`  
> **Records analyzed:** 1,110 (all-time)

---

## 1. Volume Stats

| Metric | Count | % |
|--------|------:|--:|
| Total records | 1,110 | 100% |
| **Winner: consensus** | 811 | 73.1% |
| **Winner: pro** (tiebreaker called) | 286 | 25.8% |
| **Winner: flash_only** | 13 | 1.2% |

**Pipeline flow:** Regex + Flash-Lite run in parallel → if they agree = consensus → if they disagree = Pro tiebreaker.

| Final Result | Count | % |
|-------------|------:|--:|
| FAIL | 990 | 89.2% |
| PASS | 120 | 10.8% |

| Flash Result | Count | % |
|-------------|------:|--:|
| FAIL | 844 | 76.0% |
| PASS | 266 | 24.0% |

> [!NOTE]
> Flash passes 266 headlines (24%) but only 120 (10.8%) make it through Pro tiebreaker,
> meaning Pro overrules Flash in ~55% of disagreements by FAILing what Flash passed.

---

## 2. Disagreement Summary

| Category | Count | % of Total |
|----------|------:|----------:|
| Both PASS (agreement) | 117 | 10.5% |
| Both FAIL (agreement) | 840 | 75.7% |
| **Regex PASS + AI FAIL** | **150** | **13.5%** |
| **Regex FAIL + AI PASS** | **3** | **0.3%** |
| **Total disagreements** | **153** | **13.8%** |

> [!IMPORTANT]
> The disagreement is overwhelmingly one-directional: regex finds catalysts that AI rejects
> (150 cases) vs AI finding catalysts regex missed (only 3 cases).
> This suggests **AI is systematically more conservative than regex.**

---

## 3. Regex PASS + AI FAIL — Detailed Breakdown (150 cases)

### By Regex Type

| Regex Category | Cases | % of Disagreements |
|---------------|------:|-------------------:|
| **earnings** | **133** | **88.7%** |
| contract | 7 | 4.7% |
| acquisition | 6 | 4.0% |
| ipo | 3 | 2.0% |
| clinical_advance | 1 | 0.7% |

> [!CAUTION]
> **Earnings dominates the disagreement space.** 133 of 150 regex-passed/AI-failed cases
> are earnings-related. This is the #1 training priority.

---

### 3a. EARNINGS Disagreements (133 cases) — Assessment

After manual review, these fall into **3 sub-categories**:

#### Sub-category A: AI is WRONG — clearly about the symbol's earnings (~85 cases)

These are headlines where the symbol IS the subject of an earnings event, and AI incorrectly rejected:

| Symbol | Headline (sample) | Flash | Pro | Assessment |
|--------|-------------------|-------|-----|------------|
| BWIN | Q4 2025 Earnings Call Transcript | FAIL | FAIL | **AI wrong** — clearly BWIN's earnings |
| BWIN | Q4 Earnings Snapshot | FAIL | FAIL | **AI wrong** |
| PRAA | PRA Group Reports Q4 and Full Year 2025 Results | FAIL | FAIL | **AI wrong** |
| ACHC | Acadia Healthcare Q4 Earnings Call Highlights | FAIL | FAIL | **AI wrong** |
| TNDM | Tandem Diabetes Care Q4 Results | FAIL | FAIL | **AI wrong** |
| JAKK | Jakks Pacific Q4 Earnings Call Highlights | FAIL | FAIL | **AI wrong** |
| MYGN | Myriad Genetics Q4 Earnings Snapshot | FAIL | FAIL | **AI wrong** |
| VIR | Vir Biotechnology Q4 Earnings Call | FAIL | FAIL | **AI wrong** |
| TZOO | Travelzoo Reports Break-Even Q4 | FAIL | FAIL | **AI wrong** |
| CLIK | Reports Strong Revenue Growth for FY 2025 | FAIL | FAIL | **AI wrong** |
| PLBY | Reports Preliminary Fourth Quarter Results | FAIL | FAIL | **AI wrong** |
| AZ | Reports Q4 Preliminary Revenues $4.6M-$5.2M | FAIL | FAIL | **AI wrong** |
| RRGB | Red Robin Q4 Earnings Call | FAIL | FAIL | **AI wrong** |
| DNUT | Krispy Kreme Q4 Earnings Snapshot | FAIL | FAIL | **AI wrong** |
| RXT | Rackspace Technology Q4 Results | FAIL | FAIL | **AI wrong** |
| IBTA | Ibotta Q4 Earnings Assessment | FAIL | FAIL | **AI wrong** |

**Pattern:** Both Flash-Lite AND Pro are rejecting straightforward "[Company] Q4 Earnings" headlines.
This is a **systematic AI deficiency** — the AI models appear unable to recognize standard earnings
headlines as catalyst events.

#### Sub-category B: AI is RIGHT — headline is about a DIFFERENT company (~25 cases)

These are market roundup or tangentially related headlines where regex matched "earnings" keyword
but the earnings event is NOT for the queried symbol:

| Symbol | Headline | Assessment |
|--------|----------|------------|
| XWEL | "Nasdaq Gains Over 1%; TJX Posts Upbeat Earnings" | **AI right** — TJX earnings, not XWEL |
| XWEL | "Dow Jumps 200 Points; Lowe's Issues Weak Earnings Outlook" | **AI right** — Lowe's, not XWEL |
| VSME | "Dow Jumps 200 Points; Lowe's Issues Weak Earnings Outlook" | **AI right** — same issue |
| IBTA | "Crude Oil Gains Over 1%; Hormel Foods Posts Upbeat Earnings" | **AI right** — Hormel, not IBTA |
| IMVT | "Recursion Pharmaceuticals to Report Q4 Earnings" | **AI right** — Recursion, not IMVT |
| IMVT | "Arcutis Biotherapeutics to Report Q4 Earnings" | **AI right** — Arcutis, not IMVT |
| RNG | "Nasdaq Gains 1%; PPL Posts In-Line Q4 Earnings" | **AI right** — PPL, not RNG |
| UIS | "Investors Are Dumping Software Stocks and Earnings Wont Stop It" | **AI right** — general market |
| BTM | "Hut 8 Stock Before Q4 Earnings Release" | **AI right** — Hut 8, not BTM |

**Root cause:** Regex cannot distinguish whether the earnings mention applies to the queried symbol
or to a different company in the same headline. **AI correctly handles this distinction.**

> [!IMPORTANT]
> This is a **fundamental regex limitation** — regex has no concept of which entity the
> earnings mention refers to. This cannot be fixed with regex alone. This is the exact
> use case where AI validation adds value.

#### Sub-category C: Ambiguous — "Earnings Scheduled" announcements (~23 cases)

Headlines like "Earnings Scheduled For February 26, 2026" matched regex because they contain
"earnings", but they announce a future date, not actual results:

| Symbol | Headline | Assessment |
|--------|----------|------------|
| BWIN | Earnings Scheduled For February 26, 2026 | **Debatable** — catalyst pending |
| PRAA | Earnings Scheduled For February 26, 2026 | **Debatable** |
| ACHC | Earnings Scheduled For February 25, 2026 | **Debatable** |
| FA | Earnings Scheduled For February 26, 2026 | **Debatable** |
| ASIC | to Announce Fourth Quarter Earnings... | **Debatable** |

**Assessment:** For Ross Cameron scanning (looking for stocks gapping on news), "earnings scheduled"
is NOT a catalyst — the gap comes when earnings are REPORTED, not scheduled. **AI is arguably correct**
to reject these.

---

### 3b. CONTRACT Disagreements (7 cases)

| Symbol | Headline | Assessment |
|--------|----------|------------|
| MRM | MEDIROM Partners with World (Sam Altman) | **Regex correct** — valid partnership |
| DNUT | KRISPY KREME Partners with OREO for Doughnuts | **AI correct** — marketing promo, not a business catalyst |
| HSPT | Definitive Business Combination Agreement with SL Bio | **Regex correct** — SPAC deal is a catalyst |
| GITS | Agreement with ATEEZ for Animated Feature | **Debatable** — entertainment deal |
| CDIO | Partnership with Southdale YMCA | **AI correct** — community partnership, not material |

**Assessment:** 3 of 7 are legitimate — AI is too aggressive rejecting partnership/agreement headlines.
But 2 are clearly not material catalysts, so AI shows better judgment on "quality" of contracts.

### 3c. ACQUISITION Disagreements (6 cases)

| Symbol | Headline | Assessment |
|--------|----------|------------|
| HSPT × 3 | "Horizon Space **Acquisition** II Corp..." | **AI correct** — "Acquisition" is in the company NAME, not an event |
| MB | "Trumps **Takeover** Of Canadian Rare Earths Miners" | **AI correct** — geopolitical story, not an M&A event for MB |
| VRE | "**Activist investor** urges Veris to consider selling" | **Regex correct** — activist involvement IS a catalyst |
| ABVE | "Confirms Release of Audited FY 2025 Results" | **AI correct** — No acquisition here; regex false positive |

**Assessment:** 4 of 6 are regex false positives — AI is correct here.
**Key issue:** Regex matches "Acquisition" in SPAC company names (Horizon Space Acquisition II Corp).

### 3d. IPO Disagreements (3 cases)

| Symbol | Headline | Assessment |
|--------|----------|------------|
| GRAN | "Florida Lender Hires Bankers to Target Going Public in Rare Bank IPO" | **AI correct** — speculative future IPO |
| ROC | "IPO Security - Released for Quotation" | **Regex correct** — actual IPO event |
| ROC | "IPO Opens For Trade At $6.30/Share" | **Regex correct** — actual IPO event |

---

## 4. Regex FAIL + AI PASS (3 cases) — Pattern Opportunities

These are catalysts the AI found that regex missed entirely:

| Symbol | Headline | Flash | Final | Regex Gap |
|--------|----------|-------|-------|-----------|
| IBTA | "Exceeds Q4 CY2025 Expectations, Stock Jumps 26.4%" | PASS | PASS | Missing "exceeds expectations" pattern |
| SONM | "Stockholders Approve Asset Sale to NEXA" | PASS | PASS | Missing "asset sale" / "stockholders approve" pattern |
| SONM | "Rebrands As DNA X, Inc., A Digital Asset Management Company" | PASS | PASS | Missing "rebrands" / corporate restructuring pattern |

### Suggested Regex Additions

1. **Earnings expansion:** Add `exceeds?\s+(expectations?|estimates?|forecasts?)` to `earnings` pattern
2. **Asset sale:** Add `(asset\s+sale|sells?\s+assets?|divests?|divestiture)` to `acquisition` pattern
3. **Corporate restructuring:** Consider new category `corporate_action` for rebrands, name changes

---

## 5. Both PASS — What's Working Well (117 cases)

| Regex Category | Count | % of Both-Pass |
|---------------|------:|---------------:|
| **earnings** | 63 | 53.8% |
| **contract** | 31 | 26.5% |
| **acquisition** | 13 | 11.1% |
| **fda** | 7 | 6.0% |
| significant_value | 2 | 1.7% |
| clinical_advance | 1 | 0.9% |

> [!TIP]
> Earnings and contract patterns are the workhorses — together they account for 80% of
> successful catalyst detections. FDA detection has 100% agreement rate (7/7 passed by both).

---

## 6. AI Blind Spots — Systematic Patterns

### Blind Spot #1: Standard Earnings Headlines (CRITICAL)

**Severity: HIGH**  
**Cases: ~85 of 133 earnings disagreements**

Both Flash-Lite and Pro consistently FAIL on headlines containing:
- `[Company] Q4 Earnings Call Transcript`
- `[Company]: Q4 Earnings Snapshot`
- `[Company] Q4 Earnings Call Highlights`
- `[Company] Reports Q4 Results`
- `Earnings Preview / Assessment / Insights for [Company]`

These are textbook earnings catalysts. The AI models appear to lack training on standard
financial news headline formats.

**Recommendation:** This is the highest-priority AI training improvement. These standard
earnings headline formats should be added to AI prompt examples or fine-tuning data.

### Blind Spot #2: Earnings Metric Headlines

**Severity: MEDIUM**  
**Cases: ~10**

Headlines like:
- "Key Metrics Tell Us About [Company] Q4 Earnings"  
- "[Company] Q4 Earnings: A Look at Key Metrics Versus Estimates"

These contain both the earnings keyword AND detailed financial analysis, yet AI rejects them.

### Not a Blind Spot: Multi-Company Headlines

**Note:** AI correctly handles ~25 cases where regex falsely matched earnings keywords in
market roundup headlines about other companies. This is where AI adds genuine value over regex.

---

## 7. Recommendations

### Priority 1: AI Prompt/Training Improvements (HIGH)

The AI models need to recognize standard earnings headline patterns. Training data should include:
- "[Company] Q4 YYYY Earnings Call Transcript" → PASS (earnings)
- "[Company]: Q4 Earnings Snapshot" → PASS (earnings)
- "[Company] Reports Q4 Results" → PASS (earnings)
- "[Company] Q4 Earnings Call Highlights" → PASS (earnings)
- "Compared to Estimates, [Company] Q4 Earnings" → PASS (earnings)

### Priority 2: New Regex Patterns (LOW — only 3 cases)

| Pattern | Regex to Add | Target |
|---------|-------------|--------|
| Exceeds expectations | `exceeds?\s+(expectations?\|estimates?\|forecasts?)` | `earnings` |
| Asset sale | `(asset\s+sale\|sells?\s+assets?\|divests?\|divestiture)` | `acquisition` |
| Corporate restructuring | `(rebrands?\|name\s+change\|restructur)` | new `corporate_action` |

### Priority 3: Regex False Positive Fixes (MEDIUM — 31 false positives)

| Issue | Count | Fix |
|-------|------:|-----|
| "Acquisition" in SPAC company names | 3 | Exclude matches within company name strings |
| "Earnings" in roundup headlines about other companies | ~25 | **Cannot fix with regex** — AI dependency |
| "Earnings Scheduled" (future date, not results) | ~23 | Consider excluding `scheduled\s+for` pattern |
| Non-material partnerships (YMCA, OREO promos) | 2 | **Cannot fix with regex** — AI dependency |

> [!IMPORTANT]
> ~50 of the 150 "Regex PASS + AI FAIL" cases are actually **correct AI rejections**
> where regex was wrong. The real AI false negative count is approximately **~100 cases**,
> concentrated almost entirely in standard earnings headline formats.

---

## 8. Evidence: Commands Used

All data was gathered via read-only VPS API queries:

```powershell
# Schema discovery
ssh root@100.113.178.7 "curl -s 'http://localhost:8000/data/ai-comparisons?limit=1'"

# Response structure discovery
ssh root@100.113.178.7 "curl -s 'http://localhost:8000/data/ai-comparisons?limit=2' | python3 -c '...'"

# Full data fetch (3 batches due to 500 API limit)
ssh root@100.113.178.7 "curl -s 'http://localhost:8000/data/ai-comparisons?limit=500' > /tmp/ai_comp_1.json; ..."

# Data downloaded via SCP for local analysis
scp root@100.113.178.7:/tmp/ai_comp_{1,2,3}.json C:\tmp\

# Analysis performed locally via Python script
python C:\tmp\query_ai_comparisons.py
```

Raw analysis data saved at `C:\tmp\ai_comparisons_analysis.json`.

---

## 9. Price Outcome Analysis — Did We Miss Opportunities?

> **Data source:** VPS `warrior-scan-history` endpoint + `warrior_setups.yaml`  
> **Verified via:** `ssh root@100.113.178.7 "curl -s 'http://localhost:8000/data/warrior-scan-history?symbol=XXX&limit=5'"`

### 9a. Ross Cameron Trade Overlap

**Result: Zero overlap** between the 45 disagreement symbols and Ross's 47 traded symbols.

Ross's symbols (CMCT, OPTX, LCFY, PAVM, ROLR, HIND, etc.) are **entirely different** from the
stocks where regex and AI disagreed (BWIN, ACHC, DNUT, etc.). This means the AI disagreements
did not cause any missed Ross Cameron trades.

### 9b. Architecture Finding — How Catalyst Decisions Actually Work

> [!CAUTION]
> **Earlier version of this section was incorrect.** It claimed "AI disagreements are just
> training data logs." This was wrong. The actual architecture is more nuanced.

**Verified pipeline flow** (from [warrior_scanner_service.py](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py)):

```
Step 1: _evaluate_catalyst_pillar (L1308-1441)
  → Calendar check first (FMP earnings calendar)
  → Regex classifier runs on headlines
  → If regex match with confidence ≥ 0.6: ctx.has_catalyst = True, catalyst_source = "regex"

Step 2: _run_multi_model_catalyst_validation (L1443-1539)
  → Runs EVEN when regex already set catalyst (always_run_ai_comparison = True, L149)
  → For each headline: validate_sync() → Regex + Flash-Lite → Pro tiebreaker
  → At L1517: if final_valid AND NOT ctx.has_catalyst → sets ctx.has_catalyst = True, source = "ai"
```

**Key behavior:**

| Scenario | Regex | AI (Flash/Pro) | Result | Explanation |
|----------|-------|---------------|--------|-------------|
| Regex PASS + AI PASS | ✅ | ✅ | **PASS** (regex) | Consensus — both agree |
| **Regex PASS + AI FAIL** | ✅ | ❌ | **PASS** (regex) | AI cannot revoke regex — `ctx.has_catalyst` already True at L1364 |
| **Regex FAIL + AI PASS** | ❌ | ✅ | **PASS** (ai) | AI catches what regex missed via L1517 check |
| Regex FAIL + AI FAIL | ❌ | ❌ | **FAIL** | Both agree no catalyst |

> [!IMPORTANT]
> **AI can ADD catalysts but cannot REVOKE them.** When regex passes, the stock passes 
> regardless of AI's verdict. This explains why `catalyst_source: 'regex'` appears in 
> scan history — regex set the catalyst first, and AI's disagreement didn't override it.

**Evidence** — the critical line at [L1517](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/domain/scanner/warrior_scanner_service.py#L1517):
```python
if final_valid and not ctx.has_catalyst:
    ctx.has_catalyst = True
    ctx.catalyst_source = "ai"
```

### Design Documents Reviewed

The pipeline was refactored on **2026-02-20** per these design docs:

| Document | Key Finding |
|----------|------------|
| [spec_catalyst_pipeline_refactor.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-02-20/spec_catalyst_pipeline_refactor.md) | Full technical spec (618 lines). Clay's intent: regex+AI in parallel on ALL headlines for comparison data |
| [backend_status_catalyst_pipeline_refactor.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-02-20/backend_status_catalyst_pipeline_refactor.md) | Implementation status: all 3 changes complete, tests passing |
| [audit_catalyst_pipeline.md](file:///c:/Users/ftbbo/Nextcloud4/OneDrive%20Backup/Documents%20(sync'd)/Development/Nexus/nexus2/reports/2026-02-20/audit_catalyst_pipeline.md) | Pre-refactor audit identifying the data loss problem |

**The original problem** (spec L72): Before the refactor, `not ctx.has_catalyst` at the AI gate
meant that if regex or calendar already set `ctx.has_catalyst = True`, the **entire AI pipeline
was skipped** — no `validate_sync()` call, no `CatalystAudit` rows, no `AIComparison` rows.
Only regex-missed symbols got AI comparison data, defeating the training purpose.

**The fix** (spec L280, backend_status Change 3b): Changed the gate to
`(not ctx.has_catalyst or s.always_run_ai_comparison)` so AI now runs on **all headlines**
regardless of regex/calendar status. This generates comparison data for training.

**The asymmetry was intentional** — the spec explicitly states (Section 3.3 and 5.0):
> _"`catalyst_source` answers 'why did we decide to trade?' — not 'what data did we collect?'"_
> _"Only the first resolution source sets `catalyst_source` for the trade"_

And Change Point #2 (spec L297-298):
> _"Keep the `not ctx.has_catalyst` guard here — this is the trade decision logic. Only set
> `ctx.has_catalyst` if no prior method (calendar/regex) already confirmed."_

### 9c. Scanner Results for Disagreement Stocks

| Symbol | Gap % | Scanner Result | Reason | Score | Catalyst Source |
|--------|------:|---------------|--------|------:|-----------------|
| **ACHC** | +25% | **FAIL** | `etb_high_float` (82.3M) | - | regex (earnings) |
| **BWIN** | +22-54% | **FAIL** | `etb_high_float` (67.4M) | - | regex (earnings) |
| **CCCC** | +17% | **FAIL** | `etb_high_float` (65.7M) | - | regex (clinical_advance) |
| **ANY** | +26% | **PASS** | - | 10 | regex (earnings) |
| **ASIC** | +24% | **PASS** | - | 9 | regex (earnings) |
| **AZ** | +26% | **PASS** | - | 7 | regex (earnings) |
| **BTM** | +6-11% | **PASS** | - | 9-10 | regex (earnings) |
| **CAI** | +19% | **PASS** | - | 8 | regex (earnings) |
| **CDIO** | +21% | **PASS** | - | 9 | regex (contract) |
| **ABVE** | +9% | **PASS** | - | 5 | regex (acquisition) |

**Key observations:**
1. **Stocks with big gaps (9-54%) were all scanned** — regex caught them
2. **Failures were for float/ETB reasons**, not catalyst detection failures
3. **CDIO had 1,245 scan hits** — it was scanned exhaustively despite AI disagreement
4. **The AI FAIL on these stocks' headlines had zero impact on scanning**

### 9d. Implications

**Today's impact on trading:**
- **150 Regex PASS + AI FAIL cases:** No missed trades. Regex set `ctx.has_catalyst` first,
  AI's FAIL verdict doesn't remove it. These stocks passed the catalyst check.
- **3 Regex FAIL + AI PASS cases:** AI **actively caught** catalysts regex missed. These
  stocks (IBTA, SONM) passed the scanner **because of AI**. Without AI, they would have
  been rejected for lacking a catalyst.
- **Stocks that failed the scanner** (ACHC, BWIN, CCCC) failed for `etb_high_float`,
  not catalyst issues. Even if AI had passed their catalysts, they'd still fail.

**Design issue:** The current pipeline is asymmetric:
- AI can rescue a regex miss (PASS when regex FAILs) ✅
- AI **cannot** correct a regex false positive (FAIL when regex PASSes) ❌
- This means regex false positives (~50 cases) flow straight through unchecked

**Stale docstring:** `MultiModelValidator` at L575-576 reads _"Trading decisions still use
regex only"_ — this is incorrect. AI decisions at L1517 directly set `ctx.has_catalyst`.
This docstring should be updated.

**Future consideration:** If improved AI accuracy is desired, the L1517 check could be
changed to also allow AI to revoke regex false positives. But this requires fixing the
earnings blind spot first — otherwise AI would incorrectly reject ~85 valid earnings stocks.
