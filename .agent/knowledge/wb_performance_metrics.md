# WB Performance Metrics — Definitions

> **Version:** 2026-02-27  
> **Authority:** Clay (product owner) + Coordinator

---

## Primary Metrics

### P&L Capture (%)
**Formula:** `Bot Total P&L / Ross Total P&L × 100`  
**Scope:** All test cases in the batch (same universe for both)  
**What it measures:** Overall portfolio-level performance vs Ross  
**Current baseline (37 cases):** 85.9% ($383K / $446K)

> Cases where Ross didn't trade (P&L = $0) or lost are included in Ross's total.
> If the bot profits on those cases, that's genuine alpha.

---

### Methodology Fidelity (%)
**Formula:** `Bot P&L on Ross-win cases / Ross P&L on Ross-win cases × 100`  
**Scope:** Only cases where `ross_pnl > 0` (Ross traded AND profited)  
**What it measures:** How well the bot replicates Ross's winning methodology  
**Current baseline:** ⚠️ Needs recomputation (was 41.9% on 26 cases — stale after ENVB P&L fix and +2 cases)

> This reveals how much of Ross's winning trades the bot captures.
> High capture + low fidelity = bot finds its own alpha but poorly replicates Ross.

---

### Win Rate (%)
**Formula:** `Bot profitable cases / total cases × 100`  
**Scope:** All test cases  
**Current baseline:** 73.0% (27/37)

---

## Anti-Patterns

- ❌ **Do NOT** call fidelity "capture" — they measure different things
- ❌ **Do NOT** report 82% capture without noting the fidelity gap
- ❌ **Do NOT** count no-trade cases as wins or losses for win rate
- ❌ **Do NOT** state P&L numbers without verifying against `wb-benchmark.md`

## Where These Are Computed

- `scripts/gc_quick_test.py` → `print_results()` and `diff_results()`
- `scripts/gc_memory_bridge.py` → `write_benchmark_memory()` (GC memory)
