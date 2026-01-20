"""Test Alpaca's top movers API for pre-market detection."""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

key = os.environ.get('APCA_API_KEY_ID')
secret = os.environ.get('APCA_API_SECRET_KEY')

headers = {'APCA-API-KEY-ID': key, 'APCA-API-SECRET-KEY': secret}

# Test 1: Top Movers
print("=" * 60)
print("Alpaca Top Movers (Screener)")
print("=" * 60)
r = requests.get(
    'https://data.alpaca.markets/v1beta1/screener/stocks/movers?top=50',
    headers=headers
)
data = r.json()
print(f"Gainers: {len(data.get('gainers', []))}")
print(f"Losers: {len(data.get('losers', []))}")

gainers = data.get('gainers', [])
if gainers:
    print("\nTop 10 Gainers:")
    for g in gainers[:10]:
        print(f"  {g.get('symbol')}: {g.get('percent_change', 0):.1f}%")

# Check for TWG
twg = [x for x in gainers if x.get('symbol') == 'TWG']
print(f"\nTWG in list: {twg if twg else 'NOT FOUND'}")

# Test 2: Direct snapshot for TWG
print("\n" + "=" * 60)
print("Alpaca Snapshot for TWG")
print("=" * 60)
r2 = requests.get(
    'https://data.alpaca.markets/v2/stocks/TWG/snapshot',
    headers=headers
)
print(r2.json())
