"""
A/B Test: Re-entry Quality Gate (full batch)

Run 1: Gate ON  (block_reentry_after_loss = True)  — default
Run 2: Gate OFF (block_reentry_after_loss = False) — baseline

Toggles the setting via PUT /monitor/settings between runs.
Concurrent batch runner picks up saved settings via load_monitor_settings().
"""
import requests
import json
import time

BASE = "http://localhost:8000/warrior"
BATCH_URL = f"{BASE}/sim/run_batch_concurrent"
SETTINGS_URL = f"{BASE}/monitor/settings"


def set_gate(enabled: bool):
    """Toggle block_reentry_after_loss via PUT."""
    r = requests.put(SETTINGS_URL, json={"block_reentry_after_loss": enabled}, timeout=10)
    r.raise_for_status()
    print(f"  Gate set to: {enabled}")


def run_batch(label: str) -> dict:
    """Run full batch and return results dict."""
    print(f"\n{'='*60}")
    print(f"  Running: {label}")
    print(f"{'='*60}")
    start = time.time()
    r = requests.post(BATCH_URL, json={}, timeout=300)
    r.raise_for_status()
    data = r.json()
    elapsed = time.time() - start
    print(f"  Completed in {elapsed:.1f}s")
    return data


def summarize(results: list) -> dict:
    """Summarize batch results."""
    total_pnl = sum(r.get("total_pnl", 0) for r in results)
    total_ross = sum(r.get("ross_pnl", 0) for r in results)
    cases = {r["case_id"]: r.get("total_pnl", 0) for r in results}
    return {"total_pnl": total_pnl, "total_ross": total_ross, "cases": cases, "count": len(results)}


if __name__ == "__main__":
    # Run 1: Gate ON
    set_gate(True)
    data_on = run_batch("Gate ON (block re-entry after loss)")
    results_on = data_on.get("results", [])
    summary_on = summarize(results_on)

    # Run 2: Gate OFF
    set_gate(False)
    data_off = run_batch("Gate OFF (allow re-entry after loss)")
    results_off = data_off.get("results", [])
    summary_off = summarize(results_off)

    # Restore gate to ON (safe default)
    set_gate(True)

    # Compare
    print(f"\n{'='*80}")
    print(f"  A/B TEST RESULTS: Re-entry Quality Gate")
    print(f"{'='*80}")
    print(f"  Gate ON  total P&L: ${summary_on['total_pnl']:>+12,.2f}  ({summary_on['count']} cases)")
    print(f"  Gate OFF total P&L: ${summary_off['total_pnl']:>+12,.2f}  ({summary_off['count']} cases)")
    delta = summary_on["total_pnl"] - summary_off["total_pnl"]
    print(f"  Gate IMPACT:        ${delta:>+12,.2f}")
    print(f"  Ross total P&L:     ${summary_on['total_ross']:>+12,.2f}")
    print()

    # Per-case comparison (only show differences)
    print(f"  {'Case':<30} {'Gate ON':>12} {'Gate OFF':>12} {'Delta':>12}")
    print(f"  {'-'*30} {'-'*12} {'-'*12} {'-'*12}")
    diffs = []
    for case_id in sorted(summary_on["cases"].keys()):
        pnl_on = summary_on["cases"].get(case_id, 0)
        pnl_off = summary_off["cases"].get(case_id, 0)
        case_delta = pnl_on - pnl_off
        if abs(case_delta) > 0.01:
            diffs.append((case_id, pnl_on, pnl_off, case_delta))
            print(f"  {case_id:<30} ${pnl_on:>+11,.2f} ${pnl_off:>+11,.2f} ${case_delta:>+11,.2f}")

    if not diffs:
        print(f"  (no per-case differences)")
    
    print(f"\n  Cases with differences: {len(diffs)}/{summary_on['count']}")
    print(f"{'='*80}")
