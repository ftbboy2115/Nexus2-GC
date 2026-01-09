"""Fetch historical intraday data for Warrior test cases."""
from nexus2 import config
import httpx

api_key = config.FMP_API_KEY

# Test cases to fetch
test_cases = [
    ("ACON", "2025-01-08"),
    ("FLYX", "2025-01-08"),
    ("CMCT", "2024-12-24"),
]

for symbol, date in test_cases:
    print(f"\n=== {symbol} {date} ===")
    
    url = f"https://financialmodelingprep.com/api/v3/historical-chart/1min/{symbol}?from={date}&to={date}&apikey={api_key}"
    
    try:
        resp = httpx.get(url, timeout=30)
        data = resp.json()
        
        if data and not isinstance(data, dict):  # Check it's not an error
            print(f"Total candles: {len(data)}")
            
            # FMP returns newest first, reverse it
            data = list(reversed(data))
            
            # Show first 5 (open) and last 5 (close)
            print("\nFirst 5 candles (market open):")
            for c in data[:5]:
                print(f"  {c['date']} O:{c['open']:.2f} H:{c['high']:.2f} L:{c['low']:.2f} C:{c['close']:.2f}")
            
            print("\nLast 5 candles (market close):")
            for c in data[-5:]:
                print(f"  {c['date']} O:{c['open']:.2f} H:{c['high']:.2f} L:{c['low']:.2f} C:{c['close']:.2f}")
            
            # Find high and low of day
            high = max(c['high'] for c in data)
            low = min(c['low'] for c in data)
            open_price = data[0]['open']
            close_price = data[-1]['close']
            
            print(f"\nSummary: Open ${open_price:.2f} | High ${high:.2f} | Low ${low:.2f} | Close ${close_price:.2f}")
        else:
            print(f"No data or error: {data}")
            
    except Exception as e:
        print(f"Error: {e}")
