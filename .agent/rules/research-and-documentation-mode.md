---
trigger: always_on
---

## Research & Documentation Mode

When in this mode, focus on **research and documentation only**. This mode exists to prevent hallucination, drift, and invented trading rules.

> [!CAUTION]
> In this mode, you DO NOT:
> - Implement logic or write code
> - Propose algorithms or pseudo-code
> - Infer rules from memory or fill gaps with assumptions

Your sole responsibility is to: Research → Verify → Document → Present for approval.

### Research Rules
- Use the trader's actual terminology (e.g., "Episodic Pivot", not "Entry Point")
- Distinguish: canonical rules, inferred principles, and non-rules
- Avoid numeric thresholds unless the trader explicitly states them
- Reference the relevant strategy file in `.agent/strategies/` as ground truth

### Documentation Rules
- Separate: verified facts, observed patterns, system-level constraints, open questions
- Include: definitions, criteria, examples, non-examples, edge cases, failure modes
- Avoid: over-formalization, invented thresholds, non-documented indicators

### Process
1. Restate the research question.
2. Conduct research, extract verified information.
3. Produce a structured document with facts, principles, ambiguities, and open questions.
4. Request approval before any implementation begins.

Goal: Ensure all trading-related logic is grounded in verified research and explicit human approval.