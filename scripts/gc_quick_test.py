"""
GC Quick Test — Fast single-case or filtered batch test with diff comparison.

Usage:
  python scripts/gc_quick_test.py BATL              # Run one case
  python scripts/gc_quick_test.py BATL AAPL GRI     # Run specific cases
  python scripts/gc_quick_test.py --all             # Run all cases (like full batch)
  python scripts/gc_quick_test.py BATL --diff       # Run and diff vs last saved result
  python scripts/gc_quick_test.py --all --save      # Run all and save as baseline
  python scripts/gc_quick_test.py --all --diff      # Run all and diff vs saved baseline
"""
from __future__ import annotations

import io
import json
import os
import sys
import argparse
import time

# Fix Windows encoding
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
except (AttributeError, TypeError):
    pass

import urllib.request

try:
    from gc_memory_bridge import write_benchmark_memory
except ImportError:
    # Fallback: add scripts dir to path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from gc_memory_bridge import write_benchmark_memory

BASE_URL = "http://localhost:8000"
NEXUS_PATH = os.environ.get(
    "NEXUS_PATH",
    r"C:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus"
)
BASELINE_FILE = os.path.join(NEXUS_PATH, "nexus2", "reports", "gc_diagnostics", "baseline.json")
LAST_RUN_FILE = os.path.join(NEXUS_PATH, "nexus2", "reports", "gc_diagnostics", "last_run.json")


def fetch_json(url: str, method: str = "GET", body: dict | None = None, timeout: int = 600) -> dict:
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def resolve_case_ids(inputs: list[str]) -> list[str]:
    """Resolve symbol shorthands (BATL) to full case IDs (ross_batl_20260127).
    
    Accepts both full IDs and symbol shorthands. Symbol matching is case-insensitive.
    If a shorthand matches multiple cases (e.g., same symbol different dates), all are included.
    """
    # Fetch all test cases
    data = fetch_json(f"{BASE_URL}/warrior/sim/test_cases")
    all_cases = data.get("test_cases", [])
    
    resolved = []
    for inp in inputs:
        # If it looks like a full ID (contains underscore + digits), use as-is
        if "_" in inp and any(c.isdigit() for c in inp):
            resolved.append(inp)
            continue
        
        # Otherwise, match by symbol (case-insensitive)
        symbol_upper = inp.upper()
        matches = [c["id"] for c in all_cases if c.get("symbol", "").upper() == symbol_upper]
        
        if matches:
            resolved.extend(matches)
        else:
            print(f"  WARNING: No test case found for '{inp}', skipping")
    
    return resolved


def list_cases():
    """List all available test cases."""
    data = fetch_json(f"{BASE_URL}/warrior/sim/test_cases")
    cases = data.get("test_cases", [])
    print(f"\n  Available test cases ({len(cases)}):")
    print(f"  {'ID':<30s} | {'Symbol':<8s} | {'Date':<12s} | {'Setup'}")
    print(f"  {'-'*30}-+-{'-'*8}-+-{'-'*12}-+-{'-'*20}")
    for c in cases:
        print(f"  {c['id']:<30s} | {c.get('symbol','?'):<8s} | {c.get('trade_date','?'):<12s} | {c.get('setup_type','?')}")
    print()


def run_cases(case_ids: list[str] | None = None, include_trades: bool = False) -> dict:
    """Run batch test for specific cases or all."""
    body: dict = {"include_trades": include_trades}
    if case_ids:
        body["case_ids"] = case_ids
    t0 = time.time()
    result = fetch_json(f"{BASE_URL}/warrior/sim/run_batch_concurrent", method="POST", body=body)
    elapsed = time.time() - t0
    result["_runtime"] = round(elapsed, 1)
    return result


