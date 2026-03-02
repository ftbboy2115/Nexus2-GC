"""
GC Price-Tier Sizing Backtest

Validates Ross Cameron's March 2026 price-based position sizing hypothesis:
  - Double size on $5-$10 stocks (sweet spot)
  - Half size on $2-$5 and $10-$20 stocks
  - NO trades on stocks >$20 (net negative YTD)

Approach: Post-hoc analysis. Runs the batch test with include_trades=True,
then mathematically scales each trade's P&L based on what the position size
WOULD have been under price-tier rules. Since P&L = shares * (exit - entry),
scaling shares by Nx also scales P&L by Nx.

Usage:
  python scripts/gc_price_tier_backtest.py
  python scripts/gc_price_tier_backtest.py --cases ross_BATL_20260227 ross_ROLR_20260114
  python scripts/gc_price_tier_backtest.py --json
"""
from __future__ import annotations

import io
import json
import os
import sys
import argparse
import time

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
except (AttributeError, TypeError):
    pass

import urllib.request

BASE_URL = "http://127.0.0.1:8000"
NEXUS_PATH = os.environ.get(
    "NEXUS_PATH",
    r"C:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus"
)
REPORT_DIR = os.path.join(NEXUS_PATH, "nexus2", "reports", "2026-03-01")


# =============================================================================
# PRICE TIER DEFINITIONS (from Ross Cameron Mar 1, 2026 watchlist video)
# =============================================================================
# Ross's YTD performance by price range showed:
#   $5-$10  = best performance     → DOUBLE size (2.0x)
#   $2-$5   = moderate             → HALF size   (0.5x)
#   $10-$20 = moderate             → HALF size   (0.5x)
#   >$20    = NET NEGATIVE on year → SKIP        (0.0x)
#   <$2     = penny stocks, skip   → SKIP        (0.0x)

PRICE_TIERS = [
    {"label": "$0-$2",   "min": 0,  "max": 2,  "multiplier": 0.0},
    {"label": "$2-$5",   "min": 2,  "max": 5,  "multiplier": 0.5},
    {"label": "$5-$10",  "min": 5,  "max": 10, "multiplier": 2.0},
    {"label": "$10-$20", "min": 10, "max": 20, "multiplier": 0.5},
    {"label": "$20+",    "min": 20, "max": 9999, "multiplier": 0.0},
]


def get_tier(entry_price: float) -> dict:
    """Get the price tier for a given entry price."""
    for tier in PRICE_TIERS:
        if tier["min"] <= entry_price < tier["max"]:
            return tier
    return PRICE_TIERS[-1]  # fallback to $20+


def fetch_json(url: str, method: str = "GET", body: dict | None = None, timeout: int = 600) -> dict:
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def run_batch_with_trades(case_ids: list[str] | None = None) -> dict:
    """Run batch test with include_trades=True to get per-trade details."""
    body: dict = {"include_trades": True}
    if case_ids:
        body["case_ids"] = case_ids
    return fetch_json(f"{BASE_URL}/warrior/sim/run_batch_concurrent", method="POST", body=body)


