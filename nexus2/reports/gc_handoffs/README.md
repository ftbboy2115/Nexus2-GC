# GC ↔ Claude Communication Protocol

This directory enables structured data exchange between **Gravity Claw (GC)** and **Claude (Antigravity)** agents.

## Directory Structure

```
gc_handoffs/
├── gc_to_claude/      ← GC writes findings and validation results here
├── claude_to_gc/      ← Claude writes tasks for GC to execute here
└── README.md          ← This file
```

## Message Format

All messages are JSON files named: `YYYY-MM-DD_<topic>.json`

### GC → Claude (Findings)

```json
{
  "type": "finding|validation|regression",
  "timestamp": "2026-02-23T19:30:00-05:00",
  "case_id": "ross_npt_20260203",
  "symbol": "NPT",
  "category": "LATE_ENTRY",
  "data": { ... },
  "request": "Human-readable description of what Claude should investigate"
}
```

### Claude → GC (Tasks)

```json
{
  "type": "validate|sweep|test",
  "timestamp": "2026-02-23T19:45:00-05:00",
  "changed_files": ["warrior_entry_patterns.py"],
  "command": "python scripts/gc_quick_test.py NPT --json",
  "expected": "NPT entry should move earlier, delta should decrease"
}
```

## Available Scripts (for GC)

| Script | Flag | Purpose |
|--------|------|---------|
| `gc_quick_test.py <symbol> --json` | Single case test | Fast validation (~5-10s) |
| `gc_quick_test.py --all --diff --json` | Full diff | Regression detection (~25s) |
| `gc_quick_test.py --all --save` | Save baseline | After confirmed improvement |
| `gc_param_sweep.py <setting> <values> --json` | Parameter sweep | Optimize settings |
| `gc_batch_diagnose.py` | Full diagnosis | Categorize all issues |

## Protocol Rules

1. **GC does NOT modify source code** — it runs tests and reports findings
2. **Claude reads GC findings, makes code changes, writes validation tasks**
3. **GC validates Claude's changes by running the specified command**
4. **Baseline is saved only after confirmed net-positive results**
