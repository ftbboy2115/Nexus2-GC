"""Run guards-OFF batch only — saves to JSON. No stdin, no prompts."""
import json, os, time, urllib.request

API = "http://127.0.0.1:8000"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "nexus2", "reports", "2026-02-24")
OFF_FILE = os.path.join(OUT_DIR, "batch_guards_off.json")

body = json.dumps({"include_trades": True, "skip_guards": True}).encode()
req = urllib.request.Request(
    f"{API}/warrior/sim/run_batch_concurrent",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)

print("Running batch with guards OFF... (timeout 900s)")
start = time.time()
resp = urllib.request.urlopen(req, timeout=900)
data = json.loads(resp.read().decode())
elapsed = time.time() - start

results = data.get("results", [])
total = sum(r.get("total_pnl", 0) or 0 for r in results)
ross = sum(r.get("ross_pnl", 0) or 0 for r in results)
cap = (total / ross * 100) if ross else 0

print(f"Done in {elapsed:.1f}s -- {len(results)} cases")
print(f"Bot P&L: {total:,.0f}  Ross: {ross:,.0f}  Capture: {cap:.1f}%")

with open(OFF_FILE, "w") as f:
    json.dump(data, f, indent=2, default=str)
print(f"Saved: {OFF_FILE}")