def analyze_price_tiers(batch_data: dict) -> dict:
    """
    Analyze batch results through the price-tier lens.
    
    For each case/trade, compute:
      - baseline_pnl: actual P&L with current flat sizing
      - tiered_pnl: hypothetical P&L with price-tier multipliers
    """
    results = batch_data.get("results", [])
    
    analysis = {
        "cases": [],
        "tier_breakdown": {tier["label"]: {"trades": 0, "baseline_pnl": 0, "tiered_pnl": 0} for tier in PRICE_TIERS},
    }
    
    total_baseline = 0
    total_tiered = 0
    cases_baseline_profitable = 0
    cases_tiered_profitable = 0
    skipped_by_price_gate = 0
    
    for case in results:
        case_id = case.get("case_id", "?")
        symbol = case.get("symbol", "?")
        trades = case.get("trades", [])
        baseline_case_pnl = case.get("total_pnl", 0) or 0
        ross_pnl = case.get("ross_pnl", 0) or 0
        
        tiered_case_pnl = 0
        trade_details = []
        
        if not trades:
            # No trades — need to infer price from premarket_data or just use baseline
            # If no trades, both baseline and tiered are 0
            analysis["cases"].append({
                "case_id": case_id,
                "symbol": symbol,
                "ross_pnl": ross_pnl,
                "baseline_pnl": baseline_case_pnl,
                "tiered_pnl": 0,
                "delta": -baseline_case_pnl,
                "tier": "N/A (no trades)",
                "multiplier": "N/A",
                "trades": [],
            })
            total_baseline += baseline_case_pnl
            continue
        
        for trade in trades:
            entry_price = trade.get("entry_price", 0) or 0
            trade_pnl = trade.get("pnl", 0) or 0
            shares = trade.get("shares", 0)
            
            tier = get_tier(entry_price)
            multiplier = tier["multiplier"]
            
            # Scale P&L by the tier multiplier
            # baseline: 1.0x (current behavior)
            # tiered: Nx based on price range
            scaled_pnl = trade_pnl * multiplier
            
            trade_details.append({
                "entry": entry_price,
                "shares": shares,
                "pnl": trade_pnl,
                "tier": tier["label"],
                "multiplier": multiplier,
                "scaled_pnl": round(scaled_pnl, 2),
            })
            
            tiered_case_pnl += scaled_pnl
            
            # Accumulate tier breakdown
            analysis["tier_breakdown"][tier["label"]]["trades"] += 1
            analysis["tier_breakdown"][tier["label"]]["baseline_pnl"] += trade_pnl
            analysis["tier_breakdown"][tier["label"]]["tiered_pnl"] += scaled_pnl
            
            if multiplier == 0.0:
                skipped_by_price_gate += 1
        
        tiered_case_pnl = round(tiered_case_pnl, 2)
        
        # Determine primary tier for the case (first trade's entry)
        primary_tier = get_tier(trades[0]["entry_price"]) if trades else {"label": "N/A", "multiplier": "N/A"}
        
        analysis["cases"].append({
            "case_id": case_id,
            "symbol": symbol,
            "ross_pnl": ross_pnl,
            "baseline_pnl": baseline_case_pnl,
            "tiered_pnl": tiered_case_pnl,
            "delta": round(tiered_case_pnl - baseline_case_pnl, 2),
            "tier": primary_tier["label"],
            "multiplier": primary_tier["multiplier"],
            "trades": trade_details,
        })
        
        total_baseline += baseline_case_pnl
        total_tiered += tiered_case_pnl
        
        if baseline_case_pnl > 0:
            cases_baseline_profitable += 1
        if tiered_case_pnl > 0:
            cases_tiered_profitable += 1
    
    analysis["summary"] = {
        "total_baseline_pnl": round(total_baseline, 2),
        "total_tiered_pnl": round(total_tiered, 2),
        "delta": round(total_tiered - total_baseline, 2),
        "delta_pct": round((total_tiered - total_baseline) / abs(total_baseline) * 100, 1) if total_baseline != 0 else 0,
        "cases_baseline_profitable": cases_baseline_profitable,
        "cases_tiered_profitable": cases_tiered_profitable,
        "trades_skipped_by_price_gate": skipped_by_price_gate,
        "total_cases": len(results),
        "ross_total_pnl": round(sum(c.get("ross_pnl", 0) or 0 for c in results), 2),
    }
    
    return analysis


