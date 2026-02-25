# Handoff: Transcript Re-Processing (Phase 1: Jan 1-15, Phase 2: December)

**Agent:** MockMarket Specialist  
**Priority:** P1 — Data Integrity  
**Date:** 2026-02-24  

---

## Problem

The early transcript processing agent hallucinated trading rules that Ross never stated. **Clay spot-checked several December 2025 transcripts** against the actual YouTube videos and confirmed MACD references were fabricated — Ross didn't mention MACD, but the agent added it to entry/exit criteria anyway.

### Scope
- **Phase 1 (this task):** Jan 1-15, 2026 (16 transcripts) — safe to re-process since test cases start in Jan second half
- **Phase 2 (follow-up):** All December 2025 transcripts — confirmed hallucination zone per Clay's spot-check

### Confirmed Hallucinations (December — Clay Verified)

### Verified Example: AHMA (2025-12-01)
- **Agent claimed** (line 82): `"Only add when MACD is positive"` 
- **Agent claimed** (line 87): `"Exit when MACD crosses negative"`
- **Actual transcript**: Truncated at `[Full transcript continues - abbreviated for space]`
- **Video spot-check**: Clay watched the video — Ross did NOT mention MACD

### Counter-Example: MNTS (2026-01-05)  
- This transcript was processed properly with full text
- Ross discusses Level 2, VWAP support, price action — no MACD mention
- Agent correctly did NOT fabricate MACD rules

### Impact
The `warrior.md` strategy file was built from these transcripts. If MACD references were hallucinated across multiple transcripts, then the MACD guard in the Warrior bot may be based on fabricated methodology. This undermines all MACD-related logic.

---

## Task

Re-process all trade recap transcripts from **January 1-15, 2026** with strict methodology fidelity.

### Target Files (16 transcripts)

```
.agent/knowledge/warrior_trading/2026-01-01_transcript_Lin4WAwzPNY.md
.agent/knowledge/warrior_trading/2026-01-02_transcript_dSiAML8v7Ng.md
.agent/knowledge/warrior_trading/2026-01-03_transcript_oaHTe5lotSQ.md
.agent/knowledge/warrior_trading/2026-01-05_transcript_2T3cZs-LSeY.md
.agent/knowledge/warrior_trading/2026-01-05_transcript_E0u1KKDsQ5Q.md
.agent/knowledge/warrior_trading/2026-01-05_transcript__2Wplp-aNr4.md
.agent/knowledge/warrior_trading/2026-01-06_transcript_pKHzgYSBCEc.md
.agent/knowledge/warrior_trading/2026-01-06_transcript_tDb0WPsRZT4.md
.agent/knowledge/warrior_trading/2026-01-07_transcript_cgIghGaQtY4.md
.agent/knowledge/warrior_trading/2026-01-08_transcript_eYwFYoL6kDE.md
.agent/knowledge/warrior_trading/2026-01-08_transcript_vKjnG1YKXfY.md
.agent/knowledge/warrior_trading/2026-01-09_transcript_BUJQPzYCtJ0.md
.agent/knowledge/warrior_trading/2026-01-12_transcript_EbsPz8WfNAY.md
.agent/knowledge/warrior_trading/2026-01-14_transcript_cXp-i4wM4eQ.md
.agent/knowledge/warrior_trading/2026-01-14_transcript_lneGXw0sxzo.md
.agent/knowledge/warrior_trading/2026-01-15_transcript_0kC1DPUycE0.md
```

---

## Mandatory Rules

> [!CAUTION]
> These rules exist because the previous agent VIOLATED them. Follow without exception.

### 1. ONLY extract what Ross explicitly says
- If Ross says "MACD" → include it with the exact quote
- If Ross does NOT say "MACD" → do NOT add MACD to entry/exit criteria
- If Ross mentions a concept but you're unsure of his exact wording → mark as `[INFERRED — not a direct quote]`

### 2. Full transcript required
- Do NOT truncate with `[Full transcript continues - abbreviated for space]`
- Include the complete text in the `<details>` section
- If the YouTube transcript is unavailable, state `[TRANSCRIPT UNAVAILABLE — video must be manually reviewed]`

### 3. Separate facts from inference
For every extracted rule, label it:
- **`[DIRECT QUOTE]`** — Ross said these exact words
- **`[PARAPHRASED]`** — Ross expressed this idea in different words (include approximate quote)
- **`[INFERRED]`** — Agent's interpretation (must be flagged clearly)
- **`[NOT MENTIONED]`** — Ross did not discuss this topic in this video

### 4. Mandatory checklist per transcript
For each trade recap, explicitly answer:

| Topic | Ross Mentioned? | Quote (if yes) |
|-------|----------------|----------------|
| MACD | YES/NO | [exact quote] |
| VWAP | YES/NO | [exact quote] |
| Level 2 / Order Book | YES/NO | [exact quote] |
| Stop method | YES/NO | [exact quote] |
| Re-entry criteria | YES/NO | [exact quote] |
| Position sizing logic | YES/NO | [exact quote] |
| Exit strategy | YES/NO | [exact quote] |
| Market temperature | YES/NO | [exact quote] |

### 5. Skip non-trade-recap videos
If a video is lifestyle content, Q&A, or educational (not a trade recap), mark it as:
```
**Type:** NON-TRADE-RECAP — [brief description]
```
Do NOT fabricate trade data for non-recap videos.

---

## Output Location

Overwrite the existing files in place:
```
.agent/knowledge/warrior_trading/2026-01-XX_transcript_XXXXX.md
```

---

## Verification

After MockMarket Agent #1 completes, spawn MockMarket Agent #2 with:
```
Task: Verify transcript re-processing quality
For each re-processed transcript:
1. Check that all [DIRECT QUOTE] entries appear in the full transcript text
2. Check that no trading rules were added without [DIRECT QUOTE] or [PARAPHRASED] labels
3. Flag any entry/exit criteria that appear fabricated
4. Produce a validation report at nexus2/reports/2026-02-24/validation_transcript_reprocessing.md
```

---

## Why This Matters

The entire Warrior bot's trading logic is derived from these transcripts via `warrior.md`. If the transcripts contain hallucinated rules, the bot is trading on fabricated methodology. This re-processing is foundational to fixing the $271K P&L gap.
