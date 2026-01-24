#!/usr/bin/env python3
"""Test Yahoo Finance for ground truth quote."""
import yfinance as yf

def test_yahoo(symbol):
    t = yf.Ticker(symbol)
    info = t.info
    print(f"Symbol: {symbol}")
    print(f"  Regular Market Price: {info.get('regularMarketPrice', 'N/A')}")
    print(f"  Post Market Price: {info.get('postMarketPrice', 'N/A')}")
    print(f"  Pre Market Price: {info.get('preMarketPrice', 'N/A')}")
    print(f"  Current Price: {info.get('currentPrice', 'N/A')}")
    print(f"  Bid: {info.get('bid', 'N/A')}")
    print(f"  Ask: {info.get('ask', 'N/A')}")

if __name__ == "__main__":
    for sym in ["BNAI", "RVYL", "IBRX"]:
        test_yahoo(sym)
        print()