def format_case(r: dict) -> str:
    """Format a single case result as a compact line."""
    symbol = r.get("symbol", r.get("case_id", "???"))
    bot_pnl = r.get("total_pnl", r.get("bot_pnl", 0)) or 0
    ross_pnl = r.get("ross_pnl", 0) or 0
    delta = r.get("delta", bot_pnl - ross_pnl) or 0
    entry_time = r.get("entry_time", "-")
    exit_time = r.get("exit_time", "-")
    direction = r.get("direction", "-")
    date = r.get("date", "")

    label = f"{symbol} {date}" if date else symbol

    # Color coding for delta
    if delta > 0:
        marker = "+"
    elif delta < 0:
        marker = ""
    else:
        marker = " "

    return f"  {label:<18s} | Bot: ${bot_pnl:>10,.2f} | Ross: ${ross_pnl:>10,.2f} | Delta: ${marker}{delta:>10,.2f} | {direction or '-':<5s} | {entry_time or '-'} -> {exit_time or '-'}"


def print_results(data: dict):
    """Print formatted results table."""
    results = data.get("results", [])
    summary = data.get("summary", {})
    runtime = data.get("_runtime", 0)

    # Sort by delta (worst first)
    results_sorted = sorted(results, key=lambda r: (r.get("total_pnl", r.get("bot_pnl", 0)) or 0) - (r.get("ross_pnl", 0) or 0))

    print(f"\n{'='*96}")
    print(f"  Cases: {len(results)} | Runtime: {runtime}s")
    print(f"{'='*96}")
    print(f"  {'Case':<18s} | {'Bot P&L':>14s} | {'Ross P&L':>14s} | {'Delta':>14s} | {'Dir':<5s} | Entry -> Exit")
    print(f"  {'-'*18}-+-{'-'*14}-+-{'-'*14}-+-{'-'*14}-+-{'-'*5}-+-{'-'*20}")

    for r in results_sorted:
        print(format_case(r))

    total_bot = summary.get("total_pnl", 0) or 0
    total_ross = summary.get("total_ross_pnl", 0) or 0
    total_delta = total_bot - total_ross
    winners = summary.get("cases_profitable", 0) or 0
    capture = (total_bot / total_ross * 100) if total_ross else 0

    print(f"  {'-'*18}-+-{'-'*14}-+-{'-'*14}-+-{'-'*14}-+-{'-'*5}-+-{'-'*20}")
    print(f"  {'TOTAL':<18s} | Bot: ${total_bot:>10,.2f} | Ross: ${total_ross:>10,.2f} | Delta: ${total_delta:>10,.2f} | {winners}W   | {capture:.1f}% capture")
    print(f"{'='*96}\n")


