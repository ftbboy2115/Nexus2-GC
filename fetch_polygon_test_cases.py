"""
Fetch test cases using Polygon.io data.
"""
import json
from pathlib import Path
import pytz
from nexus2.adapters.market_data.polygon_adapter import get_polygon_adapter

ET = pytz.timezone('US/Eastern')
OUTPUT_DIR = Path('nexus2/tests/test_cases/intraday')

def create_test_case(symbol: str, date: str, catalyst: str, ross_pnl: float = None, notes: str = ""):
    """Create a test case JSON file using Polygon data."""
    poly = get_polygon_adapter()
    bars = poly.get_intraday_bars(symbol, timeframe='1', from_date=date, to_date=date, limit=5000)
    
    if not bars:
        print(f"ERROR: No Polygon data for {symbol} on {date}")
        return None
    
    # Separate premarket vs market bars
    pm_bars = []
    mkt_bars = []
    
    for b in bars:
        bar_time = b.timestamp.astimezone(ET)
        bar_dict = {
            "t": bar_time.strftime("%H:%M"),
            "o": float(b.open),
            "h": float(b.high),
            "l": float(b.low),
            "c": float(b.close),
            "v": int(b.volume)
        }
        if bar_time.hour < 9 or (bar_time.hour == 9 and bar_time.minute < 30):
            pm_bars.append(bar_dict)
        elif bar_time.hour < 16:  # Only include market hours (exclude after-hours)
            mkt_bars.append(bar_dict)
    
    # Calculate PMH
    pmh = max(b["h"] for b in pm_bars) if pm_bars else None
    
    # Get previous close from first bar
    first_bar = pm_bars[0] if pm_bars else mkt_bars[0]
    prev_close = first_bar["o"]
    
    # Calculate gap
    market_open = mkt_bars[0]["o"] if mkt_bars else first_bar["c"]
    gap_percent = ((market_open - prev_close) / prev_close * 100) if prev_close else 0
    
    # Build test case
    test_case = {
        "symbol": symbol,
        "date": date,
        "data_source": "polygon",
        "premarket": {
            "gap_percent": round(gap_percent, 1),
            "pmh": round(pmh, 2) if pmh else None,
            "previous_close": round(prev_close, 2),
            "float_shares": 5000000,  # Placeholder
            "catalyst": catalyst,
        },
        "bars": pm_bars + mkt_bars
    }
    
    if ross_pnl:
        test_case["ross_pnl"] = ross_pnl
    if notes:
        test_case["notes"] = notes
    
    # Save
    filename = f"ross_{symbol.lower()}_{date.replace('-', '')}.json"
    output_path = OUTPUT_DIR / filename
    
    with open(output_path, 'w') as f:
        json.dump(test_case, f, indent=2)
    
    print(f"✅ Created: {output_path}")
    print(f"   PMH: ${pmh:.2f}" if pmh else "   No premarket bars")
    print(f"   Gap: {gap_percent:.1f}%")
    print(f"   Bars: {len(pm_bars)} premarket + {len(mkt_bars)} market")
    
    return filename


if __name__ == "__main__":
    import sys
    
    # Default: create recent high-priority cases
    cases = [
        {"symbol": "LRHC", "date": "2026-01-30", "catalyst": "sympathy_momentum", 
         "ross_pnl": 31076.62, "notes": "Cup & Handle VWAP Break - sympathy from TCGL squeeze"},
        {"symbol": "GRI", "date": "2026-01-28", "catalyst": "biotech_news",
         "ross_pnl": 33499.98, "notes": "RS + Breaking News 8:45 AM - HC Wainwright shelf"},
    ]
    
    if len(sys.argv) >= 3:
        # Command line: symbol date catalyst
        symbol = sys.argv[1]
        date = sys.argv[2]
        catalyst = sys.argv[3] if len(sys.argv) > 3 else "news"
        create_test_case(symbol, date, catalyst)
    else:
        # Run default cases
        for case in cases:
            create_test_case(**case)
