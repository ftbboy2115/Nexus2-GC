#!/usr/bin/env python3
"""Compare two batch result JSON files."""
import json
import sys

old_file = sys.argv[1] if len(sys.argv) >= 2 else "/tmp/batch_results.json"
new_file = sys.argv[2] if len(sys.argv) >= 3 else "/tmp/batch_results_post_fix.json"

old = json.load(open(old_file))
new = json.load(open(new_file))

old_map = {r["case_id"]: r for r in old["results"]}
new_map = {r["case_id"]: r for r in new["results"]}

ot = old["summary"]["total_pnl"]
nt = new["summary"]["total_pnl"]
print(f"OLD total: ${ot:.2f}  NEW total: ${nt:.2f}  DELTA: ${nt - ot:+.2f}")
print()
print(f"{'CASE':<35} {'OLD PNL':>10} {'NEW PNL':>10} {'DELTA':>10}")
print("-" * 70)

for cid in sorted(set(list(old_map.keys()) + list(new_map.keys()))):
    o = old_map.get(cid, {})
    n = new_map.get(cid, {})
    op = o.get("total_pnl", 0)
    np2 = n.get("total_pnl", 0)
    d = np2 - op
    flag = " ***" if abs(d) > 0.01 else ""
    print(f"{cid:<35} {op:>10.2f} {np2:>10.2f} {d:>+10.2f}{flag}")

print()
print("*** = changed")
