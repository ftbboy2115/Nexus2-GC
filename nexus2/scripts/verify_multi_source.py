"""
Multi-source data verification for test cases.

Cross-references FMP intraday data with Alpaca to verify accuracy.
This helps catch FMP ticker collision issues.
"""
import os
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
import httpx

# Load .env
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

fmp_key = os.getenv("FMP_API_KEY")
alpaca_key = os.getenv("APCA_API_KEY_ID")
alpaca_secret = os.getenv("APCA_API_SECRET_KEY")

# Test cases to verify
TEST_CASES = [
    ("CMCT", "2025-12-22"),  # Ross's verified $10K day
    ("OPTX", "2026-01-06"),  # Ross traded
    ("ACON", "2026-01-08"),  # High volume gapper
    ("FLYX", "2026-01-08"),  # Starlink news
]


def get_fmp_day_stats(symbol: str, date: str) -> dict:
    """Get O/H/L/C from FMP intraday."""
    url = f"https://financialmodelingprep.com/api/v3/historical-chart/1min/{symbol}?from={date}&to={date}&apikey={fmp_key}"
    resp = httpx.get(url, timeout=30)
    data = resp.json()
    
    if not isinstance(data, list) or len(data) == 0:
        return {"source": "fmp", "error": "no_data"}
    
    # FMP returns newest first
    candles = list(reversed(data))
    return {
        "source": "fmp",
        "open": candles[0]["open"],
        "high": max(c["high"] for c in candles),
        "low": min(c["low"] for c in candles),
        "close": candles[-1]["close"],
        "volume": sum(c["volume"] for c in candles),
        "candles": len(candles),
    }


def get_alpaca_day_stats(symbol: str, date: str) -> dict:
    """Get O/H/L/C from Alpaca historical bars."""
    # Alpaca uses RFC3339 format
    start = f"{date}T09:30:00Z"
    # Add one day for end date
    next_day = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    end = f"{next_day}T00:00:00Z"
    
    url = f"https://data.alpaca.markets/v2/stocks/{symbol}/bars"
    params = {
        "timeframe": "1Day",
        "start": date,
        "end": next_day,
        "adjustment": "raw",
    }
    headers = {
        "APCA-API-KEY-ID": alpaca_key,
        "APCA-API-SECRET-KEY": alpaca_secret,
    }
    
    try:
        resp = httpx.get(url, params=params, headers=headers, timeout=30)
        data = resp.json()
        
        if "bars" not in data or len(data["bars"]) == 0:
            return {"source": "alpaca", "error": "no_data"}
        
        bar = data["bars"][0]
        return {
            "source": "alpaca",
            "open": bar["o"],
            "high": bar["h"],
            "low": bar["l"],
            "close": bar["c"],
            "volume": bar["v"],
        }
    except Exception as e:
        return {"source": "alpaca", "error": str(e)}


def compare_sources(fmp: dict, alpaca: dict, symbol: str) -> str:
    """Compare FMP and Alpaca data, return status."""
    if "error" in fmp:
        return f"FMP: {fmp['error']}"
    if "error" in alpaca:
        return f"Alpaca: {alpaca['error']}"
    
    # Compare prices (allow 2% tolerance for slight differences)
    tolerance = 0.02
    
    def pct_diff(a, b):
        if b == 0:
            return 999
        return abs(a - b) / b
    
    open_diff = pct_diff(fmp["open"], alpaca["open"])
    high_diff = pct_diff(fmp["high"], alpaca["high"])
    low_diff = pct_diff(fmp["low"], alpaca["low"])
    
    # Check for major discrepancy (>10% = likely wrong ticker)
    if open_diff > 0.10 or high_diff > 0.10 or low_diff > 0.10:
        return f"[X] MAJOR DISCREPANCY - FMP has wrong data"
    elif open_diff > tolerance or high_diff > tolerance or low_diff > tolerance:
        return f"[!] Minor difference ({max(open_diff, high_diff, low_diff)*100:.1f}%)"
    else:
        return "[OK] VERIFIED - Sources match"


print("=" * 70)
print("MULTI-SOURCE DATA VERIFICATION")
print("Comparing FMP vs Alpaca")
print("=" * 70)

for symbol, date in TEST_CASES:
    print(f"\n{'='*50}")
    print(f"{symbol} on {date}")
    print("-" * 50)
    
    fmp_data = get_fmp_day_stats(symbol, date)
    alpaca_data = get_alpaca_day_stats(symbol, date)
    
    # Print FMP
    if "error" not in fmp_data:
        print(f"FMP:    O=${fmp_data['open']:.2f} H=${fmp_data['high']:.2f} L=${fmp_data['low']:.2f} C=${fmp_data['close']:.2f} V={fmp_data['volume']:,}")
    else:
        print(f"FMP:    {fmp_data['error']}")
    
    # Print Alpaca
    if "error" not in alpaca_data:
        print(f"Alpaca: O=${alpaca_data['open']:.2f} H=${alpaca_data['high']:.2f} L=${alpaca_data['low']:.2f} C=${alpaca_data['close']:.2f} V={alpaca_data['volume']:,}")
    else:
        print(f"Alpaca: {alpaca_data['error']}")
    
    # Comparison
    status = compare_sources(fmp_data, alpaca_data, symbol)
    print(f"Status: {status}")

print("\n" + "=" * 70)
print("VERIFICATION COMPLETE")
print("=" * 70)

# Save results to file for review
output_file = Path(__file__).parent.parent.parent / "data" / "verification_results.txt"
with open(output_file, "w") as f:
    f.write("MULTI-SOURCE DATA VERIFICATION RESULTS\n")
    f.write("=" * 50 + "\n\n")
    for symbol, date in TEST_CASES:
        fmp_data = get_fmp_day_stats(symbol, date)
        alpaca_data = get_alpaca_day_stats(symbol, date)
        status = compare_sources(fmp_data, alpaca_data, symbol)
        
        f.write(f"{symbol} on {date}\n")
        if "error" not in fmp_data:
            f.write(f"  FMP:    O=${fmp_data['open']:.2f} H=${fmp_data['high']:.2f} L=${fmp_data['low']:.2f} C=${fmp_data['close']:.2f}\n")
        else:
            f.write(f"  FMP:    {fmp_data['error']}\n")
        if "error" not in alpaca_data:
            f.write(f"  Alpaca: O=${alpaca_data['open']:.2f} H=${alpaca_data['high']:.2f} L=${alpaca_data['low']:.2f} C=${alpaca_data['close']:.2f}\n")
        else:
            f.write(f"  Alpaca: {alpaca_data['error']}\n")
        f.write(f"  Status: {status}\n\n")
print(f"\nResults saved to {output_file}")