def diff_results(current: dict, baseline: dict):
    """Show per-case diff between current run and baseline."""
    current_map = {r["case_id"]: r for r in current.get("results", [])}
    baseline_map = {r["case_id"]: r for r in baseline.get("results", [])}

    all_ids = sorted(set(list(current_map.keys()) + list(baseline_map.keys())))

    # Compute stats first
    improved = 0
    regressed = 0
    unchanged = 0
    total_change = 0
    new_total_pnl = 0
    new_total_ross = 0
    changed_cases = []

    for cid in all_ids:
        old = baseline_map.get(cid, {})
        new = current_map.get(cid, {})

        old_pnl = old.get("total_pnl", old.get("bot_pnl", 0)) or 0
        new_pnl = new.get("total_pnl", new.get("bot_pnl", 0)) or 0
        ross_pnl = new.get("ross_pnl", 0) or 0
        change = new_pnl - old_pnl
        total_change += change
        new_total_pnl += new_pnl
        new_total_ross += ross_pnl

        if abs(change) < 0.01:
            unchanged += 1
        elif change > 0:
            improved += 1
            changed_cases.append((cid, old_pnl, new_pnl, change, "IMPROVED"))
        else:
            regressed += 1
            changed_cases.append((cid, old_pnl, new_pnl, change, "REGRESSED"))

    total = improved + regressed + unchanged
    capture = (new_total_pnl / new_total_ross * 100) if new_total_ross else 0

    # Get baseline timestamp
    baseline_ts = baseline.get("saved_at", "unknown")

    # Print SUMMARY FIRST (so GC always sees it before truncation)
    print(f"\n{'='*80}")
    print(f"  DIFF vs BASELINE ({total} cases)")
    print(f"  Baseline saved: {baseline_ts}")
    print(f"{'='*80}")
    print(f"  Improved:  {improved}/{total}")
    print(f"  Regressed: {regressed}/{total}")
    print(f"  Unchanged: {unchanged}/{total}")
    print(f"  Net change:  ${total_change:>+,.2f}")
    print(f"  New total P&L: ${new_total_pnl:>,.2f}  (Ross: ${new_total_ross:>,.2f})")
    print(f"  Capture: {capture:.1f}%")
    print(f"{'='*80}")

    # Then show per-case changes (sorted by impact)
    if changed_cases:
        changed_cases.sort(key=lambda x: x[3])  # worst first
        print(f"  {'Case':<30s} | {'Old P&L':>12s} | {'New P&L':>12s} | {'Change':>12s}")
        print(f"  {'-'*30}-+-{'-'*12}-+-{'-'*12}-+-{'-'*12}")
        for cid, old_pnl, new_pnl, change, status in changed_cases:
            marker = "+" if status == "IMPROVED" else "-"
            print(f"  {marker} {cid:<28s} | ${old_pnl:>10,.2f} | ${new_pnl:>10,.2f} | ${change:>+10,.2f}")
    print()


def save_baseline(data: dict):
    """Save current results as baseline for future diffs."""
    os.makedirs(os.path.dirname(BASELINE_FILE), exist_ok=True)
    from datetime import datetime
    data["saved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(BASELINE_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  [Saved baseline to {BASELINE_FILE}]")
    # Auto-write to GC's persistent memory
    try:
        write_benchmark_memory(data)
        print(f"  [Updated GC memory: wb-benchmark.md]")
    except Exception as e:
        print(f"  [WARNING: Failed to update GC memory: {e}]")


def load_baseline() -> dict | None:
    """Load saved baseline if it exists."""
    if os.path.exists(BASELINE_FILE):
        with open(BASELINE_FILE, "r") as f:
            return json.load(f)
    return None


