"""
10s vs 1min Forensic Comparison — Identify why 10s stepping loses $210K vs 1min.

Runs batch tests at both timeframes with trade details, then compares:
- Entry prices and timing
- Exit reasons and prices
- Stop-hit frequency
- Trade count differences

Usage:
  python scripts/gc_10s_forensic.py           # Run both batches + compare
  python scripts/gc_10s_forensic.py --no-run  # Compare saved results only
"""

import json
import os
import sys
import urllib.request
import time

NEXUS_PATH = os.environ.get(
    "NEXUS_PATH",
    r"C:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus"
)
REPORT_DIR = os.path.join(NEXUS_PATH, "nexus2", "reports", "gc_diagnostics")
RESULTS_FILE = os.path.join(REPORT_DIR, "forensic_10s_vs_1min.json")
API_BASE = "http://localhost:8000"


def fetch_json(url: str, method: str = "GET", body: dict | None = None, timeout: int = 600) -> dict:
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def run_batch(timeframe: str) -> dict:
    """Run batch with include_trades=True and specific timeframe."""
    body = {
        "include_trades": True,
    }
    if timeframe == "10s":
        body["config_overrides"] = {"entry_bar_timeframe": "10s"}
    
    print(f"\n  Running batch with {timeframe} bars...")
    start = time.time()
    result = fetch_json(f"{API_BASE}/warrior/sim/run_batch_concurrent", method="POST", body=body)
    elapsed = time.time() - start
    pnl = result["summary"]["total_pnl"]
    print(f"  {timeframe}: P&L=${pnl:,.2f} ({elapsed:.0f}s)")
    return result


def compare_results(results_1min: dict, results_10s: dict):
    """Compare trade-by-trade differences between timeframes."""
    
    # Index by case_id
    cases_1min = {r["case_id"]: r for r in results_1min["results"]}
    cases_10s = {r["case_id"]: r for r in results_10s["results"]}
    
    all_cases = sorted(set(cases_1min.keys()) | set(cases_10s.keys()))
    
    divergent_cases = []
    
    for case_id in all_cases:
        c1 = cases_1min.get(case_id, {})
        c10 = cases_10s.get(case_id, {})
        
        pnl_1min = c1.get("total_pnl", 0)
        pnl_10s = c10.get("total_pnl", 0)
        delta = pnl_10s - pnl_1min
        ross_pnl = c1.get("ross_pnl", 0) or c10.get("ross_pnl", 0)
        
        trades_1min = c1.get("trades", [])
        trades_10s = c10.get("trades", [])
        
        divergent_cases.append({
            "case_id": case_id,
            "symbol": c1.get("symbol", c10.get("symbol", "?")),
            "ross_pnl": ross_pnl,
            "pnl_1min": pnl_1min,
            "pnl_10s": pnl_10s,
            "delta": delta,
            "trade_count_1min": len(trades_1min),
            "trade_count_10s": len(trades_10s),
            "trades_1min": trades_1min,
            "trades_10s": trades_10s,
        })
    
    # Sort by absolute delta (biggest divergences first)
    divergent_cases.sort(key=lambda c: abs(c["delta"]), reverse=True)
    
    return divergent_cases


