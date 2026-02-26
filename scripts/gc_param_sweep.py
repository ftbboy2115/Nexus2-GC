"""
GC Parameter Sweep — Test multiple values for any setting and compare results.

Usage:
  python scripts/gc_param_sweep.py max_reentry_after_loss 1 2 3 5
  python scripts/gc_param_sweep.py macd_histogram_tolerance -0.02 -0.10 -1.0
  python scripts/gc_param_sweep.py micro_pullback_min_dip 0.3 0.5 1.0 --cases BATL AAPL

Runs a full batch test for each value, then outputs a comparison matrix.

Supports BOTH engine config settings (e.g. macd_histogram_tolerance) and
monitor settings (e.g. enable_profit_check_guard). Auto-detects which
endpoint owns the setting, or you can force with --type config|monitor.

Config overrides are passed directly in the batch request payload via
config_overrides, which bypasses disk-persistence race conditions and
ensures each sim engine receives the exact sweep value.
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
REPORT_DIR = os.path.join(NEXUS_PATH, "nexus2", "reports", "gc_diagnostics")

# Known engine config fields (WarriorEngineConfig dataclass fields)
# These go to PUT /warrior/config and also as config_overrides in batch
ENGINE_CONFIG_FIELDS = {
    "max_positions", "max_daily_loss", "risk_per_trade", "max_capital",
    "max_candidates", "scanner_interval_minutes", "orb_enabled", "pmh_enabled",
    "max_shares_per_trade", "max_value_per_trade", "entry_bar_timeframe",
    "macd_histogram_tolerance", "micro_pullback_enabled", "extension_threshold",
    "micro_pullback_min_dip", "micro_pullback_max_dip", "micro_pullback_macd_tolerance",
    "dip_for_level_enabled", "pullback_enabled", "bull_flag_enabled",
    "level_proximity_cents", "level_granularity", "require_macd_positive",
    "vwap_break_enabled", "inverted_hs_enabled", "abcd_enabled", "cup_handle_enabled",
    "whole_half_anticipatory_enabled", "hod_break_enabled", "top_x_picks",
    "min_entry_score", "max_entry_spread_percent",
    "static_blacklist", "max_stop_pct",
}


def fetch_json(url: str, method: str = "GET", body: dict | None = None, timeout: int = 600) -> dict:
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"} if body else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def detect_setting_type(key: str) -> str:
    """Auto-detect whether a setting belongs to engine config or monitor settings."""
    if key in ENGINE_CONFIG_FIELDS:
        return "config"
    return "monitor"


def get_current_settings(setting_type: str) -> dict:
    """Fetch current settings from the appropriate endpoint."""
    if setting_type == "config":
        # Engine config endpoint returns current_config inside response
        result = fetch_json(f"{BASE_URL}/warrior/status")
        return result.get("config", result)
    else:
        return fetch_json(f"{BASE_URL}/warrior/monitor/settings")


def update_setting(key: str, value, setting_type: str) -> dict:
    """Update a single setting via the appropriate PUT endpoint."""
    if setting_type == "config":
        return fetch_json(
            f"{BASE_URL}/warrior/config",
            method="PUT",
            body={key: value}
        )
    else:
        return fetch_json(
            f"{BASE_URL}/warrior/monitor/settings",
            method="PUT",
            body={key: value}
        )


def run_batch(case_ids: list[str] | None = None, config_overrides: dict | None = None, monitor_overrides: dict | None = None) -> dict:
    """Run batch test and return results.
    
    Args:
        case_ids: Optional list of specific case IDs to run
        config_overrides: Engine config overrides passed directly to each sim engine
        monitor_overrides: Monitor settings overrides passed directly to each sim engine's monitor
    """
    body: dict = {"include_trades": False}
    if case_ids:
        body["case_ids"] = case_ids
    if config_overrides:
        body["config_overrides"] = config_overrides
    if monitor_overrides:
        body["monitor_overrides"] = monitor_overrides
    return fetch_json(f"{BASE_URL}/warrior/sim/run_batch_concurrent", method="POST", body=body)


def parse_value(val_str: str):
    """Parse a string value to int/float/bool as appropriate."""
    if val_str.lower() in ("true", "false"):
        return val_str.lower() == "true"
    try:
        if "." in val_str:
            return float(val_str)
        return int(val_str)
    except ValueError:
        return val_str


def main():
    parser = argparse.ArgumentParser(description="GC Parameter Sweep — test multiple values for any setting")
    parser.add_argument("setting", help="Setting name (e.g., macd_histogram_tolerance, max_reentry_after_loss)")
    parser.add_argument("values", nargs="+", help="Values to test")
    parser.add_argument("--cases", nargs="*", help="Specific case IDs to run (default: all)")
    parser.add_argument("--json", action="store_true", help="Output JSON (for GC/automation)")
    parser.add_argument("--type", choices=["config", "monitor"], default=None,
                        help="Force setting type (auto-detected if not specified)")
    args = parser.parse_args()

    setting_name = args.setting
    values = [parse_value(v) for v in args.values]
    case_ids = args.cases if args.cases else None
    json_mode = args.json

    # Detect setting type
    setting_type = args.type or detect_setting_type(setting_name)

    # Save original setting value
    try:
        original_settings = get_current_settings(setting_type)
        original_value = original_settings.get(setting_name)
        
        # Fallback: if API returns None, read from persistence file
        if original_value is None and setting_type == "config":
            settings_file = os.path.join(NEXUS_PATH, "data", "warrior_settings.json")
            if os.path.exists(settings_file):
                with open(settings_file) as f:
                    persisted = json.load(f)
                original_value = persisted.get(setting_name)
        
        if not json_mode:
            print(f"\n  Setting: {setting_name} (type: {setting_type})")
            print(f"  Original value: {original_value}")
            print(f"  Testing values: {values}")
            if case_ids:
                print(f"  Cases: {', '.join(case_ids)}")
            print()
    except Exception as e:
        if json_mode:
            print(json.dumps({"error": f"Could not fetch settings: {e}"}))
        else:
            print(f"  ERROR: Could not fetch settings: {e}")
        sys.exit(1)

    # Run sweep
    results = []
    for val in values:
        if not json_mode:
            sep = "=" * 60
            print(sep)
            print(f"  Testing {setting_name} = {val}")
            print(sep)

        # Update the persistent setting (so it's readable via GET)
        try:
            update_setting(setting_name, val, setting_type)
        except Exception as e:
            if not json_mode:
                print(f"  ERROR: Could not set {setting_name}={val}: {e}")
            results.append({"value": val, "error": str(e)})
            continue

        # Build config_overrides or monitor_overrides based on setting type
        # This bypasses disk-persistence race conditions by passing
        # the value directly to each sim engine in the batch
        config_overrides = None
        monitor_overrides = None
        if setting_type == "config":
            config_overrides = {setting_name: val}
        else:
            monitor_overrides = {setting_name: val}

        t0 = time.time()
        try:
            data = run_batch(case_ids, config_overrides=config_overrides, monitor_overrides=monitor_overrides)
            elapsed = time.time() - t0
            summary = data.get("summary", {})

            total_pnl = summary.get("total_pnl", 0) or 0
            ross_pnl = summary.get("total_ross_pnl", 0) or 0
            delta = total_pnl - ross_pnl
            winners = summary.get("cases_profitable", 0) or 0
            capture = (total_pnl / ross_pnl * 100) if ross_pnl else 0

            results.append({
                "value": val,
                "total_pnl": total_pnl,
                "ross_pnl": ross_pnl,
                "delta": delta,
                "winners": winners,
                "capture": round(capture, 1),
                "runtime": round(elapsed, 1),
                "per_case": {r["case_id"]: r.get("total_pnl", 0) or 0 for r in data.get("results", [])},
            })

            if not json_mode:
                print(f"  P&L: ${total_pnl:,.2f} | Delta: ${delta:,.2f} | Winners: {winners} | {elapsed:.0f}s")
        except Exception as e:
            if not json_mode:
                print(f"  ERROR running batch: {e}")
            results.append({"value": val, "error": str(e)})

    # Restore original value
    if original_value is not None:
        try:
            update_setting(setting_name, original_value, setting_type)
            if not json_mode:
                print(f"\n  Restored {setting_name} to {original_value}")
        except Exception:
            if not json_mode:
                print(f"\n  WARNING: Could not restore {setting_name} to {original_value}")

    # JSON output
    if json_mode:
        # Find best value
        valid = [r for r in results if "error" not in r]
        best = max(valid, key=lambda r: r["total_pnl"]) if valid else None
        output = {
            "setting": setting_name,
            "setting_type": setting_type,
            "original_value": original_value,
            "values_tested": values,
            "results": results,
            "best_value": best["value"] if best else None,
            "best_pnl": best["total_pnl"] if best else None,
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        # Print comparison table
        print(f"\n{'='*100}")
        print(f"  PARAMETER SWEEP RESULTS: {setting_name}")
        print(f"{'='*100}")
        print(f"  {'Value':>12s} | {'Bot P&L':>14s} | {'Delta':>14s} | {'Winners':>8s} | {'Capture':>8s} | {'Time':>6s}")
        print(f"  {'-'*12}-+-{'-'*14}-+-{'-'*14}-+-{'-'*8}-+-{'-'*8}-+-{'-'*6}")

        for r in results:
            if "error" in r:
                print(f"  {str(r['value']):>12s} | ERROR: {r['error']}")
                continue
            print(
                f"  {str(r['value']):>12s} | ${r['total_pnl']:>12,.2f} | ${r['delta']:>+12,.2f} | "
                f"{r['winners']:>8d} | {r['capture']:>7.1f}% | {r['runtime']:>5.1f}s"
            )

        # Per-case diff (show cases that differ between values)
        if len(results) >= 2:
            all_case_ids = set()
            for r in results:
                if "per_case" in r:
                    all_case_ids.update(r["per_case"].keys())

            changed_cases = []
            for cid in sorted(all_case_ids):
                pnls = [r.get("per_case", {}).get(cid) for r in results if "per_case" in r]
                if len(set(p for p in pnls if p is not None)) > 1:
                    changed_cases.append(cid)

            if changed_cases:
                print(f"\n  CASES THAT CHANGED:")
                print(f"  {'Case':<12s} | " + " | ".join(f"{str(r['value']):>12s}" for r in results if "per_case" in r))
                print(f"  {'-'*12}-+-" + "-+-".join(f"{'-'*12}" for r in results if "per_case" in r))
                for cid in changed_cases:
                    vals = [f"${r.get('per_case', {}).get(cid, 0):>10,.2f}" for r in results if "per_case" in r]
                    print(f"  {cid:<12s} | " + " | ".join(vals))
            else:
                print(f"\n  No per-case differences detected across values.")

        print()

    # Save results
    os.makedirs(REPORT_DIR, exist_ok=True)
    outfile = os.path.join(REPORT_DIR, f"sweep_{setting_name}.json")
    with open(outfile, "w") as f:
        json.dump({"setting": setting_name, "setting_type": setting_type, "values": [str(v) for v in values], "results": results}, f, indent=2, default=str)
    if not json_mode:
        print(f"  Results saved to {outfile}\n")


if __name__ == "__main__":
    main()
