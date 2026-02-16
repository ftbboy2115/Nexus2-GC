"""A/B batch runner for re-entry quality gate comparison.

Uses the SEQUENTIAL /sim/run_batch endpoint because it shares the global engine,
allowing us to toggle settings via the API between runs.
The concurrent endpoint uses ProcessPoolExecutor with isolated contexts that
don't load persisted settings.
"""
import requests
import json
import sys

BASE = "http://localhost:8000/warrior"
SETTINGS_URL = f"{BASE}/monitor/settings"
BATCH_URL = f"{BASE}/sim/run_batch"


def set_gate(enabled: bool):
    """Toggle the re-entry quality gate via API."""
    r = requests.put(SETTINGS_URL, json={"block_reentry_after_loss": enabled}, timeout=10)
    if r.status_code == 200:
        print(f"[A/B] block_reentry_after_loss = {enabled}")
    else:
        print(f"[A/B] WARNING: Settings update failed: {r.status_code} {r.text}")


def run_batch(label: str):
    """Run batch and return results."""
    print(f"\n{'='*80}")
    print(f"  RUNNING BATCH: {label}")
    print(f"{'='*80}")
    r = requests.post(BATCH_URL, json={"case_ids": []}, timeout=600)
    data = r.json()
    summary = data.get("summary", {})
    print(f"  Total P&L: ${summary.get('total_pnl', 0):+,.2f}")
    print(f"  Cases: {summary.get('cases_run', 0)}, Profitable: {summary.get('cases_profitable', 0)}")
    return data


def print_comparison(on_results, off_results):
    """Print side-by-side comparison."""
    on_cases = {r["case_id"]: r for r in on_results.get("results", [])}
    off_cases = {r["case_id"]: r for r in off_results.get("results", [])}
    
    all_ids = sorted(set(list(on_cases.keys()) + list(off_cases.keys())))
    
    print(f"\n{'='*100}")
    print(f"  A/B COMPARISON: Re-entry Quality Gate")
    print(f"{'='*100}\n")
    
    print(f"{'Case':<32} {'Gate ON':>12} {'Gate OFF':>12} {'Diff':>12}  {'Impact'}")
    print(f"{'-'*90}")
    
    total_on = 0
    total_off = 0
    improved = 0
    regressed = 0
    unchanged = 0
    
    for cid in all_ids:
        on_pnl = on_cases.get(cid, {}).get("total_pnl", 0)
        off_pnl = off_cases.get(cid, {}).get("total_pnl", 0)
        diff = on_pnl - off_pnl
        total_on += on_pnl
        total_off += off_pnl
        
        if abs(diff) < 0.01:
            impact = ""
            unchanged += 1
        elif diff > 0:
            impact = f"✅ +${diff:,.2f}"
            improved += 1
        else:
            impact = f"❌ ${diff:,.2f}"
            regressed += 1
        
        print(f"{cid:<32} ${on_pnl:>+10,.2f} ${off_pnl:>+10,.2f} ${diff:>+10,.2f}  {impact}")
    
    print(f"{'-'*90}")
    total_diff = total_on - total_off
    print(f"{'TOTAL':<32} ${total_on:>+10,.2f} ${total_off:>+10,.2f} ${total_diff:>+10,.2f}")
    print(f"\nImproved: {improved} | Regressed: {regressed} | Unchanged: {unchanged}")
    print(f"Net impact of gate: ${total_diff:>+,.2f}")
    
    return {
        "total_on": total_on,
        "total_off": total_off,
        "diff": total_diff,
        "improved": improved,
        "regressed": regressed,
        "unchanged": unchanged,
    }


if __name__ == "__main__":
    # Run 1: Gate OFF (baseline — old behavior)
    set_gate(False)
    off_data = run_batch("GATE OFF (baseline — allow re-entry after loss)")
    
    # Run 2: Gate ON (new behavior)
    set_gate(True)
    on_data = run_batch("GATE ON (block re-entry after loss)")
    
    # Compare
    summary = print_comparison(on_data, off_data)
    
    print(f"\n{'='*100}")
    print(f"  VERDICT")
    print(f"{'='*100}")
    if summary["diff"] > 0:
        print(f"  ✅ Gate ON is BETTER by ${summary['diff']:,.2f}")
    elif summary["diff"] < 0:
        print(f"  ❌ Gate ON is WORSE by ${abs(summary['diff']):,.2f}")
    else:
        print(f"  — No difference")
