"""
Fetch Historical Bar Data for Ross Cameron Test Cases

Fetches 1-minute bars (including premarket) from Polygon for creating realistic test cases.
"""

import os
import sys
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Check for required packages
try:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
except ImportError:
    print("Installing alpaca-py...")
    os.system("pip install alpaca-py")
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

import pytz

# Use nexus2 config for credentials
from nexus2 import config as app_config

# 
# API_KEY = app_config.ALPACA_KEY
# API_SECRET = app_config.ALPACA_SECRET

# if not API_KEY or not API_SECRET:
#     print(f"Error: Missing Alpaca credentials")
#     print(f"  ALPACA_KEY: {'SET' if API_KEY else 'MISSING'}")
#     print(f"  ALPACA_SECRET: {'SET' if API_SECRET else 'MISSING'}")
#     exit(1)

# print(f"Using Alpaca key: {API_KEY[:8]}...")

# Initialize client
# client = StockHistoricalDataClient(API_KEY, API_SECRET)

ET = pytz.timezone("US/Eastern")

def fetch_bars(symbol: str, date_str: str, include_prev_day: bool = True) -> dict:
    """
    Fetch 1-minute bars for a symbol on a given date.
    Includes premarket (4am-9:30am) and market hours (9:30am-4pm).
    
    Uses Polygon as primary source (latest provider with best premarket coverage).
    Falls back to FMP if Polygon fails.
    
    Args:
        symbol: Stock symbol
        date_str: Date in YYYY-MM-DD format
        include_prev_day: If True, include previous day's last ~50 bars for MACD continuity
    
    Returns dict with bars, pmh, prev_close, etc.
    """
    from nexus2.adapters.market_data.polygon_adapter import get_polygon_adapter
    from datetime import timedelta
    
    date = datetime.strptime(date_str, "%Y-%m-%d")
    prev_date = date - timedelta(days=1)
    # Skip weekends for previous day
    while prev_date.weekday() >= 5:  # Saturday=5, Sunday=6
        prev_date -= timedelta(days=1)
    prev_date_str = prev_date.strftime("%Y-%m-%d")
    
    print(f"Fetching {symbol} bars from Polygon for {date_str}...")
    
    try:
        # Use Polygon adapter as primary source
        polygon = get_polygon_adapter()
        bars_data = polygon.get_intraday_bars(
            symbol=symbol,
            timeframe="1",  # 1-minute bars
            from_date=date_str,
            to_date=date_str,
            limit=1000
        )
        
        if not bars_data or len(bars_data) == 0:
            raise Exception("Polygon returned no data")
        
        print(f"  Got {len(bars_data)} bars from Polygon")
        
        # Fetch previous day's bars for MACD continuity
        prev_day_bars = []
        if include_prev_day:
            try:
                prev_bars_data = polygon.get_intraday_bars(
                    symbol=symbol,
                    timeframe="1",
                    from_date=prev_date_str,
                    to_date=prev_date_str,
                    limit=1000
                )
                if prev_bars_data and len(prev_bars_data) > 0:
                    # Take last 50 bars from previous day (for MACD 26-period + buffer)
                    prev_day_bars = prev_bars_data[-50:]
                    print(f"  Got {len(prev_day_bars)} bars from previous day ({prev_date_str}) for MACD continuity")
            except Exception as e:
                print(f"  Warning: Could not fetch previous day bars: {e}")
        
        # Convert to test case format
        continuity_bars = []  # Previous day bars for MACD calculation
        premarket_bars = []
        market_bars = []
        
        # Process previous day bars (mark with previous day's date in timestamp)
        for bar in prev_day_bars:
            bar_time = bar.timestamp.astimezone(ET)
            bar_dict = {
                "t": bar_time.strftime("%H:%M"),
                "d": prev_date_str,  # Include date to distinguish from current day
                "o": float(bar.open),
                "h": float(bar.high),
                "l": float(bar.low),
                "c": float(bar.close),
                "v": int(bar.volume),
                "prev_day": True,  # Flag for MACD continuity bars
            }
            continuity_bars.append(bar_dict)
        
        for bar in bars_data:
            bar_time = bar.timestamp.astimezone(ET)
            bar_dict = {
                "t": bar_time.strftime("%H:%M"),
                "o": float(bar.open),
                "h": float(bar.high),
                "l": float(bar.low),
                "c": float(bar.close),
                "v": int(bar.volume)
            }
            
            if bar_time.hour < 9 or (bar_time.hour == 9 and bar_time.minute < 30):
                premarket_bars.append(bar_dict)
            else:
                market_bars.append(bar_dict)
        
        # Calculate premarket high (PMH)
        pmh = max([b["h"] for b in premarket_bars]) if premarket_bars else None
        
        # Get previous close (use first premarket bar's open as approx)
        prev_close = premarket_bars[0]["o"] if premarket_bars else market_bars[0]["o"]
        
        # Calculate gap
        first_bar_open = market_bars[0]["o"] if market_bars else premarket_bars[-1]["c"]
        gap_percent = ((first_bar_open - prev_close) / prev_close) * 100 if prev_close else 0
        
        return {
            "symbol": symbol,
            "date": date_str,
            "continuity_bars": continuity_bars,  # Previous day bars for MACD
            "premarket_bars": premarket_bars,
            "market_bars": market_bars,
            "pmh": pmh,
            "prev_close": prev_close,
            "gap_percent": gap_percent,
            "source": "polygon",
        }
        
    except Exception as e:
        # Fallback to FMP for data
        print(f"  Polygon failed: {e}")
        print(f"  Trying FMP fallback...")
        import httpx
        fmp_key = os.getenv("FMP_API_KEY")
        url = f"https://financialmodelingprep.com/api/v3/historical-chart/1min/{symbol}?from={date_str}&to={date_str}&apikey={fmp_key}"
        resp = httpx.get(url, timeout=30)
        raw = resp.json()
        
        if not isinstance(raw, list) or len(raw) == 0:
            raise Exception(f"FMP also failed: {raw}")
        
        candles = list(reversed(raw))  # Chronological order
        print(f"  Got {len(candles)} bars from FMP")
        
        # Convert FMP format to our format
        premarket_bars = []
        market_bars = []
        for c in candles:
            time_str = c["date"].split()[1][:5]  # HH:MM
            bar_dict = {
                "t": time_str,
                "o": c["open"],
                "h": c["high"],
                "l": c["low"],
                "c": c["close"],
                "v": c["volume"]
            }
            hour = int(time_str[:2])
            minute = int(time_str[3:5])
            if hour < 9 or (hour == 9 and minute < 30):
                premarket_bars.append(bar_dict)
            else:
                market_bars.append(bar_dict)
        
        pmh = max([b["h"] for b in premarket_bars]) if premarket_bars else None
        first_bar = premarket_bars[0] if premarket_bars else market_bars[0]
        prev_close = first_bar["o"]
        first_market_open = market_bars[0]["o"] if market_bars else premarket_bars[-1]["c"]
        gap_percent = ((first_market_open - prev_close) / prev_close) * 100 if prev_close else 0
        
        return {
            "symbol": symbol,
            "date": date_str,
            "premarket_bars": premarket_bars,
            "market_bars": market_bars,
            "pmh": pmh,
            "prev_close": prev_close,
            "gap_percent": gap_percent,
            "source": "fmp",
        }


