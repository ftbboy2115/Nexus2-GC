"""
A/B Test: Scaling Variants for Warrior Bot

Runs 5 scaling variants back-to-back and compares P&L:
1. no_scale        — All scaling disabled
2. baseline        — Current accidental 1-scale behavior (enable_improved_scaling=False)
3. momentum_only   — Only momentum adds (new feature)
4. pullback_only   — Improved pullback scaling only
5. combined        — Both pullback + momentum adds

Usage:
  python scripts/ab_test_scaling.py           # Run all 5 variants
  python scripts/ab_test_scaling.py --quick   # Run only 2 variants (baseline + momentum_only)
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import argparse

# Fix Windows encoding
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
except (AttributeError, TypeError):
    pass

import urllib.request

BASE_URL = "http://127.0.0.1:8000"


def fetch_json(url: str, method: str = "GET", body: dict | None = None, timeout: int = 600) -> dict:
    """Make HTTP request and return JSON response."""
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def get_current_settings() -> dict:
    """Get current monitor settings (to restore after test)."""
    return fetch_json(f"{BASE_URL}/warrior/monitor/settings")


def set_settings(overrides: dict) -> dict:
    """Update monitor settings with overrides."""
    return fetch_json(f"{BASE_URL}/warrior/monitor/settings", method="PUT", body=overrides)


def run_batch() -> dict:
    """Run full batch test (concurrent)."""
    return fetch_json(f"{BASE_URL}/warrior/sim/run_batch_concurrent", method="POST", body={})


# =============================================================================
# VARIANT DEFINITIONS
# =============================================================================

VARIANTS = {
    "no_scale": {
        "description": "All scaling disabled",
        "settings": {
            "enable_scaling": False,
            "enable_momentum_adds": False,
        },
    },
    "baseline": {
        "description": "Current accidental 1-scale (enable_improved_scaling=False)",
        "settings": {
            "enable_scaling": True,
            "enable_improved_scaling": False,
            "enable_momentum_adds": False,
        },
    },
    "momentum_only": {
        "description": "Only momentum adds (new feature)",
        "settings": {
            "enable_scaling": False,
            "enable_momentum_adds": True,
            "momentum_add_interval": 1.0,
            "momentum_add_size_pct": 50,
            "max_momentum_adds": 3,
        },
    },
    "pullback_only": {
        "description": "Improved pullback scaling only",
        "settings": {
            "enable_scaling": True,
            "enable_improved_scaling": True,
            "enable_momentum_adds": False,
        },
    },
    "combined": {
        "description": "Both pullback + momentum adds",
        "settings": {
            "enable_scaling": True,
            "enable_improved_scaling": True,
            "enable_momentum_adds": True,
            "momentum_add_interval": 1.0,
            "momentum_add_size_pct": 50,
            "max_momentum_adds": 3,
        },
    },
}


def run_variant(name: str, variant: dict) -> dict:
    """Run a single variant and return results with timing."""
    print(f"\n  [{name}] Setting overrides: {variant['settings']}")
    set_settings(variant["settings"])

    print(f"  [{name}] Running batch test...")
    t0 = time.time()
    result = run_batch()
    elapsed = round(time.time() - t0, 1)

    summary = result.get("summary", {})
    total_pnl = summary.get("total_pnl", 0) or 0
    total_ross = summary.get("total_ross_pnl", 0) or 0
    capture = (total_pnl / total_ross * 100) if total_ross else 0

    print(f"  [{name}] Done in {elapsed}s — Bot P&L: ${total_pnl:,.2f} ({capture:.1f}% capture)")

    return {
        "name": name,
        "description": variant["description"],
        "total_pnl": total_pnl,
        "total_ross": total_ross,
        "capture": capture,
        "runtime": elapsed,
        "cases": result.get("results", []),
        "summary": summary,
    }


def print_comparison(results: list[dict]):
    """Print comparison table across all variants."""
    # Find baseline for delta calculation
    baseline_pnl = 0
    for r in results:
        if r["name"] == "baseline":
            baseline_pnl = r["total_pnl"]
            break

    print(f"\n{'='*95}")
    print(f"  SCALING A/B TEST RESULTS")
    print(f"{'='*95}")
    print(f"  {'Variant':<18s} | {'Bot P&L':>12s} | {'Capture':>8s} | {'Delta vs Baseline':>18s} | {'Runtime':>8s}")
    print(f"  {'-'*18}-+-{'-'*12}-+-{'-'*8}-+-{'-'*18}-+-{'-'*8}")

    for r in results:
        delta = r["total_pnl"] - baseline_pnl
        delta_str = f"${delta:>+,.2f}" if r["name"] != "baseline" else "—"
        print(
            f"  {r['name']:<18s} | ${r['total_pnl']:>10,.2f} | {r['capture']:>6.1f}% | {delta_str:>18s} | {r['runtime']:>6.1f}s"
        )

    print(f"{'='*95}")


def print_regressions(results: list[dict]):
    """Print per-case regressions (cases where variant P&L < baseline)."""
    # Build baseline case map
    baseline_map = {}
    for r in results:
        if r["name"] == "baseline":
            for case in r["cases"]:
                case_id = case.get("case_id", "")
                baseline_map[case_id] = case.get("total_pnl", case.get("bot_pnl", 0)) or 0
            break

    if not baseline_map:
        print("\n  [No baseline found for regression analysis]")
        return

    has_regressions = False
    for r in results:
        if r["name"] == "baseline":
            continue

        regressions = []
        for case in r["cases"]:
            case_id = case.get("case_id", "")
            variant_pnl = case.get("total_pnl", case.get("bot_pnl", 0)) or 0
            baseline_pnl = baseline_map.get(case_id, 0)
            delta = variant_pnl - baseline_pnl
            if delta < -0.01:
                regressions.append({
                    "case_id": case_id,
                    "symbol": case.get("symbol", "?"),
                    "baseline_pnl": baseline_pnl,
                    "variant_pnl": variant_pnl,
                    "delta": delta,
                })

        if regressions:
            has_regressions = True
            regressions.sort(key=lambda x: x["delta"])
            print(f"\n  Regressions in [{r['name']}] ({len(regressions)} cases):")
            print(f"    {'Case':<30s} | {'Baseline':>10s} | {'Variant':>10s} | {'Delta':>10s}")
            print(f"    {'-'*30}-+-{'-'*10}-+-{'-'*10}-+-{'-'*10}")
            for reg in regressions:
                print(
                    f"    {reg['case_id']:<30s} | ${reg['baseline_pnl']:>8,.2f} | "
                    f"${reg['variant_pnl']:>8,.2f} | ${reg['delta']:>+8,.2f}"
                )

    if not has_regressions:
        print("\n  No regressions found across any variant!")


def save_report(results: list[dict], filepath: str):
    """Save JSON results for later analysis."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "variants": results,
    }
    with open(filepath, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  [Saved JSON report to {filepath}]")


def main():
    parser = argparse.ArgumentParser(description="A/B test scaling variants for Warrior bot")
    parser.add_argument("--quick", action="store_true", help="Run only baseline + momentum_only")
    parser.add_argument("--variants", nargs="*", help="Specific variants to run (e.g., baseline momentum_only)")
    parser.add_argument("--save", type=str, default=None, help="Save JSON report to file")
    args = parser.parse_args()

    # Determine which variants to run
    if args.variants:
        variant_names = args.variants
        for v in variant_names:
            if v not in VARIANTS:
                print(f"  ERROR: Unknown variant '{v}'. Available: {list(VARIANTS.keys())}")
                sys.exit(1)
    elif args.quick:
        variant_names = ["baseline", "momentum_only"]
    else:
        variant_names = list(VARIANTS.keys())

    print(f"\n  A/B Test: Scaling Variants")
    print(f"  Variants: {', '.join(variant_names)}")
    print(f"  Server: {BASE_URL}")

    # Save original settings to restore later
    print(f"\n  Saving original settings...")
    try:
        original_settings = get_current_settings()
    except Exception as e:
        print(f"  ERROR: Cannot connect to server at {BASE_URL}: {e}")
        print(f"  Make sure the Nexus server is running.")
        sys.exit(1)

    results = []
    total_t0 = time.time()

    try:
        for name in variant_names:
            variant = VARIANTS[name]
            result = run_variant(name, variant)
            results.append(result)

    finally:
        # ALWAYS restore original settings, even on error/interrupt
        print(f"\n  Restoring original settings...")
        try:
            # Only restore the fields we may have changed
            restore = {
                "enable_scaling": original_settings.get("enable_scaling"),
                "enable_improved_scaling": original_settings.get("enable_improved_scaling", False),
                "enable_momentum_adds": original_settings.get("enable_momentum_adds", False),
                "momentum_add_interval": original_settings.get("momentum_add_interval", 1.0),
                "momentum_add_size_pct": original_settings.get("momentum_add_size_pct", 50),
                "max_momentum_adds": original_settings.get("max_momentum_adds", 3),
            }
            set_settings(restore)
            print(f"  Settings restored.")
        except Exception as e:
            print(f"  WARNING: Failed to restore settings: {e}")

    total_elapsed = round(time.time() - total_t0, 1)
    print(f"\n  Total A/B test time: {total_elapsed}s")

    # Print results
    if results:
        print_comparison(results)
        print_regressions(results)

    # Save report
    if args.save:
        save_report(results, args.save)
    else:
        # Default save location
        default_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "nexus2", "reports", "gc_diagnostics", "ab_test_scaling_latest.json",
        )
        save_report(results, default_path)


if __name__ == "__main__":
    main()
