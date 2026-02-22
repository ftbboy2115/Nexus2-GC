"""Fetch 10s bars from Polygon and save to JSON for Mock Market replay."""
import json
import pytz
from nexus2.adapters.market_data.polygon_adapter import get_polygon_adapter

ET = pytz.timezone("US/Eastern")

def fetch_10s_bars(symbol: str, date: str):
    polygon = get_polygon_adapter()
    bars = polygon.get_second_bars(symbol, seconds=10, from_date=date, to_date=date)
    
    if not bars:
        print(f"No bars returned for {symbol} on {date}")
        return
    
    # Convert to JSON-serializable format with Eastern Time
    data = {
        "symbol": symbol,
        "date": date,
        "timeframe": "10s",
        "timezone": "US/Eastern",
        "bar_count": len(bars),
        "bars": [
            {
                "t": b.timestamp.astimezone(ET).strftime("%H:%M:%S"),
                "o": float(b.open),
                "h": float(b.high),
                "l": float(b.low),
                "c": float(b.close),
                "v": b.volume
            }
            for b in bars
        ]
    }
    
    # Save to file
    output_path = f"nexus2/tests/test_cases/intraday/{symbol.lower()}_{date.replace('-', '')}_10s.json"
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    
    first_time = bars[0].timestamp.astimezone(ET).strftime("%H:%M:%S")
    last_time = bars[-1].timestamp.astimezone(ET).strftime("%H:%M:%S")
    print(f"Saved {len(bars)} bars to {output_path}")
    print(f"Time range (ET): {first_time} to {last_time}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        fetch_10s_bars(sys.argv[1], sys.argv[2])
    else:
        # Fetch all 10s chart cases
        cases = [
            ("GRI", "2026-01-28"),
            ("HIND", "2026-01-27"),
            ("BCTX", "2026-01-27"),
        ]
        for symbol, date in cases:
            try:
                fetch_10s_bars(symbol, date)
            except Exception as e:
                print(f"Error fetching {symbol}: {e}")
