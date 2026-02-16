"""Run batch sim for 14 re-entry cases and save trade-level results."""
import requests
import json
import os

CASE_IDS = [
    "ross_gwav_20260116", "ross_mnts_20260209", "ross_lrhc_20260130",
    "ross_pavm_20260121", "ross_mlec_20260213", "ross_batl_20260126",
    "ross_batl_20260127", "ross_vero_20260116", "ross_rolr_20260114",
    "ross_tnmg_20260116", "ross_evmn_20260210", "ross_dcx_20260129",
    "ross_bnai_20260205", "ross_bnkk_20260115",
]

print("Running batch for 14 re-entry cases...")
r = requests.post(
    "http://localhost:8000/warrior/sim/run_batch_concurrent",
    json={"case_ids": CASE_IDS},
    timeout=300,
)
data = r.json()

out_path = os.path.join(
    os.path.dirname(__file__), "..", "reports", "2026-02-15", "reentry_batch_results.json"
)
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w") as f:
    json.dump(data, f, indent=2)

print(f"Cases returned: {len(data.get('results', []))}")
print()

for res in data.get("results", []):
    cid = res.get("case_id", "?")
    pnl = res.get("total_pnl", 0)
    trades = res.get("trades", [])
    n = len(trades)
    print(f"{cid}: ${pnl:+.2f}  trades={n}")
    for i, t in enumerate(trades):
        entry_t = t.get("entry_time", "?")
        exit_t = t.get("exit_time", "?")
        t_pnl = t.get("pnl", 0)
        trigger = t.get("entry_trigger", "?")
        exit_r = t.get("exit_reason", "?")
        ep = t.get("entry_price", 0)
        xp = t.get("exit_price", 0)
        shares = t.get("shares", 0)
        print(f"  T{i+1}: {entry_t} -> {exit_t}  ${t_pnl:+.2f}  "
              f"entry={trigger} exit={exit_r} "
              f"@${ep}->${xp} x{shares}")
    print()

print("Saved to:", os.path.abspath(out_path))
