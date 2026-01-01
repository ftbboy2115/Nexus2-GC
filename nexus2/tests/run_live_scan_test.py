"""Quick script to test live HTF and Breakout scanners."""
import requests

API_BASE = "http://localhost:8000"

print("=" * 60)
print("LIVE SCANNER TEST (Market Closed - Using Historical Data)")
print("=" * 60)

# Test HTF Scanner (POST endpoint)
print("\n🔍 HTF (High Tight Flag) Scanner:")
try:
    r = requests.post(f"{API_BASE}/scanner/htf", params={"limit": 10}, timeout=60)
    if r.status_code == 200:
        data = r.json()
        candidates = data.get("candidates", [])
        print(f"   Found {len(candidates)} HTF candidates")
        for c in candidates[:5]:
            status = c.get("status", "N/A")
            score = c.get("score", 0)
            print(f"   • {c['symbol']}: {status} (score: {score})")
    else:
        print(f"   Error {r.status_code}: {r.text[:100]}")
except Exception as e:
    print(f"   Error: {e}")

# Test Breakout Scanner (POST endpoint)
print("\n🔍 Breakout Scanner:")
try:
    r = requests.post(f"{API_BASE}/scanner/breakout", params={"limit": 10}, timeout=60)
    if r.status_code == 200:
        data = r.json()
        candidates = data.get("candidates", [])
        print(f"   Found {len(candidates)} Breakout candidates")
        for c in candidates[:5]:
            status = c.get("status", "?")
            print(f"   • {c.get('symbol', '?')}: {status}")
    else:
        print(f"   Error {r.status_code}: {r.text[:100]}")
except Exception as e:
    print(f"   Error: {e}")

# Test Unified Scanner (all modes)
print("\n🔍 Unified Scanner (EP + Breakout + HTF):")
try:
    r = requests.post(f"{API_BASE}/automation/scan-all", timeout=120)
    if r.status_code == 200:
        data = r.json()
        signals = data.get("signals", [])
        print(f"   Found {len(signals)} total signals")
        print(f"   EP: {data.get('ep_count', 0)}, Breakout: {data.get('breakout_count', 0)}, HTF: {data.get('htf_count', 0)}")
        for s in signals[:5]:
            setup = s.get("setup_type", "?")
            quality = s.get("quality_score", 0)
            print(f"   • {s['symbol']}: {setup} (Q{quality})")
    else:
        print(f"   Error: {r.status_code}")
except Exception as e:
    print(f"   Error: {e}")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
