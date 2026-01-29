# Hypothesis vs Confirmation Rule

When debugging or analyzing issues, always distinguish between:

## HYPOTHESIS (unverified)
- Based on log symptoms, error messages, or behavioral observations
- Use language like: "This *may* be caused by...", "I *suspect*...", "Potential issue..."
- Do NOT present as fact until verified in code

## CONFIRMED (verified)
- Verified by reading the actual source code
- Reproducible or traceable to a specific line/function
- Use language like: "The bug is at line X...", "I confirmed that..."

## Process
1. When analyzing logs/errors, present findings as **hypotheses**
2. Before writing an implementation plan, **verify each hypothesis** by reading the relevant code
3. Only list items as "bugs" or "issues" after code verification
4. If you haven't verified, say: "I need to verify this in the code before confirming"

## Example

❌ Wrong: "I found 4 bugs causing this issue"  
✅ Right: "Based on the logs, I hypothesize 4 potential causes. Let me verify each in the code."
