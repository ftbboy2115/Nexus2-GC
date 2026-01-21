"""
Sanity check: Compare 5 1-minute candles aggregated vs actual 5-minute candle
"""
import asyncio
from nexus2.adapters.market_data.alpaca_market_data import AlpacaMarketDataAdapter

async def test():
    adapter = AlpacaMarketDataAdapter()
    symbol = 'SPY'
    
    # Get 5 x 1-minute candles
    candles_1m = await adapter.get_intraday_bars(symbol, '1min', limit=5)
    
    # Get 1 x 5-minute candle
    candles_5m = await adapter.get_intraday_bars(symbol, '5min', limit=1)
    
    if candles_1m and candles_5m:
        # Aggregate 1m into synthetic 5m
        synthetic_open = candles_1m[0].open
        synthetic_high = max(c.high for c in candles_1m)
        synthetic_low = min(c.low for c in candles_1m)
        synthetic_close = candles_1m[-1].close
        synthetic_volume = sum(c.volume for c in candles_1m)
        
        actual_5m = candles_5m[0]
        
        print('=== 1-MINUTE CANDLES ===')
        for i, c in enumerate(candles_1m):
            print(f'{i+1}: O={c.open:.2f} H={c.high:.2f} L={c.low:.2f} C={c.close:.2f} V={c.volume}')
        
        print()
        print('=== SYNTHETIC 5-MIN ===')
        print(f'O={synthetic_open:.2f} H={synthetic_high:.2f} L={synthetic_low:.2f} C={synthetic_close:.2f} V={synthetic_volume}')
        
        print()
        print('=== ACTUAL 5-MIN ===')
        print(f'O={actual_5m.open:.2f} H={actual_5m.high:.2f} L={actual_5m.low:.2f} C={actual_5m.close:.2f} V={actual_5m.volume}')
        
        print()
        print('=== ALIGNMENT CHECK ===')
        print(f'Open match: {abs(synthetic_open - actual_5m.open) < 0.01}')
        print(f'High match: {abs(synthetic_high - actual_5m.high) < 0.01}')
        print(f'Low match: {abs(synthetic_low - actual_5m.low) < 0.01}')
        print(f'Close match: {abs(synthetic_close - actual_5m.close) < 0.01}')
    else:
        print('Failed to fetch candles')

if __name__ == "__main__":
    asyncio.run(test())