def main():
    parser = argparse.ArgumentParser(description="GC Quick Test — fast single-case or filtered batch test")
    parser.add_argument("cases", nargs="*", help="Case IDs or symbols (e.g., BATL, ross_batl_20260127)")
    parser.add_argument("--all", action="store_true", help="Run all cases")
    parser.add_argument("--diff", action="store_true", help="Diff results against saved baseline")
    parser.add_argument("--save", action="store_true", help="Save results as new baseline")
    parser.add_argument("--last", action="store_true", help="Use cached results from last run (skip re-running)")
    parser.add_argument("--trades", action="store_true", help="Include per-trade details")
    parser.add_argument("--list", action="store_true", help="List all available test cases")
    parser.add_argument("--json", action="store_true", help="Output JSON (for GC/automation)")
    args = parser.parse_args()

    if args.list:
        if args.json:
            data = fetch_json(f"{BASE_URL}/warrior/sim/test_cases")
            print(json.dumps(data, indent=2))
        else:
            list_cases()
        sys.exit(0)

    if not args.cases and not args.all:
        parser.print_help()
        print("\nExamples:")
        print("  python scripts/gc_quick_test.py BATL              # Run one case (by symbol)")
        print("  python scripts/gc_quick_test.py BATL MLEC GRI     # Run specific cases")
        print("  python scripts/gc_quick_test.py --all --save       # Run all + save baseline")
        print("  python scripts/gc_quick_test.py --all --diff       # Run all + diff vs baseline")
        print("  python scripts/gc_quick_test.py --list             # List all test case IDs")
        print("  python scripts/gc_quick_test.py --all --json       # JSON output (for GC)")
        sys.exit(0)

    # Resolve symbol shorthands to full case IDs
    case_ids = None
    if args.cases:
        case_ids = resolve_case_ids(args.cases)
        if not case_ids:
            if args.json:
                print(json.dumps({"error": "No valid case IDs resolved"}))
            else:
                print("  ERROR: No valid case IDs resolved. Use --list to see available cases.")
            sys.exit(1)
        label = ", ".join(case_ids)
    else:
        label = "ALL"

    # Use cached results if --last flag
    if args.last:
        if os.path.exists(LAST_RUN_FILE):
            with open(LAST_RUN_FILE, "r") as f:
                data = json.load(f)
            if not args.json:
                print(f"\n  Using cached results from last run")
        else:
            print("  ERROR: No cached results found. Run without --last first.")
            sys.exit(1)
    else:
        if not args.json:
            print(f"\n  Running: {label} ...")
        data = run_cases(case_ids, include_trades=args.trades)
        # Cache results for --last
        os.makedirs(os.path.dirname(LAST_RUN_FILE), exist_ok=True)
        with open(LAST_RUN_FILE, "w") as f:
            json.dump(data, f, indent=2)
        # Auto-write to GC's persistent memory on every run
        try:
            write_benchmark_memory(data)
        except Exception:
            pass  # Non-critical

    # Build JSON output
    if args.json:
        output = {
            "runtime": data.get("_runtime", 0),
            "summary": data.get("summary", {}),
            "cases": []
        }
        for r in data.get("results", []):
            output["cases"].append({
                "case_id": r.get("case_id"),
                "symbol": r.get("symbol"),
                "date": r.get("date"),
                "bot_pnl": r.get("total_pnl", 0) or 0,
                "ross_pnl": r.get("ross_pnl", 0) or 0,
                "delta": r.get("delta", 0) or 0,
                "entry_time": r.get("entry_time"),
                "exit_time": r.get("exit_time"),
                "direction": r.get("direction"),
                "guard_blocks": r.get("guard_blocks", []),
            })

        # Add diff if requested
        if args.diff:
            baseline = load_baseline()
            if baseline:
                baseline_map = {r["case_id"]: r for r in baseline.get("results", [])}
                diff = {"improved": [], "regressed": [], "unchanged": []}
                for c in output["cases"]:
                    old = baseline_map.get(c["case_id"], {})
                    old_pnl = old.get("total_pnl", old.get("bot_pnl", 0)) or 0
                    change = c["bot_pnl"] - old_pnl
                    entry = {"case_id": c["case_id"], "symbol": c["symbol"],
                             "old_pnl": old_pnl, "new_pnl": c["bot_pnl"], "change": round(change, 2)}
                    if abs(change) < 0.01:
                        diff["unchanged"].append(entry)
                    elif change > 0:
                        diff["improved"].append(entry)
                    else:
                        diff["regressed"].append(entry)
                output["diff"] = diff
                output["diff_summary"] = {
                    "improved": len(diff["improved"]),
                    "regressed": len(diff["regressed"]),
                    "unchanged": len(diff["unchanged"]),
                    "total_change": round(sum(e["change"] for e in diff["improved"] + diff["regressed"]), 2)
                }
            else:
                output["diff"] = None
                output["diff_summary"] = {"error": "No baseline found. Run with --save first."}

        print(json.dumps(output, indent=2))

    # Save baseline (works with both --json and non-JSON)
    if args.save:
        save_baseline(data)

    # Display: diff mode = compact summary only; normal = full table
    if not args.json and args.diff:
        baseline = load_baseline()
        if baseline:
            diff_results(data, baseline)
        else:
            print("  [No baseline found. Run with --save first to create one.]")
    elif not args.json:
        print_results(data)


if __name__ == "__main__":
    main()

