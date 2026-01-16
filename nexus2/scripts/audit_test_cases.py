"""
Fetch historical data for all Warrior test cases and generate accurate price ranges.

This replaces estimated prices with actual FMP data.
"""
import os
import yaml
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import httpx

# Load .env
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)
api_key = os.getenv("FMP_API_KEY")

# Load test cases
test_cases_path = Path(__file__).parent.parent / "tests" / "test_cases" / "warrior_setups.yaml"
with open(test_cases_path) as f:
    data = yaml.safe_load(f)

output_dir = Path(__file__).parent.parent.parent / "data" / "test_case_data"
output_dir.mkdir(parents=True, exist_ok=True)

print("=" * 70)
print("WARRIOR TEST CASE DATA AUDIT")
print("=" * 70)

audit_results = []

for case in data.get("test_cases", []):
    case_id = case.get("id", "unknown")
    symbol = case.get("symbol")
    trade_date = case.get("trade_date")
    ross_traded = case.get("ross_traded", False)
    verified = case.get("verified", False)
    synthetic = case.get("synthetic", False)
    
    if synthetic:
        print(f"\n[SKIP] {case_id}: Synthetic test case")
        continue
    
    if not symbol or not trade_date:
        print(f"\n[SKIP] {case_id}: Missing symbol or date")
        continue
    
    print(f"\n{'='*50}")
    print(f"Case: {case_id}")
    print(f"Symbol: {symbol} | Date: {trade_date}")
    print(f"Ross Traded: {ross_traded} | Verified: {verified}")
    
    # Fetch FMP data
    url = f"https://financialmodelingprep.com/api/v3/historical-chart/1min/{symbol}?from={trade_date}&to={trade_date}&apikey={api_key}"
    
    try:
        resp = httpx.get(url, timeout=30)
        candles = resp.json()
        
        if not isinstance(candles, list) or len(candles) == 0:
            print(f"  [NO DATA] FMP returned no intraday data")
            audit_results.append({
                "case_id": case_id,
                "symbol": symbol,
                "date": trade_date,
                "status": "NO_FMP_DATA",
                "ross_traded": ross_traded,
            })
            continue
        
        # FMP returns newest first, reverse
        candles = list(reversed(candles))
        
        # Calculate actual stats
        open_price = candles[0]["open"]
        high = max(c["high"] for c in candles)
        low = min(c["low"] for c in candles)
        close = candles[-1]["close"]
        volume = sum(c["volume"] for c in candles)
        
        print(f"  FMP Data: {len(candles)} candles")
        print(f"  Open: ${open_price:.2f} | High: ${high:.2f} | Low: ${low:.2f} | Close: ${close:.2f}")
        print(f"  Volume: {volume:,}")
        
        # Compare to test case expected values
        expected_entry = case.get("expected", {}).get("entry_near")
        premarket_high = case.get("premarket_data", {}).get("premarket_high")
        
        if expected_entry:
            # Find when entry price was first hit
            entry_candles = [c for c in candles if c["high"] >= expected_entry]
            if entry_candles:
                first_entry = entry_candles[0]
                print(f"  Expected entry ${expected_entry:.2f} first hit: {first_entry['date']}")
                
                # Check if entry is realistic
                if expected_entry > high:
                    print(f"  ⚠️ WARNING: Expected entry ${expected_entry:.2f} ABOVE day high ${high:.2f}")
                    status = "ENTRY_ABOVE_HIGH"
                elif expected_entry < low:
                    print(f"  ⚠️ WARNING: Expected entry ${expected_entry:.2f} BELOW day low ${low:.2f}")
                    status = "ENTRY_BELOW_LOW"
                else:
                    status = "ENTRY_IN_RANGE"
            else:
                print(f"  ⚠️ WARNING: Entry ${expected_entry:.2f} never reached")
                status = "ENTRY_NEVER_HIT"
        else:
            status = "NO_ENTRY_SPECIFIED"
        
        # Save candle data
        output_file = output_dir / f"{symbol}_{trade_date.replace('-', '')}_1min.json"
        with open(output_file, "w") as f:
            json.dump({
                "symbol": symbol,
                "date": trade_date,
                "case_id": case_id,
                "fmp_stats": {
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                    "candle_count": len(candles),
                },
                "candles": candles,
            }, f, indent=2)
        print(f"  Saved to {output_file.name}")
        
        audit_results.append({
            "case_id": case_id,
            "symbol": symbol,
            "date": trade_date,
            "status": status,
            "ross_traded": ross_traded,
            "fmp_open": open_price,
            "fmp_high": high,
            "fmp_low": low,
            "fmp_close": close,
            "expected_entry": expected_entry,
            "volume": volume,
        })
        
    except Exception as e:
        print(f"  [ERROR] {e}")
        audit_results.append({
            "case_id": case_id,
            "symbol": symbol,
            "date": trade_date,
            "status": "ERROR",
            "error": str(e),
        })

# Summary
print("\n" + "=" * 70)
print("AUDIT SUMMARY")
print("=" * 70)

for r in audit_results:
    status_icon = {
        "ENTRY_IN_RANGE": "✅",
        "ENTRY_ABOVE_HIGH": "❌",
        "ENTRY_BELOW_LOW": "❌",
        "ENTRY_NEVER_HIT": "⚠️",
        "NO_FMP_DATA": "📭",
        "NO_ENTRY_SPECIFIED": "❓",
        "ERROR": "💥",
    }.get(r["status"], "?")
    
    ross = "🎯" if r.get("ross_traded") else "  "
    print(f"{status_icon} {ross} {r['case_id']}: {r['status']}")

# Save audit results
audit_file = output_dir / "audit_results.json"
with open(audit_file, "w") as f:
    json.dump(audit_results, f, indent=2)
print(f"\nSaved audit results to {audit_file}")
