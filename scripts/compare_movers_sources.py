"""Compare FMP vs Alpaca pre-market movers data in real-time."""
import os
import requests
from dotenv import load_dotenv
from decimal import Decimal

load_dotenv()

# FMP Setup
fmp_key = os.environ.get('FMP_API_KEY')

# Alpaca Setup
alpaca_key = os.environ.get('APCA_API_KEY_ID')
alpaca_secret = os.environ.get('APCA_API_SECRET_KEY')
alpaca_headers = {'APCA-API-KEY-ID': alpaca_key, 'APCA-API-SECRET-KEY': alpaca_secret}

print("=" * 80)
print("FMP vs Alpaca Pre-Market Movers Comparison")
print("=" * 80)

# FMP Actives
print("\n📊 FMP stock_market/actives (Top 10):")
fmp_actives = requests.get(f'https://financialmodelingprep.com/api/v3/stock_market/actives?apikey={fmp_key}').json()
fmp_dict = {}
for i, item in enumerate(fmp_actives[:10]):
    sym = item.get('symbol')
    pct = item.get('changesPercentage', 0)
    fmp_dict[sym] = pct
    print(f"  {i+1:2}. {sym:6} | {pct:>8.1f}%")

# FMP Gainers
print("\n📊 FMP stock_market/gainers (Top 10):")
fmp_gainers = requests.get(f'https://financialmodelingprep.com/api/v3/stock_market/gainers?apikey={fmp_key}').json()
for i, item in enumerate(fmp_gainers[:10]):
    sym = item.get('symbol')
    pct = item.get('changesPercentage', 0)
    fmp_dict[sym] = pct
    print(f"  {i+1:2}. {sym:6} | {pct:>8.1f}%")

# FMP Pre-market Gainers
print("\n📊 FMP pre_post_market/gainers (Top 10):")
fmp_premarket = requests.get(f'https://financialmodelingprep.com/api/v3/pre_post_market/gainers?apikey={fmp_key}').json()
if fmp_premarket:
    for i, item in enumerate(fmp_premarket[:10]):
        sym = item.get('symbol')
        pct = item.get('changesPercentage', 0)
        print(f"  {i+1:2}. {sym:6} | {pct:>8.1f}%")
else:
    print("  (empty)")

# Alpaca Top Movers
print("\n📊 Alpaca screener/stocks/movers (Top 10 Gainers):")
alpaca_resp = requests.get(
    'https://data.alpaca.markets/v1beta1/screener/stocks/movers?top=50',
    headers=alpaca_headers
).json()
alpaca_gainers = alpaca_resp.get('gainers', [])
alpaca_dict = {}
for i, item in enumerate(alpaca_gainers[:10]):
    sym = item.get('symbol')
    pct = item.get('percent_change', 0)
    alpaca_dict[sym] = pct
    print(f"  {i+1:2}. {sym:6} | {pct:>8.1f}%")

# Cross-reference
print("\n" + "=" * 80)
print("🔍 DISCREPANCY ANALYSIS")
print("=" * 80)

# Find symbols in Alpaca but not in FMP (potential misses)
alpaca_only = set(alpaca_dict.keys()) - set(fmp_dict.keys())
if alpaca_only:
    print("\n⚠️  In Alpaca TOP 10 but NOT in FMP actives/gainers TOP 10:")
    for sym in alpaca_only:
        print(f"   {sym}: {alpaca_dict[sym]:.1f}%")

# Find symbols in both and compare
common = set(alpaca_dict.keys()) & set(fmp_dict.keys())
if common:
    print("\n📈 Common symbols (FMP vs Alpaca):")
    for sym in sorted(common, key=lambda x: alpaca_dict[x], reverse=True):
        fmp_pct = fmp_dict[sym]
        alp_pct = alpaca_dict[sym]
        diff = abs(fmp_pct - alp_pct)
        flag = "⚠️" if diff > 5 else "✅"
        print(f"   {flag} {sym}: FMP={fmp_pct:>6.1f}% | Alpaca={alp_pct:>6.1f}% | Diff={diff:.1f}%")

print("\n" + "=" * 80)
