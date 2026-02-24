"""Quick live data check for Polygon outage verification."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()
from nexus2.adapters.market_data.polygon_adapter import get_polygon_adapter

p = get_polygon_adapter()

print("=== LIVE DATA FRESHNESS CHECK ===\n")

# Real-time quote
q = p.get_quote("SPY")
print(f"SPY: ${q.price:.2f}  vol={q.volume:,.0f}  ts={q.timestamp}")

# Today's intraday bars
print("\n--- Today's Intraday Bars (2026-02-23) ---")
bars = p.get_intraday_bars("SPY", "1", from_date="2026-02-23", to_date="2026-02-23", limit=50)
print(f"Bars so far today: {len(bars)}")
if bars:
    print(f"  First: {bars[0].timestamp}  O={bars[0].open:.2f}")
    print(f"  Last:  {bars[-1].timestamp}  C={bars[-1].close:.2f}")

# Gainers
print("\n--- Gainers ---")
gainers = p.get_gainers()
print(f"Count: {len(gainers)}")
if gainers:
    for g in gainers[:5]:
        sym = g.get("symbol", "?")
        prc = g.get("price", 0)
        chg = g.get("change_pct", 0)
        vol = g.get("volume", 0)
        print(f"  {sym:>6s}: ${prc:.2f}  {chg:+.1f}%  vol={vol:,.0f}")

# Multi-symbol snapshot
print("\n--- Multi-Symbol Snapshot ---")
for sym in ["AAPL", "MSFT", "TSLA", "AMD"]:
    try:
        q = p.get_quote(sym)
        print(f"  {sym:>5s}: ${q.price:.2f}  vol={q.volume:,.0f}")
    except Exception as e:
        print(f"  {sym:>5s}: FAILED - {e}")

print("\n=== CHECK COMPLETE ===")
