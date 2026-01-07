"""
Trade Post-Mortem Analysis
Analyzes the 7 failed positions to determine if they should have been taken.
"""
import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

FMP_API_KEY = os.getenv("FMP_API_KEY")
BASE_URL = "https://financialmodelingprep.com/api/v3"

SYMBOLS = ["CMCSA", "CP", "MDLZ", "PBR", "T", "WBD", "WMB"]

def get_quote(symbol: str) -> dict:
    url = f"{BASE_URL}/quote/{symbol}?apikey={FMP_API_KEY}"
    resp = requests.get(url)
    return resp.json()[0] if resp.ok and resp.json() else {}

def get_profile(symbol: str) -> dict:
    url = f"{BASE_URL}/profile/{symbol}?apikey={FMP_API_KEY}"
    resp = requests.get(url)
    return resp.json()[0] if resp.ok and resp.json() else {}

def get_ratios(symbol: str) -> dict:
    url = f"{BASE_URL}/ratios-ttm/{symbol}?apikey={FMP_API_KEY}"
    resp = requests.get(url)
    return resp.json()[0] if resp.ok and resp.json() else {}

def get_daily_history(symbol: str, days: int = 30) -> list:
    url = f"{BASE_URL}/historical-price-full/{symbol}?apikey={FMP_API_KEY}"
    resp = requests.get(url)
    if resp.ok and resp.json():
        return resp.json().get("historical", [])[:days]
    return []

def get_ema(symbol: str, period: int) -> float:
    url = f"{BASE_URL}/technical_indicator/daily/{symbol}?period={period}&type=ema&apikey={FMP_API_KEY}"
    resp = requests.get(url)
    return resp.json()[0].get("ema", 0) if resp.ok and resp.json() else 0

def get_rsi(symbol: str) -> float:
    url = f"{BASE_URL}/technical_indicator/daily/{symbol}?period=14&type=rsi&apikey={FMP_API_KEY}"
    resp = requests.get(url)
    return resp.json()[0].get("rsi", 0) if resp.ok and resp.json() else 0

def analyze_trade(symbol: str) -> dict:
    """Analyze a single trade for post-mortem."""
    print(f"\n{'='*60}")
    print(f"Analyzing {symbol}...")
    
    quote = get_quote(symbol)
    profile = get_profile(symbol)
    ratios = get_ratios(symbol)
    history = get_daily_history(symbol, 30)
    
    ema10 = get_ema(symbol, 10)
    ema20 = get_ema(symbol, 20)
    ema50 = get_ema(symbol, 50)
    rsi = get_rsi(symbol)
    
    price = quote.get("price", 0)
    market_cap = profile.get("mktCap", 0) / 1e9  # in billions
    sector = profile.get("sector", "N/A")
    industry = profile.get("industry", "N/A")
    
    # Calculate recent performance
    if len(history) >= 5:
        price_5d_ago = history[4].get("close", price)
        pct_change_5d = ((price - price_5d_ago) / price_5d_ago) * 100
    else:
        pct_change_5d = 0
    
    if len(history) >= 20:
        price_20d_ago = history[19].get("close", price)
        pct_change_20d = ((price - price_20d_ago) / price_20d_ago) * 100
    else:
        pct_change_20d = 0
    
    # Volume analysis
    if len(history) >= 20:
        avg_vol = sum(d.get("volume", 0) for d in history[:20]) / 20
        latest_vol = history[0].get("volume", 0) if history else 0
        rvol = latest_vol / avg_vol if avg_vol > 0 else 0
    else:
        rvol = 0
    
    # MA stacking check (KK criteria)
    ma_stacked = price > ema10 > ema20 > ema50
    
    # Trend analysis
    above_10 = price > ema10
    above_20 = price > ema20
    above_50 = price > ema50
    
    result = {
        "symbol": symbol,
        "price": price,
        "market_cap_b": market_cap,
        "sector": sector,
        "industry": industry,
        "ema10": ema10,
        "ema20": ema20,
        "ema50": ema50,
        "rsi": rsi,
        "pct_5d": pct_change_5d,
        "pct_20d": pct_change_20d,
        "rvol": rvol,
        "ma_stacked": ma_stacked,
        "above_10": above_10,
        "above_20": above_20,
        "above_50": above_50,
    }
    
    return result

def print_analysis(r: dict):
    """Print formatted analysis."""
    symbol = r["symbol"]
    
    print(f"\n{'='*60}")
    print(f" {symbol} - Post-Mortem Analysis")
    print(f"{'='*60}")
    
    print(f"\n📊 BASICS:")
    print(f"   Price: ${r['price']:.2f}")
    print(f"   Market Cap: ${r['market_cap_b']:.1f}B")
    print(f"   Sector: {r['sector']}")
    print(f"   Industry: {r['industry']}")
    
    print(f"\n📈 TECHNICALS:")
    print(f"   10 EMA: ${r['ema10']:.2f} {'✅' if r['above_10'] else '❌'}")
    print(f"   20 EMA: ${r['ema20']:.2f} {'✅' if r['above_20'] else '❌'}")
    print(f"   50 EMA: ${r['ema50']:.2f} {'✅' if r['above_50'] else '❌'}")
    print(f"   RSI(14): {r['rsi']:.1f}")
    print(f"   MA Stacked: {'✅ YES' if r['ma_stacked'] else '❌ NO'}")
    
    print(f"\n📉 PERFORMANCE:")
    print(f"   5-Day: {r['pct_5d']:+.1f}%")
    print(f"   20-Day: {r['pct_20d']:+.1f}%")
    print(f"   RVOL: {r['rvol']:.2f}x")
    
    # Verdict
    issues = []
    if not r['ma_stacked']:
        issues.append("MAs not stacked (trend weak)")
    if r['pct_5d'] < -3:
        issues.append(f"Sharp recent drop ({r['pct_5d']:.1f}%)")
    if r['rvol'] < 0.8:
        issues.append("Low relative volume")
    if r['rsi'] < 40:
        issues.append(f"RSI weak ({r['rsi']:.0f})")
    
    print(f"\n🔍 VERDICT:")
    if not issues:
        print("   ✅ Setup looked valid - just didn't work out")
    else:
        print("   ⚠️ POTENTIAL ISSUES:")
        for issue in issues:
            print(f"      • {issue}")

def main():
    print("="*60)
    print(" TRADE POST-MORTEM ANALYSIS")
    print(f" Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*60)
    
    results = []
    for symbol in SYMBOLS:
        try:
            r = analyze_trade(symbol)
            results.append(r)
            print_analysis(r)
        except Exception as e:
            print(f"Error analyzing {symbol}: {e}")
    
    # Summary
    print("\n" + "="*60)
    print(" SUMMARY")
    print("="*60)
    
    valid_setups = [r for r in results if r['ma_stacked'] and r['pct_5d'] > -3]
    questionable = [r for r in results if not r['ma_stacked'] or r['pct_5d'] < -3]
    
    print(f"\n✅ Valid setups that didn't work out: {len(valid_setups)}")
    for r in valid_setups:
        print(f"   {r['symbol']}")
    
    print(f"\n⚠️ Questionable entries: {len(questionable)}")
    for r in questionable:
        print(f"   {r['symbol']}")

if __name__ == "__main__":
    main()
