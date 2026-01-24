#!/usr/bin/env python3
"""Test TradingView library for ground truth quotes."""
from tradingview_ta import TA_Handler, Interval, Exchange

def test_tradingview(symbol):
    try:
        handler = TA_Handler(
            symbol=symbol,
            screener="america",
            exchange="NASDAQ",
            interval=Interval.INTERVAL_1_MINUTE
        )
        analysis = handler.get_analysis()
        
        print(f"Symbol: {symbol}")
        print(f"  Close: {analysis.indicators.get('close')}")
        print(f"  Open: {analysis.indicators.get('open')}")
        print(f"  High: {analysis.indicators.get('high')}")
        print(f"  Low: {analysis.indicators.get('low')}")
        print(f"  Volume: {analysis.indicators.get('volume')}")
        print(f"  Recommendation: {analysis.summary.get('RECOMMENDATION')}")
    except Exception as e:
        print(f"{symbol}: Error - {e}")

if __name__ == "__main__":
    for sym in ["BNAI", "RVYL", "IBRX"]:
        test_tradingview(sym)
        print()
