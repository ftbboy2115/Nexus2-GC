# Handoff: Backend Planner — Catalyst Classifier Training Analysis

> **Date:** 2026-02-27  
> **From:** Coordinator  
> **To:** Backend Planner  
> **Priority:** Low  
> **Type:** READ-ONLY analysis — no code changes

---

## Objective

Analyze the `ai_comparisons` table in telemetry.db to find disagreements between the regex classifier and AI models (Flash-Lite, Pro). Produce a structured training report that identifies:

1. Regex PASS + AI FAIL cases (potential AI false negatives — AI may be too conservative)
2. Regex FAIL + AI PASS cases (potential new regex patterns needed)
3. Common headline patterns in tiebreaker cases

---

## Verified Facts

1. **The `ai_comparisons` table stores regex vs Flash vs Pro results** — verified via `GET /data/ai-comparisons` endpoint
2. **Three winner types exist:** `consensus`, `pro`, `flash_only` — verified via `GET /data/ai-comparisons/distinct?column=winner`
3. **Example false negative found:** BWIN "Q4 2025 Earnings Call Transcript" — regex correctly matched `earnings`, but both Flash and Pro voted FAIL
4. **The endpoint is at** `nexus2/api/routes/data_routes.py` under `/data/ai-comparisons`

---

## Open Questions (YOU must investigate)

### Q1: How many disagreements exist?

Query the VPS to determine:
- Total records in `ai_comparisons`
- Breakdown by winner type (consensus vs pro vs flash_only)
- How many have `regex_result != 'FAIL'` AND `final_result = 'FAIL'` (regex found something, AI rejected)
- How many have `regex_result = 'FAIL'` AND `final_result != 'FAIL'` (regex missed, AI caught)

### Q2: What headline patterns does regex catch but AI rejects?

For all cases where `regex_result` is a valid catalyst type (earnings, fda, contract, etc.) but `final_result = 'FAIL'`:
- Group by `regex_result` type
- List the actual headlines
- Assess whether regex or AI was correct

### Q3: What headline patterns does AI catch but regex misses?

For all cases where `regex_result = 'FAIL'` but `flash_result` or `pro_result` = PASS:
- What types of headlines are these?
- Could new regex patterns be added?
- Are there common keywords?

### Q4: Are there systematic AI blind spots?

Look for patterns where the AI consistently fails on a category that regex handles well (like the BWIN earnings example).

---

## How to Query

Use the VPS API (read-only):

```powershell
# All disagreements (non-consensus)
ssh root@100.113.178.7 "curl -s 'http://localhost:8000/data/ai-comparisons?limit=500&sort_dir=desc' | python3 -m json.tool"

# Filter to tiebreaker cases only
ssh root@100.113.178.7 "curl -s 'http://localhost:8000/data/ai-comparisons?winner=pro&limit=100' | python3 -m json.tool"

# Total count
ssh root@100.113.178.7 "curl -s 'http://localhost:8000/data/ai-comparisons?limit=1' | python3 -c 'import sys,json; d=json.load(sys.stdin); print(f\"Total: {d[\"total\"]}\")'
```

You may also want to read the regex patterns at `nexus2/domain/automation/catalyst_classifier.py:112-189` to understand what the regex classifier looks for.

---

## Key Files

| File | What to look for |
|------|-----------------|
| `nexus2/domain/automation/catalyst_classifier.py:112-189` | Current regex patterns (positive, tier2, negative) |
| `nexus2/domain/automation/ai_catalyst_validator.py:848-957` | `validate_sync()` — how consensus/tiebreaker works |
| `nexus2/api/routes/data_routes.py:622-745` | AI comparisons API endpoint |

---

## Expected Deliverable

A report at `nexus2/reports/2026-02-27/research_catalyst_training_analysis.md` containing:

1. **Volume stats** — total records, disagreement rate, breakdown by winner type
2. **Regex PASS + AI FAIL table** — each case with headline, regex type, and assessment (who was right?)
3. **Regex FAIL + AI PASS table** — potential new pattern opportunities
4. **Pattern recommendations** — specific regex additions suggested by the data
5. **AI blind spots** — categories where the AI is systematically wrong

> [!IMPORTANT]
> This is READ-ONLY research. Do NOT modify any production code.
> Include exact VPS commands and output as evidence for all findings.
