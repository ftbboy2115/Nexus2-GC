"""Quick batch runner with clean output."""
import requests, json

r = requests.post("http://localhost:8000/warrior/sim/run_batch_concurrent", json={"case_ids": []}, timeout=300)
data = r.json()

summary = data.get("summary", {})
results = sorted(data.get("results", []), key=lambda x: x.get("total_pnl", 0))

print(f"\n{'='*90}")
print(f"BATCH TEST RESULTS ({summary.get('cases_run', 0)} cases)")
print(f"{'='*90}\n")

print(f"{'Case':<32} {'Bot P&L':>12} {'Ross P&L':>12} {'Delta':>12}")
print(f"{'-'*70}")

for c in results:
    bot = c.get("total_pnl", 0)
    ross = c.get("ross_pnl", 0)
    delta = c.get("delta", 0)
    sign = "+" if bot >= 0 else ""
    print(f"{c['case_id']:<32} {sign}${bot:>10,.2f}  ${ross:>10,.2f}  ${delta:>10,.2f}")

print(f"{'-'*70}")
print(f"{'TOTAL':<32} ${summary.get('total_pnl', 0):>+10,.2f}  ${summary.get('total_ross_pnl', 0):>10,.2f}  ${summary.get('delta', 0):>10,.2f}")
print(f"\nCases profitable: {summary.get('cases_profitable', 0)}/{summary.get('cases_run', 0)}")
print(f"Runtime: {summary.get('runtime_seconds', 0):.1f}s")
