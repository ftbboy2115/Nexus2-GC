"""Test timestamp accuracy from Alpaca and FMP"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timezone
import httpx
from nexus2 import config

print(f'Current time: {datetime.now(timezone.utc).isoformat()}')
print()

# Alpaca
headers = {'APCA-API-KEY-ID': config.ALPACA_KEY, 'APCA-API-SECRET-KEY': config.ALPACA_SECRET}
r1 = httpx.get('https://data.alpaca.markets/v2/stocks/DVLT/quotes/latest', headers=headers)
alpaca = r1.json()
print('=== ALPACA QUOTE ===')
print(f"Timestamp: {alpaca['quote']['t']}")
print(f"Bid: {alpaca['quote']['bp']}, Ask: {alpaca['quote']['ap']}")

# FMP
r2 = httpx.get(f'https://financialmodelingprep.com/api/v3/quote/DVLT?apikey={config.FMP_API_KEY}')
fmp = r2.json()
print()
print('=== FMP QUOTE ===')
if fmp:
    print(f"Price: {fmp[0].get('price')}")
    print(f"Timestamp: {fmp[0].get('timestamp')}")
    print(f"Previous Close: {fmp[0].get('previousClose')}")
else:
    print('No data')
