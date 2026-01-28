#!/usr/bin/env python3
"""Check news sources for HIND to diagnose catalyst gap."""
import asyncio
import sys
sys.path.insert(0, '/root/Nexus2')

from adapters.market_data.fmp_adapter import FMPAdapter
from adapters.market_data.alpaca_adapter import AlpacaAdapter

async def main():
    symbol = "HIND"
    
    print(f"=== FMP News for {symbol} ===")
    fmp = FMPAdapter()
    try:
        news = await fmp.get_news(symbol)
        if not news:
            print("No news found")
        for n in news[:10]:
            print(f"{n.published_at}: {n.title}")
    except Exception as e:
        print(f"FMP Error: {e}")
    
    print(f"\n=== Alpaca News for {symbol} ===")
    alpaca = AlpacaAdapter()
    try:
        news = await alpaca.get_news(symbol)
        if not news:
            print("No news found")
        for n in news[:10]:
            print(f"{n.published_at}: {n.title}")
    except Exception as e:
        print(f"Alpaca Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