def print_report(divergent_cases: list):
    """Print forensic comparison report."""
    
    total_delta = sum(c["delta"] for c in divergent_cases)
    improved = sum(1 for c in divergent_cases if c["delta"] > 100)
    worsened = sum(1 for c in divergent_cases if c["delta"] < -100)
    unchanged = len(divergent_cases) - improved - worsened
    
    print(f"\n{'='*100}")
    print(f"  10s vs 1min FORENSIC COMPARISON")
    print(f"{'='*100}")
    print(f"  Total P&L delta (10s - 1min): ${total_delta:+,.2f}")
    print(f"  Cases improved with 10s: {improved}")
    print(f"  Cases worsened with 10s: {worsened}")
    print(f"  Cases unchanged: {unchanged}")
    
    # Show top divergent cases with trade details
    print(f"\n{'='*100}")
    print(f"  TOP DIVERGENT CASES (sorted by |delta|)")
    print(f"{'='*100}")
    
    for case in divergent_cases:
        delta = case["delta"]
        if abs(delta) < 100:  # Skip negligible differences
            continue
        
        direction = "WORSE" if delta < 0 else "BETTER"
        
        print(f"\n{'─'*80}")
        print(f"  {case['case_id']}  ({case['symbol']})")
        print(f"{'─'*80}")
        print(f"  Ross:  ${case['ross_pnl']:>12,.2f}")
        print(f"  1min:  ${case['pnl_1min']:>12,.2f}  ({case['trade_count_1min']} trades)")
        print(f"  10s:   ${case['pnl_10s']:>12,.2f}  ({case['trade_count_10s']} trades)")
        print(f"  Delta: ${delta:>+12,.2f}  [{direction} with 10s]")
        
        # Compare individual trades
        trades_1min = case.get("trades_1min", [])
        trades_10s = case.get("trades_10s", [])
        
        max_trades = max(len(trades_1min), len(trades_10s))
        
        if max_trades > 0:
            print(f"\n  {'Trade':>7} | {'--- 1min ---':^36} | {'--- 10s ---':^36}")
            print(f"  {'':>7} | {'Entry':>8} {'Exit':>8} {'P&L':>10} {'Reason':>8} | {'Entry':>8} {'Exit':>8} {'P&L':>10} {'Reason':>8}")
            print(f"  {'':>7}-+-{'-'*36}-+-{'-'*36}")
            
            for i in range(max_trades):
                t1 = trades_1min[i] if i < len(trades_1min) else None
                t10 = trades_10s[i] if i < len(trades_10s) else None
                
                def fmt_trade(t):
                    if t is None:
                        return f"{'---':>8} {'---':>8} {'---':>10} {'---':>8}"
                    entry = f"${t.get('entry_price', 0):.2f}"
                    exit_p = f"${t.get('exit_price', 0):.2f}" if t.get('exit_price') else "open"
                    pnl = f"${t.get('pnl', 0):+.2f}"
                    reason = (t.get('exit_reason') or t.get('exit_mode') or '?')[:8]
                    return f"{entry:>8} {exit_p:>8} {pnl:>10} {reason:>8}"
                
                print(f"  {'#'+str(i+1):>7} | {fmt_trade(t1)} | {fmt_trade(t10)}")
        
        # Diagnose the divergence
        diagnoses = []
        
        # Check if different number of trades
        if case["trade_count_1min"] != case["trade_count_10s"]:
            if case["trade_count_10s"] > case["trade_count_1min"]:
                diagnoses.append("MORE_TRADES_10s (10s triggered additional entries)")
            else:
                diagnoses.append("FEWER_TRADES_10s (10s missed entries that 1min caught)")
        
        # Check exit reason differences
        for i in range(min(len(trades_1min), len(trades_10s))):
            t1 = trades_1min[i]
            t10 = trades_10s[i]
            
            r1 = t1.get("exit_reason", "")
            r10 = t10.get("exit_reason", "")
            if r1 != r10:
                diagnoses.append(f"EXIT_REASON_DIFF: trade#{i+1} 1min={r1} vs 10s={r10}")
            
            # Check entry price difference
            e1 = t1.get("entry_price", 0)
            e10 = t10.get("entry_price", 0)
            if e1 and e10 and abs(e1 - e10) > 0.01:
                diagnoses.append(f"ENTRY_PRICE_DIFF: trade#{i+1} 1min=${e1:.2f} vs 10s=${e10:.2f} (Δ${e10-e1:+.2f})")
            
            # Check exit price difference
            x1 = t1.get("exit_price", 0) or 0
            x10 = t10.get("exit_price", 0) or 0
            if x1 and x10 and abs(x1 - x10) > 0.05:
                diagnoses.append(f"EXIT_PRICE_DIFF: trade#{i+1} 1min=${x1:.2f} vs 10s=${x10:.2f} (Δ${x10-x1:+.2f})")
        
        if diagnoses:
            print(f"\n  Diagnosis:")
            for d in diagnoses:
                print(f"    • {d}")
    
    # Summary of root causes
    print(f"\n{'='*100}")
    print(f"  ROOT CAUSE SUMMARY")
    print(f"{'='*100}")
    
    total_from_worsened = sum(c["delta"] for c in divergent_cases if c["delta"] < -100)
    total_from_improved = sum(c["delta"] for c in divergent_cases if c["delta"] > 100)
    print(f"  P&L lost from worsened cases:   ${total_from_worsened:+,.2f}")
    print(f"  P&L gained from improved cases: ${total_from_improved:+,.2f}")
    print(f"  Net impact:                     ${total_delta:+,.2f}")


def main():
    no_run = "--no-run" in sys.argv
    
    os.makedirs(REPORT_DIR, exist_ok=True)
    
    if no_run and os.path.exists(RESULTS_FILE):
        print("  Loading saved results...")
        with open(RESULTS_FILE, "r") as f:
            saved = json.load(f)
        results_1min = saved["results_1min"]
        results_10s = saved["results_10s"]
    else:
        # Run both batches
        results_1min = run_batch("1min")
        results_10s = run_batch("10s")
        
        # Save for later analysis
        with open(RESULTS_FILE, "w") as f:
            json.dump({
                "results_1min": results_1min,
                "results_10s": results_10s,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }, f, indent=2)
        print(f"\n  Raw results saved to {RESULTS_FILE}")
    
    # Compare
    divergent_cases = compare_results(results_1min, results_10s)
    print_report(divergent_cases)


if __name__ == "__main__":
    main()
