"""Diagnostic: check if MNTS/MLEC have re-entries in batch sim."""
import requests
import json

BATCH_URL = "http://localhost:8000/warrior/sim/run_batch_concurrent"
TARGET_CASES = ["ross_mnts_20260209", "ross_mlec_20260213", "ross_flye_20260206", "ross_lcfy_20260116"]

r = requests.post(BATCH_URL, json={"case_ids": TARGET_CASES}, timeout=120)
data = r.json()

for result in data.get("results", []):
    case_id = result["case_id"]
    trades = result.get("trades", [])
    total_pnl = result.get("total_pnl", 0)
    
    print(f"\n{'='*80}")
    print(f"  {case_id} | Total P&L: ${total_pnl:+,.2f} | Trades: {len(trades)}")
    print(f"{'='*80}")
    
    if len(trades) <= 1:
        print("  >> SINGLE ENTRY ONLY - re-entry gate NOT applicable")
    else:
        print(f"  >> {len(trades)} ENTRIES - re-entry gate SHOULD apply")
    
    for i, t in enumerate(trades):
        entry = t.get("entry_price", 0)
        exit_p = t.get("exit_price", "open")
        pnl = t.get("pnl", 0)
        trigger = t.get("entry_trigger", "?")
        reason = t.get("exit_reason", "?")
        
        marker = " <<<< LOSS" if pnl < 0 else ""
        print(f"  Trade {i+1}: entry=${entry}, exit=${exit_p}, pnl=${pnl:+,.2f}, "
              f"trigger={trigger}, exit_reason={reason}{marker}")
