"""Quick A/B test: isolate scaling v2 vs structural exits impact."""
import sys, os, json, time, io

# Encoding handled by PowerShell

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gc_param_sweep import run_batch

configs = {
    "A: Legacy scaling + legacy exits (baseline)": {
        "enable_level_break_scaling": False,
        "enable_structural_levels": False,
    },
    "B: Level-break scaling + legacy exits": {
        "enable_level_break_scaling": True,
        "enable_structural_levels": False,
    },
    "C: Legacy scaling + structural exits": {
        "enable_level_break_scaling": False,
        "enable_structural_levels": True,
    },
    "D: Level-break + structural exits (new default)": {
        "enable_level_break_scaling": True,
        "enable_structural_levels": True,
    },
}

print(f"\n{'='*90}")
print(f"  SCALING V2 A/B TEST — Isolating Changes")
print(f"{'='*90}\n")

results = {}
for label, overrides in configs.items():
    print(f"  Running: {label} ...")
    t0 = time.time()
    data = run_batch(monitor_overrides=overrides)
    elapsed = time.time() - t0
    
    summary = data.get("summary", {})
    total_bot = summary.get("total_pnl", 0) or 0
    total_ross = summary.get("total_ross_pnl", 0) or 0
    winners = summary.get("cases_profitable", 0) or 0
    cases = len(data.get("results", []))
    capture = (total_bot / total_ross * 100) if total_ross else 0
    
    # Fidelity
    raw = data.get("results", [])
    rt_bot = sum((r.get("total_pnl", r.get("bot_pnl", 0)) or 0) for r in raw if (r.get("ross_pnl", 0) or 0) > 0)
    rt_ross = sum((r.get("ross_pnl", 0) or 0) for r in raw if (r.get("ross_pnl", 0) or 0) > 0)
    fidelity = (rt_bot / rt_ross * 100) if rt_ross else 0
    
    results[label] = {"pnl": total_bot, "capture": capture, "fidelity": fidelity, "winners": winners, "cases": cases, "time": round(elapsed, 1)}
    print(f"    P&L: ${total_bot:>12,.2f} | Capture: {capture:.1f}% | Fidelity: {fidelity:.1f}% | {winners}W/{cases} | {elapsed:.0f}s\n")

print(f"\n{'='*90}")
print(f"  {'Config':<50s} | {'Bot P&L':>12s} | {'Capture':>8s} | {'Fidelity':>9s} | {'Win':>4s}")
print(f"  {'-'*50}-+-{'-'*12}-+-{'-'*8}-+-{'-'*9}-+-{'-'*4}")
for label, r in results.items():
    print(f"  {label:<50s} | ${r['pnl']:>10,.0f} | {r['capture']:>6.1f}% | {r['fidelity']:>7.1f}% | {r['winners']:>3}W")
print(f"{'='*90}\n")
