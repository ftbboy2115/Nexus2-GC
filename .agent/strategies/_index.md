# Strategy Registry

This folder contains **authoritative methodology definitions** for all trading strategies used in Nexus 2.

## Purpose

- **Single Source of Truth**: Each strategy is defined in one place
- **Agent Reference**: All specialist agents consult this registry for methodology details
- **Extensibility**: New strategies (including R&D Lab generated) are added as new files

---

## Registered Strategies

| File | Strategy | Bot/System | Status |
|------|----------|------------|--------|
| [warrior.md](warrior.md) | Ross Cameron / Warrior Trading | Warrior Bot | ✅ Production |
| [qullamaggie.md](qullamaggie.md) | Kristjan Kullamägi (KK) | NACbot | ✅ Production |
| [algo_generated.md](algo_generated.md) | R&D Lab Generated Strategies | Algo Lab | 🔬 Template |

---

## How Agents Use This Registry

1. **Before implementing trading logic**: Read the relevant strategy file
2. **Before writing tests**: Verify stop/entry logic matches documented rules
3. **When uncertain**: Cite the specific rule from this registry
4. **Adding new strategies**: Create a new file, update this index

---

## Strategy File Template

Each strategy file should include:

```markdown
# [Strategy Name]

## Overview
Brief description of the trading approach

## Core Methodology
- Entry criteria
- Stop logic
- Position sizing
- Exit rules

## What This Strategy Uses
- Indicators, patterns, catalysts

## What This Strategy Does NOT Use
- Anti-patterns, excluded indicators

## Primary Sources
Links to transcripts, KIs, or documentation

## Implementation Notes
Bot-specific implementation details
```

---

## Hallucination Prevention

> [!CAUTION]
> **Never invent trading rules.** If a rule is not documented in this registry or its sources, say "I don't have documented evidence for this."

Common confusions to avoid:
- **RS** = Relative Strength vs SPY, NOT RSI indicator
- **EP** = Episodic Pivot (earnings gap), NOT Entry Point
- Ross's stops = **candle low**, not fixed cents
- KK's stops = **ATR-based**, not candle low
