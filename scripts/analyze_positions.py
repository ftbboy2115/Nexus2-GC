"""
Pre-market trend analysis for losing positions.
Checks if price is below 10 EMA and 20 EMA (character change exit signal).
"""
import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

FMP_API_KEY = os.getenv("FMP_API_KEY")
BASE_URL = "https://financialmodelingprep.com/api/v3"

# Top losing positions from screenshot
SYMBOLS = ["CMCSA", "PBR", "MDLZ", "WMB", "WBD", "T", "CP", "SONY", "CRM", "DASH"]

def get_quote(symbol: str) -> dict:
    """Get current quote"""
    url = f"{BASE_URL}/quote/{symbol}?apikey={FMP_API_KEY}"
    resp = requests.get(url)
    if resp.ok and resp.json():
        return resp.json()[0]
    return {}

def get_ema(symbol: str, period: int) -> float:
    """Get latest EMA value"""
    url = f"{BASE_URL}/technical_indicator/daily/{symbol}?period={period}&type=ema&apikey={FMP_API_KEY}"
    resp = requests.get(url)
    if resp.ok and resp.json():
        return resp.json()[0].get("ema", 0)
    return 0

def analyze_positions():
    print("=" * 80)
    print(f"TREND ANALYSIS - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 80)
    print()
    
    results = []
    
    for symbol in SYMBOLS:
        quote = get_quote(symbol)
        price = quote.get("price", 0)
        prev_close = quote.get("previousClose", 0)
        
        ema10 = get_ema(symbol, 10)
        ema20 = get_ema(symbol, 20)
        
        below_10 = price < ema10
        below_20 = price < ema20
        character_change = below_10 and below_20
        
        status = "🔴 CHARACTER CHANGE" if character_change else (
            "🟡 BELOW 10 EMA" if below_10 else (
            "🟡 BELOW 20 EMA" if below_20 else "🟢 TREND OK"))
        
        result = {
            "symbol": symbol,
            "price": price,
            "prev_close": prev_close,
            "ema10": ema10,
            "ema20": ema20,
            "below_10": below_10,
            "below_20": below_20,
            "character_change": character_change,
            "status": status
        }
        results.append(result)
        
        print(f"{symbol:6} | Price: ${price:7.2f} | 10 EMA: ${ema10:7.2f} | 20 EMA: ${ema20:7.2f} | {status}")
    
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    char_changes = [r for r in results if r["character_change"]]
    if char_changes:
        print(f"\n🔴 CHARACTER CHANGE EXITS ({len(char_changes)} positions):")
        for r in char_changes:
            print(f"   {r['symbol']} - Price ${r['price']:.2f} below both 10 EMA (${r['ema10']:.2f}) and 20 EMA (${r['ema20']:.2f})")
    else:
        print("\n✅ No character change exits detected")
    
    partial = [r for r in results if (r["below_10"] or r["below_20"]) and not r["character_change"]]
    if partial:
        print(f"\n🟡 WARNING - Below one MA ({len(partial)} positions):")
        for r in partial:
            ma = "10 EMA" if r["below_10"] else "20 EMA"
            print(f"   {r['symbol']} - Below {ma}")
    
    ok = [r for r in results if not r["below_10"] and not r["below_20"]]
    if ok:
        print(f"\n🟢 TREND OK ({len(ok)} positions):")
        for r in ok:
            print(f"   {r['symbol']}")
    
    return results

if __name__ == "__main__":
    analyze_positions()