def print_report(analysis: dict):
    """Print a human-readable comparison report."""
    summary = analysis["summary"]
    
    print()
    print("=" * 90)
    print("  PRICE-TIER SIZING BACKTEST")
    print("  Based on Ross Cameron's Mar 1, 2026 watchlist video hypothesis")
    print("=" * 90)
    
    # Tier definitions
    print()
    print("  TIER RULES:")
    for tier in PRICE_TIERS:
        action = {0.0: "SKIP", 0.5: "HALF SIZE", 1.0: "NORMAL", 2.0: "DOUBLE SIZE"}[tier["multiplier"]]
        print(f"    {tier['label']:>10s}  →  {action} ({tier['multiplier']}x)")
    
    # Summary comparison
    print()
    print("  " + "-" * 86)
    print(f"  {'METRIC':<40s} {'BASELINE (current)':>20s} {'PRICE-TIERED':>20s}")
    print("  " + "-" * 86)
    print(f"  {'Total Bot P&L':<40s} ${summary['total_baseline_pnl']:>18,.2f} ${summary['total_tiered_pnl']:>18,.2f}")
    print(f"  {'Ross Total P&L':<40s} ${summary['ross_total_pnl']:>18,.2f} ${summary['ross_total_pnl']:>18,.2f}")
    print(f"  {'Delta (Tiered - Baseline)':<40s} {'':>20s} ${summary['delta']:>+18,.2f}")
    print(f"  {'Delta %':<40s} {'':>20s} {summary['delta_pct']:>+18.1f}%")
    print(f"  {'Cases Profitable':<40s} {summary['cases_baseline_profitable']:>20d} {summary['cases_tiered_profitable']:>20d}")
    print(f"  {'Trades Skipped (>$20 or <$2)':<40s} {'':>20s} {summary['trades_skipped_by_price_gate']:>20d}")
    print("  " + "-" * 86)
    
    # Verdict
    delta = summary["delta"]
    print()
    if delta > 0:
        print(f"  ✅ VERDICT: Price-tier sizing IMPROVES P&L by ${delta:,.2f} ({summary['delta_pct']:+.1f}%)")
    elif delta < 0:
        print(f"  ❌ VERDICT: Price-tier sizing HURTS P&L by ${-delta:,.2f} ({summary['delta_pct']:+.1f}%)")
    else:
        print(f"  ➖ VERDICT: Price-tier sizing has NO EFFECT on P&L")
    
    # Tier breakdown
    print()
    print("  BREAKDOWN BY TIER:")
    print(f"  {'Tier':>10s} | {'Trades':>7s} | {'Baseline P&L':>14s} | {'Tiered P&L':>14s} | {'Delta':>14s}")
    print(f"  {'-'*10}-+-{'-'*7}-+-{'-'*14}-+-{'-'*14}-+-{'-'*14}")
    for tier in PRICE_TIERS:
        tb = analysis["tier_breakdown"][tier["label"]]
        if tb["trades"] > 0:
            d = tb["tiered_pnl"] - tb["baseline_pnl"]
            print(
                f"  {tier['label']:>10s} | {tb['trades']:>7d} | "
                f"${tb['baseline_pnl']:>12,.2f} | ${tb['tiered_pnl']:>12,.2f} | "
                f"${d:>+12,.2f}"
            )
    
    # Per-case detail
    print()
    print("  PER-CASE COMPARISON:")
    print(f"  {'Case':<30s} | {'Tier':>10s} | {'Mult':>5s} | {'Baseline':>12s} | {'Tiered':>12s} | {'Delta':>12s}")
    print(f"  {'-'*30}-+-{'-'*10}-+-{'-'*5}-+-{'-'*12}-+-{'-'*12}-+-{'-'*12}")
    
    # Sort by delta (biggest impact first)
    sorted_cases = sorted(analysis["cases"], key=lambda c: c["delta"])
    
    for case in sorted_cases:
        mult_str = f"{case['multiplier']}x" if isinstance(case["multiplier"], (int, float)) else case["multiplier"]
        delta_str = f"${case['delta']:>+10,.2f}" if case["delta"] != 0 else f"{'$0.00':>12s}"
        
        # Highlight significant changes
        marker = ""
        if isinstance(case["multiplier"], (int, float)):
            if case["multiplier"] == 0.0 and case["baseline_pnl"] != 0:
                marker = " 🚫"
            elif case["multiplier"] == 2.0:
                marker = " ⬆"
        
        print(
            f"  {case['case_id']:<30s} | {case['tier']:>10s} | {mult_str:>5s} | "
            f"${case['baseline_pnl']:>10,.2f} | ${case['tiered_pnl']:>10,.2f} | "
            f"{delta_str}{marker}"
        )
    
    print()


def main():
    parser = argparse.ArgumentParser(description="Price-Tier Sizing Backtest")
    parser.add_argument("--cases", nargs="*", help="Specific case IDs to run (default: all)")
    parser.add_argument("--json", action="store_true", help="Output JSON (for automation)")
    args = parser.parse_args()
    
    case_ids = args.cases if args.cases else None
    
    if not args.json:
        print("\n  🔬 Running batch test with trade details...")
        if case_ids:
            print(f"  Cases: {', '.join(case_ids)}")
        print()
    
    # Step 1: Run batch with trades
    t0 = time.time()
    try:
        batch_data = run_batch_with_trades(case_ids)
    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"  ERROR: Could not run batch test: {e}")
            print(f"  Make sure the server is running on port 8000")
        sys.exit(1)
    
    batch_time = time.time() - t0
    
    if not args.json:
        print(f"  Batch completed in {batch_time:.1f}s")
        print(f"  Analyzing price tiers...")
    
    # Step 2: Analyze through price-tier lens
    analysis = analyze_price_tiers(batch_data)
    analysis["batch_runtime_seconds"] = round(batch_time, 1)
    
    # Step 3: Output
    if args.json:
        print(json.dumps(analysis, indent=2, default=str))
    else:
        print_report(analysis)
    
    # Step 4: Save results
    os.makedirs(REPORT_DIR, exist_ok=True)
    outfile = os.path.join(REPORT_DIR, "price_tier_backtest_results.json")
    with open(outfile, "w") as f:
        json.dump(analysis, f, indent=2, default=str)
    
    if not args.json:
        print(f"  Results saved to {outfile}\n")


if __name__ == "__main__":
    main()
