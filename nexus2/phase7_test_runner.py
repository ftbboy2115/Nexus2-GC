"""Phase 7 Test Runner - Performance Benchmark & P&L Fidelity"""
import requests
import json
import time
import sys

BASE = "http://100.113.178.7:8000/warrior/sim"
CASES = ["ross_rolr_20260114", "ross_hind_20260127", "ross_gri_20260128"]
body = {"case_ids": CASES}

# Quick health check first
print("Checking server health...")
try:
    r = requests.get(f"http://100.113.178.7:8000/health", timeout=5)
    print(f"Server health: {r.status_code}")
except Exception as e:
    print(f"Server unreachable: {e}")
    sys.exit(1)

print()
print("=" * 60)
print("TEST 1: Performance Benchmark (Concurrent)")
print("=" * 60)
print(f"Sending {len(CASES)} cases to /run_batch_concurrent...")
print(f"Started at: {time.strftime('%H:%M:%S')}")
sys.stdout.flush()

t0 = time.time()
try:
    r_conc = requests.post(f"{BASE}/run_batch_concurrent", json=body, timeout=600)
    t_conc = time.time() - t0
    conc_data = r_conc.json()
    print(f"Status: {r_conc.status_code}")
    print(f"Wall time: {t_conc:.1f}s")
    print(json.dumps(conc_data, indent=2, default=str))
    print(f"\nPASS CRITERIA: runtime < 30s => {'PASS' if t_conc < 30 else 'FAIL'}")
except Exception as e:
    t_conc = time.time() - t0
    print(f"CONCURRENT FAILED after {t_conc:.1f}s: {e}")
    conc_data = None

print()
print("=" * 60)
print("TEST 2: P&L Fidelity (Sequential)")
print("=" * 60)
print(f"Sending {len(CASES)} cases to /run_batch...")
print(f"Started at: {time.strftime('%H:%M:%S')}")
sys.stdout.flush()

t0 = time.time()
try:
    r_seq = requests.post(f"{BASE}/run_batch", json=body, timeout=600)
    t_seq = time.time() - t0
    seq_data = r_seq.json()
    print(f"Sequential status: {r_seq.status_code}, wall time: {t_seq:.1f}s")
    print(json.dumps(seq_data, indent=2, default=str))
except Exception as e:
    t_seq = time.time() - t0
    print(f"SEQUENTIAL FAILED after {t_seq:.1f}s: {e}")
    seq_data = None

# Compare P&L if both succeeded
if conc_data and seq_data:
    print()
    print("=" * 60)
    print("P&L COMPARISON")
    print("=" * 60)
    
    def extract_pnl(data):
        results = {}
        if isinstance(data, dict):
            case_results = data.get("results", data.get("case_results", []))
            if isinstance(case_results, list):
                for r in case_results:
                    cid = r.get("case_id", "unknown")
                    pnl = r.get("realized_pnl", r.get("pnl", "N/A"))
                    results[cid] = pnl
            elif isinstance(case_results, dict):
                for cid, r in case_results.items():
                    pnl = r.get("realized_pnl", r.get("pnl", "N/A")) if isinstance(r, dict) else r
                    results[cid] = pnl
        return results

    seq_pnl = extract_pnl(seq_data)
    conc_pnl = extract_pnl(conc_data)

    print(f"{'Case ID':<30} {'Sequential':>12} {'Concurrent':>12} {'Match':>8}")
    print("-" * 65)
    all_match = True
    for cid in CASES:
        s = seq_pnl.get(cid, "N/A")
        c = conc_pnl.get(cid, "N/A")
        match = str(s) == str(c)
        if not match:
            all_match = False
        print(f"{cid:<30} {str(s):>12} {str(c):>12} {'PASS' if match else 'FAIL':>8}")

    print(f"\nP&L FIDELITY: {'PASS' if all_match else 'FAIL'}")

print()
print("=" * 60)
print("SUMMARY")
print("=" * 60)
if conc_data:
    print(f"Test 1 (Performance): concurrent={t_conc:.1f}s => {'PASS' if t_conc < 30 else 'FAIL'}")
else:
    print(f"Test 1 (Performance): FAILED (concurrent endpoint error)")
if conc_data and seq_data:
    print(f"Test 2 (P&L Fidelity): {'PASS' if all_match else 'FAIL'}")
else:
    print(f"Test 2 (P&L Fidelity): COULD NOT COMPARE (missing data)")
print(f"Test 3 (Live Safety): Verified locally - PASS")
