# Debugging Methodology: Code Auditing vs. Trace Logging

## Context

During Phase 9-10 of the concurrent batch runner project, we spent 10+ audit conversations analyzing code structure to find a P&L divergence between sequential and concurrent runners. The root cause was ultimately found in a **single deployment cycle** using trace logging.

This document captures when each approach is most effective.

---

## Code Auditing (Static Analysis)

**What it is:** Reading code, analyzing control flow, identifying structural issues without running anything.

**Best for:**
- Identifying **architectural problems** (wrong abstractions, missing boundaries, coupling)
- Finding **dead code**, unused imports, extraction opportunities
- Verifying **contracts** (API shapes, type signatures, schema alignment)
- Catching **obvious bugs** (wrong variable names, missing null checks)
- Understanding **how code is structured** before making changes
- Pre-implementation **design review**

**Weaknesses:**
- Cannot determine **runtime behavior** — what actually executes and in what order
- Cannot distinguish between "could cause a bug" and "does cause a bug"
- Prone to **hypothesis drift** — each auditor builds theories that the next auditor must validate, creating circular analysis
- **Singleton vs instance confusion** — hard to tell which object instance is used at runtime just from reading code

**Case study:** 10+ audit conversations identified multiple *plausible* root causes (wall-clock throttle, shared engine state, DB contamination, callback wiring) but couldn't definitively confirm which one was the *actual* cause.

---

## Trace Logging (Runtime Observation)

**What it is:** Instrumenting code to emit structured events at runtime, then comparing event streams between two execution paths.

**Best for:**
- **Divergence diagnosis** — when two paths should produce identical output but don't
- Identifying **which specific decision point** causes different behavior
- Confirming **actual execution order** and timing
- Validating **state at decision points** (what values guards actually see)
- **Proving** vs. theorizing — trace data is evidence, not hypothesis

**Weaknesses:**
- Requires **knowing where to instrument** (needs some prior understanding of code)
- Can generate **overwhelming data** if too broad
- Must be **cleaned up** after diagnosis (temporary by nature, unless promoted to TML)
- Not useful for **structural problems** (architecture, design, naming)

**Case study:** Trace logging immediately revealed that prices and triggers were identical, MACD and cooldown guards were identical, and the **entire** divergence was 10 position guard blocks in sequential vs. 0 in concurrent. Root cause identified in one deployment.

---

## Decision Framework

```
Is the bug about WHAT CODE EXISTS or WHAT CODE DOES AT RUNTIME?

├─ WHAT CODE EXISTS (structure, contracts, architecture)
│  → Code Audit
│
├─ WHAT CODE DOES (behavior, state, timing, divergence)
│  → Trace Logging
│
└─ UNSURE
   → Start with a focused audit to understand the system
   → If the audit produces multiple competing hypotheses without resolution
   → Switch to trace logging to gather empirical evidence
```

### Escalation Rule

> **If two audit rounds produce competing hypotheses without definitive proof, switch to trace logging.**
>
> Auditing is excellent for narrowing the search space, but trace logging provides the empirical evidence needed to close the investigation.

---

## Combined Workflow (Recommended)

1. **Audit first** — understand the system, identify candidate root causes  
2. **Instrument second** — add targeted trace logging at the decision points identified by the audit  
3. **Run and compare** — let the data speak  
4. **Promote or clean up** — if the trace reveals a permanent observability gap (like guard decisions not going to TML), promote the logging to a permanent system. Otherwise, clean up.

---

## Real Example: Position Guard Divergence (Feb 2026)

| Phase | Approach | Result |
|-------|----------|--------|
| Phases 1-9 | Code audits | 10+ conversations, multiple hypotheses, no definitive answer |
| Phase 10 | Trace logging | Root cause found in **1 deployment cycle** |

**Root cause:** `get_warrior_monitor()` (global singleton) used instead of `engine.monitor` in `_check_position_guards`. The global singleton had no positions in the concurrent runner, bypassing the max-scale guard entirely.

**Why auditing missed it:** The code *looked* correct — `get_warrior_monitor()` is a standard pattern used elsewhere. The bug was a **runtime identity problem** (which monitor instance is active), not a structural problem visible in code.

**Why tracing caught it:** Trace data showed identical prices, identical triggers, identical MACD/cooldown guards — and exactly 10 position guard blocks in sequential, zero in concurrent. The data pointed directly to the line.

**Bonus finding:** Guard decisions weren't being logged to TML at all. This was promoted to a permanent `GUARD_BLOCK` event type in `trade_event_service.py`.