def create_test_case(symbol: str, date_str: str, catalyst: str, output_dir: Path):
    """Create a test case JSON file."""
    data = fetch_bars(symbol, date_str)
    
    # Continuity bars from previous day (for MACD calculation)
    continuity_bars = data.get("continuity_bars", [])
    
    # Combine premarket and market bars for full replay
    all_bars = data["premarket_bars"] + data["market_bars"]
    
    test_case = {
        "symbol": symbol,
        "date": date_str,
        "premarket": {
            "gap_percent": round(data["gap_percent"], 1),
            "pmh": data["pmh"],
            "previous_close": data["prev_close"],
            "float_shares": 5000000,  # Would need separate lookup
            "catalyst": catalyst,
        },
        "continuity_bars": continuity_bars,  # Previous day bars for MACD continuity
        "bars": all_bars,
        "source": data.get("source", "polygon"),  # Track data provider
    }
    
    filename = f"ross_{symbol.lower()}_{date_str.replace('-', '')}.json"
    output_path = output_dir / filename
    
    with open(output_path, "w") as f:
        json.dump(test_case, f, indent=2)
    
    print(f"Created: {output_path}")
    print(f"  PMH: ${data['pmh']}")
    print(f"  Gap: {data['gap_percent']:.1f}%")
    print(f"  Bars: {len(all_bars)} total, {len(data['premarket_bars'])} premarket, {len(continuity_bars)} continuity (prev day)")
    
    return filename


if __name__ == "__main__":
    # Script is in Nexus root, output to nexus2/tests/test_cases/intraday/
    output_dir = Path(__file__).parent / "nexus2" / "tests" / "test_cases" / "intraday"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Ross Cameron trades from transcripts
    # Usage: python fetch_ross_test_cases.py [SYMBOL DATE CATALYST]
    # If args provided, fetch single case. Otherwise fetch all in list.
    if len(sys.argv) >= 4:
        test_cases = [
            {"symbol": sys.argv[1], "date": sys.argv[2], "catalyst": sys.argv[3]}
        ]
    else:
        test_cases = [
            # January 2026 Ross Cameron trades - all confirmed from transcripts
            {"symbol": "ROLR", "date": "2026-01-14", "catalyst": "news"},
            {"symbol": "BNKK", "date": "2026-01-15", "catalyst": "news"},
            {"symbol": "LCFY", "date": "2026-01-16", "catalyst": "headline"},
            {"symbol": "TNMG", "date": "2026-01-16", "catalyst": "news"},
            {"symbol": "GWAV", "date": "2026-01-16", "catalyst": "news"},
            {"symbol": "VERO", "date": "2026-01-16", "catalyst": "news"},
            {"symbol": "BATL", "date": "2026-01-26", "catalyst": "news"},
            {"symbol": "BATL", "date": "2026-01-27", "catalyst": "news"},
            {"symbol": "HIND", "date": "2026-01-27", "catalyst": "news"},
            {"symbol": "GRI", "date": "2026-01-28", "catalyst": "news"},
            {"symbol": "DCX", "date": "2026-01-29", "catalyst": "news"},
            {"symbol": "LRHC", "date": "2026-01-30", "catalyst": "news"},
        ]
    
    created_files = []
    for tc in test_cases:
        try:
            filename = create_test_case(tc["symbol"], tc["date"], tc["catalyst"], output_dir)
            created_files.append(filename)
        except Exception as e:
            print(f"Error fetching {tc['symbol']}: {e}")
    
    print("\n=== Summary ===")
    print(f"Created {len(created_files)} test case files:")
    for f in created_files:
        print(f"  - {f}")
