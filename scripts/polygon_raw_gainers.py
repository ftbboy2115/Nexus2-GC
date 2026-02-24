"""Check raw Polygon gainers response to see if change_pct is missing at source."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv
load_dotenv()
import json
from nexus2.adapters.market_data.polygon_adapter import get_polygon_adapter

p = get_polygon_adapter()

# Get raw response
data = p._get("/v2/snapshot/locale/us/markets/stocks/gainers")
print(f"Status: {data.get('status')}")
print(f"Ticker count: {len(data.get('tickers', []))}")

# Show first 3 tickers raw
for t in data.get("tickers", [])[:3]:
    print(f"\n--- {t.get('ticker')} ---")
    print(f"  todaysChangePerc: {t.get('todaysChangePerc')}")
    print(f"  todaysChange:     {t.get('todaysChange')}")
    print(f"  day:     {json.dumps(t.get('day', {}), indent=4)}")
    print(f"  prevDay: {json.dumps(t.get('prevDay', {}), indent=4)}")
    print(f"  lastQuote: {json.dumps(t.get('lastQuote', {}), indent=4)}")
