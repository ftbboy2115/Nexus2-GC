"""
Query historical EOD volume for Ross's recent trades.
FMP doesn't have pre-market intraday data, so we'll look at:
1. Full-day volume on trade day (shows total interest)
2. Average daily volume (for RVOL calculation)
"""

import os
from datetime import datetime, timedelta
import requests

from dotenv import load_dotenv
load_dotenv(r"c:\Users\ftbbo\Nextcloud4\OneDrive Backup\Documents (sync'd)\Development\Nexus\.env")

FMP_API_KEY = os.environ.get("FMP_API_KEY")
FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"

# Ross's trades from transcripts (Jan 5-18, 2026)
ROSS_TRADES = [
    {"symbol": "ROLR", "date": "2026-01-14", "entry_time": "08:18", "entry_price": 5.17, "result": "$85,000", "eod_peak": 21.0},
    {"symbol": "LCFY", "date": "2026-01-16", "entry_time": "08:00", "entry_price": 6.50, "result": "$10,000", "eod_peak": 7.30},
    {"symbol": "GWAV", "date": "2026-01-16", "entry_time": "07:30", "entry_price": 6.50, "result": "$4,000", "eod_peak": 8.43},
    {"symbol": "TNMG", "date": "2026-01-16", "entry_time": "07:15", "entry_price": 3.93, "result": "$2,100", "eod_peak": 4.10},
    {"symbol": "BNKK", "date": "2026-01-15", "entry_time": "08:30", "entry_price": 4.80, "result": "$15,000", "eod_peak": 6.00},
    {"symbol": "SPHL", "date": "2026-01-15", "entry_time": "07:01", "entry_price": 3.90, "result": "$100 (botched)", "eod_peak": 12.50},
    {"symbol": "OM", "date": "2026-01-12", "entry_time": "08:00", "entry_price": 6.50, "result": "$910", "eod_peak": 6.80},
    {"symbol": "APVO", "date": "2026-01-09", "entry_time": "07:30", "entry_price": 13.00, "result": "$6,000", "eod_peak": 14.00},
]


def get_eod_volume_data(symbol: str, date_str: str):
    """Get end-of-day volume for the trade date and calculate RVOL."""
    try:
        # Get daily bars
        url = f"{FMP_BASE_URL}/historical-price-full/{symbol}"
        params = {"apikey": FMP_API_KEY, "serietype": "bar"}
        resp = requests.get(url, params=params, timeout=15)
        
        if resp.status_code != 200:
            return {"error": f"API error: {resp.status_code}"}
        
        data = resp.json()
        daily_bars = data.get("historical", []) if isinstance(data, dict) else []
        
        if not daily_bars:
            return {"error": "No daily data"}
        
        # Find the trade date bar
        trade_date_bar = None
        for bar in daily_bars:
            if bar.get("date") == date_str:
                trade_date_bar = bar
                break
        
        if not trade_date_bar:
            return {"error": f"No data for {date_str}"}
        
        trade_day_vol = trade_date_bar.get("volume", 0)
        
        # Calculate average daily volume (20-day, excluding trade day)
        # Find index of trade date
        trade_idx = next((i for i, b in enumerate(daily_bars) if b.get("date") == date_str), 0)
        
        # Get bars AFTER the trade date (older dates, since FMP returns newest first)
        prior_bars = daily_bars[trade_idx+1:trade_idx+21]
        
        if prior_bars:
            avg_daily_vol = sum(b.get("volume", 0) for b in prior_bars) / len(prior_bars)
        else:
            avg_daily_vol = 1_000_000  # Fallback
        
        # Calculate actual EOD RVOL
        eod_rvol = trade_day_vol / avg_daily_vol if avg_daily_vol > 0 else 0
        
        return {
            "trade_day_vol": trade_day_vol,
            "avg_daily_vol": int(avg_daily_vol),
            "eod_rvol": eod_rvol,
        }
        
    except Exception as e:
        return {"error": str(e)}


def main():
    print("=" * 130)
    print("ROSS'S TRADES - END-OF-DAY VOLUME ANALYSIS")
    print("(FMP doesn't have pre-market intraday data, so we look at full-day volume)")
    print("=" * 130)
    print()
    print(f"{'Symbol':<8} {'Date':<12} {'Entry':<8} {'Price':<8} {'Peak':<8} {'TradeDayVol':<14} {'AvgDaily':<14} {'EOD RVOL':<12} {'Result'}")
    print("-" * 130)
    
    passing_2x = 0
    passing_5x = 0
    
    for trade in ROSS_TRADES:
        result = get_eod_volume_data(
            trade["symbol"],
            trade["date"],
        )
        
        if isinstance(result, dict) and "error" not in result:
            eod_rvol = result['eod_rvol']
            
            # Track how many pass thresholds
            if eod_rvol >= 2.0:
                passing_2x += 1
            if eod_rvol >= 5.0:
                passing_5x += 1
            
            # Color code based on RVOL
            rvol_indicator = "✅" if eod_rvol >= 5.0 else ("🟡" if eod_rvol >= 2.0 else "❌")
            
            print(f"{trade['symbol']:<8} {trade['date']:<12} {trade['entry_time']:<8} ${trade['entry_price']:<7} ${trade['eod_peak']:<7} "
                  f"{result['trade_day_vol']:>13,} {result['avg_daily_vol']:>13,} "
                  f"{eod_rvol:>9.1f}x {rvol_indicator}  {trade['result']}")
        else:
            error = result.get("error", result) if isinstance(result, dict) else result
            print(f"{trade['symbol']:<8} {trade['date']:<12} {trade['entry_time']:<8} ${trade['entry_price']:<7} ${trade.get('eod_peak', 'N/A'):<7} ERROR: {error}")
    
    print("-" * 130)
    print()
    print("=" * 130)
    print("SUMMARY:")
    print(f"  Trades analyzed: {len(ROSS_TRADES)}")
    print(f"  Passing 2x RVOL: {passing_2x}/{len(ROSS_TRADES)}")
    print(f"  Passing 5x RVOL: {passing_5x}/{len(ROSS_TRADES)}")
    print()
    print("KEY INSIGHT: This shows END-OF-DAY RVOL (after full day of trading)")
    print("Ross's 5x RVOL rule appears to be based on projected/expected RVOL, not raw pre-market")
    print("=" * 130)


if __name__ == "__main__":
    main()
