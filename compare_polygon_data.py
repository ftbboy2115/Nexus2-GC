"""
Compare Polygon data vs existing test case data.
"""
import json
from pathlib import Path
import pytz
from nexus2.adapters.market_data.polygon_adapter import get_polygon_adapter

ET = pytz.timezone('US/Eastern')

def compare_case(symbol: str, date: str):
    """Compare Polygon intraday data with existing test case."""
    # Load existing test case
    case_file = Path(f'nexus2/tests/test_cases/intraday/ross_{symbol.lower()}_{date.replace("-", "")}.json')
    
    if not case_file.exists():
        print(f"No existing test case found: {case_file}")
        return
    
    with open(case_file) as f:
        old_data = json.load(f)
    
    print("="*60)
    print(f"COMPARING: {symbol} on {date}")
    print("="*60)
    
    print("\n--- EXISTING TEST CASE (Alpaca/FMP) ---")
    print(f"PMH: {old_data['premarket']['pmh']}")
    print(f"Gap: {old_data['premarket']['gap_percent']}%")
    print(f"Total bars: {len(old_data['bars'])}")
    
    # Count premarket vs market bars
    pm_count = sum(1 for b in old_data['bars'] if int(b['t'][:2]) < 9 or (int(b['t'][:2]) == 9 and int(b['t'][3:5]) < 30))
    mkt_count = len(old_data['bars']) - pm_count
    print(f"Premarket bars: {pm_count}, Market bars: {mkt_count}")
    
    if old_data['bars']:
        first = old_data['bars'][0]
        last = old_data['bars'][-1]
        print(f"First bar: {first['t']} O={first['o']:.2f} H={first['h']:.2f} L={first['l']:.2f} C={first['c']:.2f}")
        print(f"Last bar:  {last['t']} O={last['o']:.2f} H={last['h']:.2f} L={last['l']:.2f} C={last['c']:.2f}")
    
    # Fetch from Polygon
    print("\n--- POLYGON DATA ---")
    poly = get_polygon_adapter()
    bars = poly.get_intraday_bars(symbol, timeframe='1', from_date=date, to_date=date, limit=5000)
    
    if not bars:
        print("No Polygon bars returned!")
        return
    
    print(f"Total bars: {len(bars)}")
    
    # Calculate PMH (premarket high)
    pm_bars = [b for b in bars if b.timestamp.astimezone(ET).hour < 9 or 
               (b.timestamp.astimezone(ET).hour == 9 and b.timestamp.astimezone(ET).minute < 30)]
    mkt_bars = [b for b in bars if not (b.timestamp.astimezone(ET).hour < 9 or 
               (b.timestamp.astimezone(ET).hour == 9 and b.timestamp.astimezone(ET).minute < 30))]
    
    print(f"Premarket bars: {len(pm_bars)}, Market bars: {len(mkt_bars)}")
    
    if pm_bars:
        pmh = max(float(b.high) for b in pm_bars)
        print(f"Polygon PMH: {pmh:.2f}")
    
    if bars:
        first = bars[0]
        last = bars[-1]
        print(f"First bar: {first.timestamp.astimezone(ET).strftime('%H:%M')} O={float(first.open):.2f} H={float(first.high):.2f} L={float(first.low):.2f} C={float(first.close):.2f}")
        print(f"Last bar:  {last.timestamp.astimezone(ET).strftime('%H:%M')} O={float(last.open):.2f} H={float(last.high):.2f} L={float(last.low):.2f} C={float(last.close):.2f}")
    
    # Compare key metrics
    print("\n--- COMPARISON ---")
    old_pmh = old_data['premarket']['pmh']
    if pm_bars:
        poly_pmh = max(float(b.high) for b in pm_bars)
        pmh_diff = abs(poly_pmh - old_pmh)
        print(f"PMH: Old={old_pmh:.2f} vs Poly={poly_pmh:.2f} (diff={pmh_diff:.2f})")
    
    bar_diff = len(bars) - len(old_data['bars'])
    print(f"Bar count: Old={len(old_data['bars'])} vs Poly={len(bars)} (diff={bar_diff:+d})")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) >= 3:
        compare_case(sys.argv[1], sys.argv[2])
    else:
        # Default: compare LCFY 2026-01-16
        compare_case("LCFY", "2026-01-16")
