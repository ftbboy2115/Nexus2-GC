"""
FMP vs Alpaca Quote Comparison Script

Compares real-time quotes from FMP and Alpaca to diagnose data discrepancies.
"""

import asyncio
import os
import sys
from decimal import Decimal
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from nexus2.adapters.market_data.fmp_adapter import FMPAdapter
from nexus2.adapters.market_data.alpaca_adapter import AlpacaAdapter


def compare_quotes(symbols: list[str]):
    """Compare FMP and Alpaca quotes for given symbols."""
    
    print("=" * 60)
    print(f"FMP vs Alpaca Quote Comparison - {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 60)
    
    fmp = FMPAdapter()
    alpaca = AlpacaAdapter()
    
    print(f"\n{'Symbol':<8} {'FMP Price':<12} {'Alpaca Price':<14} {'Diff':<10} {'% Diff':<8}")
    print("-" * 60)
    
    for symbol in symbols:
        fmp_quote = fmp.get_quote(symbol)
        alpaca_quote = alpaca.get_quote(symbol)
        
        fmp_price = fmp_quote.price if fmp_quote else None
        alpaca_price = alpaca_quote.price if alpaca_quote else None
        
        if fmp_price and alpaca_price:
            diff = float(fmp_price) - float(alpaca_price)
            pct_diff = (diff / float(alpaca_price)) * 100
            status = "✅" if abs(pct_diff) < 0.5 else "⚠️" if abs(pct_diff) < 2 else "❌"
            print(f"{symbol:<8} ${float(fmp_price):>9.2f}  ${float(alpaca_price):>11.2f}  {diff:>+8.2f}  {pct_diff:>+6.2f}% {status}")
        else:
            fmp_str = f"${float(fmp_price):.2f}" if fmp_price else "N/A"
            alpaca_str = f"${float(alpaca_price):.2f}" if alpaca_price else "N/A"
            print(f"{symbol:<8} {fmp_str:<12} {alpaca_str:<14} {'N/A':<10} {'N/A':<8}")
    
    # Also show raw FMP response for debugging
    print("\n" + "=" * 60)
    print("Raw FMP Quote Data (first symbol):")
    print("=" * 60)
    
    first_symbol = symbols[0]
    raw = fmp._get(f"quote/{first_symbol}")
    if raw and len(raw) > 0:
        q = raw[0]
        print(f"  symbol: {q.get('symbol')}")
        print(f"  price: {q.get('price')}")
        print(f"  previousClose: {q.get('previousClose')}")
        print(f"  open: {q.get('open')}")
        print(f"  dayLow: {q.get('dayLow')}")
        print(f"  dayHigh: {q.get('dayHigh')}")
        print(f"  volume: {q.get('volume')}")
        print(f"  change: {q.get('change')}")
        print(f"  changesPercentage: {q.get('changesPercentage')}")
        print(f"  timestamp: {q.get('timestamp')}")


if __name__ == "__main__":
    # Test with current positions and some reference symbols
    test_symbols = ["DASH", "OS", "AAPL", "SPY", "TSLA"]
    compare_quotes(test_symbols)
