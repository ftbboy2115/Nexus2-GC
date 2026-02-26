import json, sys

f = sys.argv[1] if len(sys.argv) > 1 else "nexus2/reports/gc_diagnostics/sweep_max_reentry_after_loss.json"
d = json.load(open(f))
print(f"Setting: {d.get('setting', '?')}")
print(f"Results: {len(d.get('results', []))}")
print()
for r in d.get("results", []):
    val = r.get("value", "?")
    pnl = r.get("total_pnl", 0)
    ross = r.get("ross_pnl", 0)
    delta = r.get("delta", 0) 
    winners = r.get("winners", 0)
    cap = r.get("capture", 0)
    rt = r.get("runtime", 0)
    print(f"  val={val:>3}  PnL=${pnl:>10,.2f}  ross=${ross:>10,.2f}  delta=${delta:>10,.2f}  W={winners}  cap={cap:.1f}%  time={rt:.0f}s")
