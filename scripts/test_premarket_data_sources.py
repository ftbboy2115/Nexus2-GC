"""
Query Alpha Vantage for pre-market intraday volume data.
Alpha Vantage includes extended hours (4AM-8PM ET) by default.
"""

import os
from datetime import datetime, timedelta
import requests

from dotenv import load_dotenv
load_dotenv(r"c:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus\.env")

# Alpha Vantage - check if we have a key, otherwise use FMP's aftermarket endpoint
ALPHA_VANTAGE_KEY = os.environ.get("ALPHAVANTAGE_API_KEY", os.environ.get("ALPHA_VANTAGE_API_KEY"))
FMP_API_KEY = os.environ.get("FMP_API_KEY")

# Ross's trades from transcripts (Jan 5-18, 2026)
ROSS_TRADES = [
    {"symbol": "ROLR", "date": "2026-01-14", "entry_time": "08:18", "entry_price": 5.17, "result": "$85,000"},
    {"symbol": "LCFY", "date": "2026-01-16", "entry_time": "08:00", "entry_price": 6.50, "result": "$10,000"},
    {"symbol": "GWAV", "date": "2026-01-16", "entry_time": "07:30", "entry_price": 6.50, "result": "$4,000"},
    {"symbol": "TNMG", "date": "2026-01-16", "entry_time": "07:15", "entry_price": 3.93, "result": "$2,100"},
    {"symbol": "BNKK", "date": "2026-01-15", "entry_time": "08:30", "entry_price": 4.80, "result": "$15,000"},
    {"symbol": "SPHL", "date": "2026-01-15", "entry_time": "07:01", "entry_price": 3.90, "result": "$100 (botched)"},
]


def test_alpha_vantage_intraday(symbol: str, date_str: str, entry_time: str):
    """Test Alpha Vantage intraday API with extended hours."""
    if not ALPHA_VANTAGE_KEY:
        return {"error": "No Alpha Vantage API key found"}
    
    try:
        url = "https://www.alphavantage.co/query"
        params = {
            "function": "TIME_SERIES_INTRADAY",
            "symbol": symbol,
            "interval": "5min",
            "extended_hours": "true",
            "outputsize": "full",
            "apikey": ALPHA_VANTAGE_KEY,
        }
        
        resp = requests.get(url, params=params, timeout=30)
        data = resp.json()
        
        if "Time Series (5min)" not in data:
            return {"error": f"No data: {list(data.keys())}"}
        
        # Parse entry time
        entry_hour, entry_min = map(int, entry_time.split(":"))
        
        # Count volume up to entry time on the trade date
        cumulative_vol = 0
        bar_count = 0
        
        for timestamp, bar in data["Time Series (5min)"].items():
            # Format: "2026-01-14 08:15:00"
            bar_dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
            
            # Check if this bar is on the trade date and before/at entry time
            if bar_dt.strftime("%Y-%m-%d") == date_str:
                bar_hour = bar_dt.hour
                bar_min = bar_dt.minute
                
                if bar_hour < entry_hour or (bar_hour == entry_hour and bar_min <= entry_min):
                    cumulative_vol += int(bar.get("5. volume", 0))
                    bar_count += 1
        
        return {
            "cumulative_vol": cumulative_vol,
            "bar_count": bar_count,
            "source": "Alpha Vantage"
        }
        
    except Exception as e:
        return {"error": str(e)}


def test_fmp_aftermarket(symbol: str):
    """Test FMP aftermarket quote endpoint (real-time only)."""
    try:
        url = f"https://financialmodelingprep.com/stable/aftermarket-quote"
        params = {"symbol": symbol, "apikey": FMP_API_KEY}
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        return data
    except Exception as e:
        return {"error": str(e)}


def main():
    print("=" * 100)
    print("TESTING PRE-MARKET DATA SOURCES")
    print("=" * 100)
    print()
    
    # Check which APIs are available
    print("API Keys Available:")
    print(f"  - Alpha Vantage: {'✅' if ALPHA_VANTAGE_KEY else '❌'}")
    print(f"  - FMP: {'✅' if FMP_API_KEY else '❌'}")
    print()
    
    if ALPHA_VANTAGE_KEY:
        print("-" * 100)
        print("Testing Alpha Vantage (extended hours intraday)...")
        print("-" * 100)
        print(f"{'Symbol':<8} {'Date':<12} {'Entry':<8} {'Vol@Entry':<15} {'Bars':<8} {'Result'}")
        print("-" * 100)
        
        for trade in ROSS_TRADES[:3]:  # Limit to 3 to avoid rate limiting
            result = test_alpha_vantage_intraday(
                trade["symbol"],
                trade["date"],
                trade["entry_time"]
            )
            
            if "error" not in result:
                print(f"{trade['symbol']:<8} {trade['date']:<12} {trade['entry_time']:<8} "
                      f"{result['cumulative_vol']:>14,} {result['bar_count']:<8} {trade['result']}")
            else:
                print(f"{trade['symbol']:<8} {trade['date']:<12} {trade['entry_time']:<8} ERROR: {result['error']}")
    else:
        print("❌ No Alpha Vantage API key found in .env")
        print("   Add ALPHAVANTAGE_API_KEY=your_key to .env")
    
    print()
    print("=" * 100)
    print("NOTES:")
    print("- Alpha Vantage free tier: 25 requests/day, extended hours included by default")
    print("- Polygon.io: Best for historical pre-market data, requires paid subscription")
    print("- FMP aftermarket-quote: Real-time only, not historical")
    print("=" * 100)


if __name__ == "__main__":
    main()
