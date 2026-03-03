"""
Tech Stop Cap Parameter Sweep

Sweeps tech_stop_max_pct values [0.10, 0.15, 0.20, 0.25] by:
1. Patching the default in warrior_types.py
2. Restarting uvicorn
3. Running gc_quick_test.py --all --json --diff
4. Collecting results

Usage: python scripts/sweep_tech_stop_cap.py
"""
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.request

NEXUS_PATH = os.environ.get(
    "NEXUS_PATH",
    r"C:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus"
)
TYPES_FILE = os.path.join(NEXUS_PATH, "nexus2", "domain", "automation", "warrior_types.py")
BASE_URL = "http://127.0.0.1:8000"

CAP_VALUES = [0.10, 0.15, 0.20, 0.25]

def patch_cap_value(value: float):
    """Replace tech_stop_max_pct default in warrior_types.py."""
    with open(TYPES_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Pattern: tech_stop_max_pct: float = 0.XX
    new_content = re.sub(
        r'(tech_stop_max_pct: float = )\d+\.\d+',
        f'\\g<1>{value}',
        content,
    )
    
    with open(TYPES_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)
    print(f"  Patched tech_stop_max_pct = {value}")


def kill_server():
    """Kill any running uvicorn on port 8000."""
    try:
        # Find and kill process on port 8000
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | "
             "Select-Object -ExpandProperty OwningProcess | Sort-Object -Unique | "
             "ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"],
            capture_output=True, text=True, timeout=10
        )
        time.sleep(2)  # Wait for cleanup
        print("  Killed existing server")
    except Exception as e:
        print(f"  Kill server: {e}")


def start_server():
    """Start uvicorn in background and wait for it to be ready."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "nexus2.api.main:app",
         "--host", "0.0.0.0", "--port", "8000"],
        cwd=NEXUS_PATH,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    
    # Wait for server to be ready (max 30s)
    for i in range(30):
        try:
            req = urllib.request.Request(f"{BASE_URL}/health")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    print(f"  Server ready (PID {proc.pid})")
                    return proc
        except Exception:
            time.sleep(1)
    
    print("  WARNING: Server may not be ready after 30s")
    return proc


def run_batch_test():
    """Run gc_quick_test.py --all --json --diff and capture results."""
    result = subprocess.run(
        [sys.executable, "scripts/gc_quick_test.py", "--all", "--json", "--diff"],
        cwd=NEXUS_PATH,
        capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr[:500]}")
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"  ERROR parsing JSON: {result.stdout[:500]}")
        return None


def main():
    results = {}
    
    print(f"\n{'='*60}")
    print(f"  TECH STOP CAP PARAMETER SWEEP")
    print(f"  Values: {CAP_VALUES}")
    print(f"{'='*60}\n")
    
    for cap_value in CAP_VALUES:
        print(f"\n--- Cap = {int(cap_value*100)}% ---")
        
        # 1. Patch code
        patch_cap_value(cap_value)
        
        # 2. Restart server
        kill_server()
        proc = start_server()
        
        # 3. Run batch test
        data = run_batch_test()
        
        if data:
            summary = data.get("summary", {})
            diff_summary = data.get("diff_summary", {})
            results[f"{int(cap_value*100)}%"] = {
                "total_pnl": summary.get("total_pnl", 0),
                "total_ross": summary.get("total_ross_pnl", 0),
                "cases": summary.get("cases_run", 0),
                "profitable": summary.get("cases_profitable", 0),
                "improved": diff_summary.get("improved", 0),
                "regressed": diff_summary.get("regressed", 0),
                "net_change": diff_summary.get("total_change", 0),
                "per_case": data.get("diff", {}),
                "full_cases": data.get("cases", []),
            }
            
            pnl = summary.get("total_pnl", 0)
            change = diff_summary.get("total_change", 0)
            improved = diff_summary.get("improved", 0)
            regressed = diff_summary.get("regressed", 0)
            print(f"  P&L: ${pnl:,.2f} | Change: ${change:+,.2f} | "
                  f"Improved: {improved} | Regressed: {regressed}")
        else:
            results[f"{int(cap_value*100)}%"] = {"error": "Test failed"}
            print(f"  FAILED")
        
        # 4. Kill server for next iteration
        kill_server()
    
    # Save full results
    output_file = os.path.join(NEXUS_PATH, "nexus2", "reports", "2026-03-03", "sweep_tech_stop_cap_raw.json")
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    
    # Print summary table
    print(f"\n{'='*80}")
    print(f"  SWEEP SUMMARY")
    print(f"{'='*80}")
    print(f"  {'Cap':>6s} | {'Total P&L':>12s} | {'Net Change':>12s} | {'Improved':>8s} | {'Regressed':>9s}")
    print(f"  {'-'*6}-+-{'-'*12}-+-{'-'*12}-+-{'-'*8}-+-{'-'*9}")
    for cap_label, r in results.items():
        if "error" in r:
            print(f"  {cap_label:>6s} | {'FAILED':>12s} |")
        else:
            print(f"  {cap_label:>6s} | ${r['total_pnl']:>10,.2f} | ${r['net_change']:>+10,.2f} | "
                  f"{r['improved']:>8d} | {r['regressed']:>9d}")
    print(f"{'='*80}")
    print(f"\n  Raw results saved to: {output_file}")


if __name__ == "__main__":
    main()
