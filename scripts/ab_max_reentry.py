"""
A/B Sensitivity Test: max_reentry_after_loss

Tests the impact of different max_reentry_after_loss values on batch P&L.
Runs the full batch (35 cases) for each value and captures summary metrics.

Usage:
    python scripts/ab_max_reentry.py
"""

import json
import time
import requests

API_BASE = "http://localhost:8000"
SETTINGS_URL = f"{API_BASE}/warrior/monitor/settings"
BATCH_URL = f"{API_BASE}/warrior/sim/run_batch_concurrent"

# Values to test: current behavior (1) vs graduated (2, 3, 5)
TEST_VALUES = [1, 2, 3, 5]


def set_max_reentry(value: int):
    """Set max_reentry_after_loss via PUT."""
    r = requests.put(SETTINGS_URL, json={"max_reentry_after_loss": value}, timeout=10)
    if r.status_code == 200:
        print(f"[A/B] max_reentry_after_loss = {value}")
    else:
        print(f"[A/B] FAILED to set max_reentry_after_loss: {r.status_code} {r.text}")


def run_batch():
    """Run full batch test and return summary."""
    print("[A/B] Running batch (this takes 20-40 seconds)...")
    start = time.time()
    r = requests.post(BATCH_URL, json={"include_trades": False}, timeout=600)
    elapsed = time.time() - start
    if r.status_code != 200:
        print(f"[A/B] BATCH FAILED: {r.status_code}")
        return None
    data = r.json()
    summary = data.get("summary", {})
    summary["runtime_seconds"] = round(elapsed, 1)
    return summary


def main():
    results = []

    for val in TEST_VALUES:
        print(f"\n{'='*60}")
        print(f"Testing max_reentry_after_loss = {val}")
        print(f"{'='*60}")

        set_max_reentry(val)
        time.sleep(1)  # Let settings propagate

        summary = run_batch()
        if summary:
            results.append({
                "max_reentry_after_loss": val,
                "total_pnl": summary.get("total_pnl", 0),
                "ross_pnl": summary.get("total_ross_pnl", 0),
                "delta": summary.get("delta", 0),
                "winners": summary.get("cases_profitable", 0),
                "cases": summary.get("cases_run", 0),
                "runtime": summary.get("runtime_seconds", 0),
            })
            print(f"  P&L: ${summary.get('total_pnl', 0):,.2f} | "
                  f"Winners: {summary.get('cases_profitable', 0)} | "
                  f"Runtime: {summary.get('runtime_seconds', 0):.0f}s")
        else:
            print("  FAILED — skipping")

    # Summary table
    print(f"\n{'='*60}")
    print("SENSITIVITY TEST RESULTS")
    print(f"{'='*60}")
    print(f"{'Max Retries':>12} | {'Bot P&L':>12} | {'Delta':>12} | {'Winners':>8} | {'Capture':>8}")
    print(f"{'-'*12}-+-{'-'*12}-+-{'-'*12}-+-{'-'*8}-+-{'-'*8}")

    for r in results:
        ross = r["ross_pnl"] if r["ross_pnl"] != 0 else 1
        capture = r["total_pnl"] / ross * 100 if ross != 0 else 0
        print(f"{r['max_reentry_after_loss']:>12} | ${r['total_pnl']:>10,.2f} | "
              f"${r['delta']:>10,.2f} | {r['winners']:>8} | {capture:>7.1f}%")

    # Reset to recommended default
    set_max_reentry(3)
    print(f"\n[A/B] Reset max_reentry_after_loss to 3 (recommended default)")

    # Save results
    outfile = "nexus2/reports/2026-02-23/ab_max_reentry_results.json"
    with open(outfile, "w") as f:
        json.dump(results, f, indent=2)
    print(f"[A/B] Results saved to {outfile}")


if __name__ == "__main__":
    main()
