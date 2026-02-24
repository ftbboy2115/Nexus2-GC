"""
Polygon Data Health Check
Quick diagnostic to verify Polygon API connectivity and data quality.
"""
import sys
import os
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from nexus2.adapters.market_data.polygon_adapter import get_polygon_adapter

def main():
    print("=" * 60)
    print("  POLYGON DATA HEALTH CHECK")
    print("=" * 60)
    
    # 1. API Key check
    api_key = os.getenv("POLYGON_API_KEY", "")
    if not api_key:
        print("\n❌ POLYGON_API_KEY not set in environment!")
        return
    print(f"\n✅ API Key: ...{api_key[-6:]}")
    
    polygon = get_polygon_adapter()
    
    # 2. Test snapshot/quote (real-time)
    print("\n--- Real-Time Quote Test (SPY) ---")
    try:
        quote = polygon.get_quote("SPY")
        print(f"  Price: ${quote.price:.2f}")
        print(f"  Bid/Ask: ${quote.bid:.2f} / ${quote.ask:.2f}")
        print(f"  Volume: {quote.volume:,}")
        print(f"  Timestamp: {quote.timestamp}")
        print(f"  ✅ Real-time quotes working")
    except Exception as e:
        print(f"  ❌ Quote failed: {e}")
    
    # 3. Test gainers endpoint (scanner depends on this)
    print("\n--- Gainers Snapshot Test ---")
    try:
        gainers = polygon.get_gainers()
        print(f"  Got {len(gainers)} gainers")
        if gainers:
            top3 = gainers[:3]
            for g in top3:
                print(f"    {g.get('symbol', '?'):>6s}: ${g.get('price', 0):.2f}  ({g.get('change_pct', 0):+.1f}%)  vol={g.get('volume', 0):,}")
        print(f"  ✅ Gainers endpoint working")
    except Exception as e:
        print(f"  ❌ Gainers failed: {e}")
    
    # 4. Test historical bars (test case data quality)
    print("\n--- Historical Bars Test (AAPL, last trading day) ---")
    try:
        # Use a known date that should have data
        bars = polygon.get_intraday_bars(
            symbol="AAPL",
            timeframe="1",
            from_date="2026-02-21",  # Last Friday
            to_date="2026-02-21",
            limit=500
        )
        print(f"  Got {len(bars)} bars")
        if bars:
            first = bars[0]
            last = bars[-1]
            print(f"  First: {first.timestamp} O={first.open:.2f}")
            print(f"  Last:  {last.timestamp} C={last.close:.2f}")
            
            # Check for premarket bars
            from zoneinfo import ZoneInfo
            ET = ZoneInfo("US/Eastern")
            premarket = [b for b in bars if b.timestamp.astimezone(ET).hour < 9 or 
                        (b.timestamp.astimezone(ET).hour == 9 and b.timestamp.astimezone(ET).minute < 30)]
            market = [b for b in bars if not (b.timestamp.astimezone(ET).hour < 9 or 
                     (b.timestamp.astimezone(ET).hour == 9 and b.timestamp.astimezone(ET).minute < 30))]
            print(f"  Premarket bars: {len(premarket)}")
            print(f"  Market bars: {len(market)}")
        print(f"  ✅ Historical bars working")
    except Exception as e:
        print(f"  ❌ Historical bars failed: {e}")
    
    # 5. Test a known test case symbol to verify data availability
    print("\n--- Test Case Symbol Check (recent test cases) ---")
    test_symbols = [
        ("EDHL", "2026-02-20"),
        ("ENVB", "2026-02-19"),
        ("SNSE", "2026-02-18"),
    ]
    for symbol, date in test_symbols:
        try:
            bars = polygon.get_intraday_bars(
                symbol=symbol,
                timeframe="1",
                from_date=date,
                to_date=date,
                limit=500
            )
            if bars:
                from zoneinfo import ZoneInfo
                ET = ZoneInfo("US/Eastern")
                premarket = [b for b in bars if b.timestamp.astimezone(ET).hour < 9 or 
                            (b.timestamp.astimezone(ET).hour == 9 and b.timestamp.astimezone(ET).minute < 30)]
                print(f"  {symbol} ({date}): {len(bars)} bars ({len(premarket)} premarket) ✅")
            else:
                print(f"  {symbol} ({date}): No bars returned ❌")
        except Exception as e:
            print(f"  {symbol} ({date}): Error - {e} ❌")
    
    # 6. Test ticker details (shares outstanding)
    print("\n--- Ticker Details Test (AAPL) ---")
    try:
        details = polygon.get_ticker_details("AAPL")
        print(f"  Name: {details.get('name', '?')}")
        print(f"  Market Cap: ${details.get('market_cap', 0):,.0f}")
        print(f"  Shares Outstanding: {details.get('shares_outstanding', 0):,.0f}")
        print(f"  ✅ Ticker details working")
    except Exception as e:
        print(f"  ❌ Ticker details failed: {e}")
    
    # 7. Test news endpoint
    print("\n--- News Endpoint Test ---")
    try:
        news = polygon.get_news(limit=3)
        print(f"  Got {len(news)} articles")
        if news:
            for n in news[:2]:
                title = n.get('title', '?')[:60]
                print(f"    - {title}...")
        print(f"  ✅ News endpoint working")
    except Exception as e:
        print(f"  ❌ News failed: {e}")
    
    # 8. Check second-level bars (10s) availability
    print("\n--- Second Bars Test (EDHL, 10s) ---")
    try:
        bars_10s = polygon.get_second_bars(
            symbol="EDHL",
            seconds=10,
            from_date="2026-02-20",
            to_date="2026-02-20",
            limit=500
        )
        print(f"  Got {len(bars_10s)} 10-second bars")
        if bars_10s:
            print(f"  First: {bars_10s[0].timestamp}")
            print(f"  Last:  {bars_10s[-1].timestamp}")
        print(f"  ✅ Second-level bars working")
    except Exception as e:
        print(f"  ❌ Second bars failed: {e}")
    
    print("\n" + "=" * 60)
    print("  HEALTH CHECK COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
