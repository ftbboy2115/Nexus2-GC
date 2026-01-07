"""
Check if MAs were stacked on the entry date (Jan 2, 2026).
"""
import os
import requests
from datetime import datetime, timedelta
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()

FMP_API_KEY = os.getenv("FMP_API_KEY")
BASE_URL = "https://financialmodelingprep.com/api/v3"

SYMBOLS = ['CMCSA', 'CP', 'MDLZ', 'PBR', 'T', 'WBD', 'WMB']
ENTRY_DATE = "2026-01-02"  # Date positions were opened

def get_historical_bars(symbol: str, days: int = 60) -> list:
    """Get historical daily bars."""
    url = f"{BASE_URL}/historical-price-full/{symbol}?apikey={FMP_API_KEY}"
    resp = requests.get(url)
    if resp.ok and resp.json():
        return resp.json().get("historical", [])[:days]
    return []

def check_ma_stacking_on_date(symbol: str, target_date: str) -> dict:
    """Check if MAs were stacked on a specific date."""
    bars = get_historical_bars(symbol, 70)  # Need 50+ days for SMA50
    
    if not bars:
        return {"symbol": symbol, "error": "No data"}
    
    # Find the target date index
    target_idx = None
    for i, bar in enumerate(bars):
        if bar["date"] == target_date:
            target_idx = i
            break
    
    if target_idx is None:
        # Try to find closest date
        for i, bar in enumerate(bars):
            if bar["date"] < target_date:
                target_idx = i
                break
    
    if target_idx is None or target_idx + 50 > len(bars):
        return {"symbol": symbol, "error": f"Not enough data for {target_date}"}
    
    # Get closes from target date forward (bars are reverse chronological)
    closes = [Decimal(str(bars[i]["close"])) for i in range(target_idx, min(target_idx + 60, len(bars)))]
    
    if len(closes) < 50:
        return {"symbol": symbol, "error": "Not enough data for SMA50"}
    
    # Calculate SMAs as of target date
    price = closes[0]  # Price on target date
    sma10 = sum(closes[:10]) / 10
    sma20 = sum(closes[:20]) / 20
    sma50 = sum(closes[:50]) / 50
    
    ma_stacked = price > sma10 > sma20 > sma50
    
    return {
        "symbol": symbol,
        "date": bars[target_idx]["date"],
        "price": float(price),
        "sma10": float(sma10),
        "sma20": float(sma20),
        "sma50": float(sma50),
        "ma_stacked": ma_stacked,
        "price_vs_10": "✅" if price > sma10 else "❌",
        "10_vs_20": "✅" if sma10 > sma20 else "❌",
        "20_vs_50": "✅" if sma20 > sma50 else "❌",
    }

print("="*70)
print(f" MA STACKING CHECK ON ENTRY DATE ({ENTRY_DATE})")
print("="*70)

for symbol in SYMBOLS:
    result = check_ma_stacking_on_date(symbol, ENTRY_DATE)
    
    if "error" in result:
        print(f"\n{symbol}: {result['error']}")
        continue
    
    print(f"\n{symbol} on {result['date']}:")
    print(f"  Price:  ${result['price']:.2f}")
    print(f"  SMA10:  ${result['sma10']:.2f} {result['price_vs_10']}")
    print(f"  SMA20:  ${result['sma20']:.2f} {result['10_vs_20']}")
    print(f"  SMA50:  ${result['sma50']:.2f} {result['20_vs_50']}")
    print(f"  MA STACKED: {'✅ YES' if result['ma_stacked'] else '❌ NO'}")

print("\n" + "="*70)
