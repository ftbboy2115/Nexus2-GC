"""
E2E Mock Trading Simulation Test

This script runs a complete end-to-end test of the mock trading simulation
without relying on the server (which reloads and clears state).

Run: python -m nexus2.tests.test_simulation_e2e
"""

import asyncio
import sys
from datetime import datetime
import pytz

# Set up path
sys.path.insert(0, ".")


async def run_e2e_test():
    print("=" * 60)
    print("E2E Mock Trading Simulation Test")
    print("=" * 60)
    
    # Step 1: Reset simulation
    print("\n📌 Step 1: Reset simulation environment")
    from nexus2.adapters.simulation import (
        reset_simulation_clock,
        reset_mock_market_data,
        get_simulation_clock,
        get_mock_market_data,
    )
    from nexus2.adapters.simulation.mock_broker import MockBroker
    
    ET = pytz.timezone("US/Eastern")
    
    # Reset clock to a specific date in the past
    start_date = datetime(2025, 9, 15, 9, 30)  # Sept 15, 2025 at market open
    clock = reset_simulation_clock(start_time=ET.localize(start_date))
    data = reset_mock_market_data()
    data.set_clock(clock)
    broker = MockBroker(initial_cash=100_000)
    # Note: MockBroker uses prices from set_price(), not clock
    
    print(f"   Clock: {clock.get_trading_day()}")
    print(f"   Cash: ${broker.get_account()['cash']:,.2f}")
    print(f"   Market hours: {clock.is_market_hours()}")
    
    # Step 2: Load historical data for multiple symbols
    print("\n📌 Step 2: Load historical FMP data")
    from nexus2.adapters.market_data.fmp_adapter import get_fmp_adapter
    
    fmp = get_fmp_adapter()
    symbols = ["NVDA", "AMD", "SMCI"]
    
    for symbol in symbols:
        bars = fmp.get_daily_bars(symbol, limit=150)
        if bars:
            bar_dicts = [{
                "date": bar.timestamp.strftime("%Y-%m-%d"),
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": bar.volume,
            } for bar in bars]
            count = data.load_data(symbol, bar_dicts)
            print(f"   {symbol}: {count} bars loaded (first: {bar_dicts[0]['date']}, last: {bar_dicts[-1]['date']})")
        else:
            print(f"   {symbol}: FAILED to load")
    
    # Step 3: Set clock to date within data range
    print("\n📌 Step 3: Set clock to date within data range")
    # Get first date from loaded data
    first_symbol = list(data._data.keys())[0]
    first_bars = data._data[first_symbol]
    if len(first_bars) > 30:
        target_date_str = first_bars[30].date  # 30 bars in for lookback
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d")
        clock.set_time(ET.localize(target_date.replace(hour=9, minute=30)))
        print(f"   Clock set to: {clock.get_trading_day()}")
    
    # Step 4: Test get_gainers
    print("\n📌 Step 4: Test MockMarketData.get_gainers()")
    gainers = data.get_gainers()
    print(f"   Gainers found: {len(gainers)}")
    for g in gainers[:5]:
        print(f"   - {g['symbol']}: +{g['change_percent']:.2f}%")
    
    # Step 5: Test get_actives
    print("\n📌 Step 5: Test MockMarketData.get_actives()")
    actives = data.get_actives()
    print(f"   Active stocks found: {len(actives)}")
    for a in actives[:5]:
        print(f"   - {a['symbol']}: vol={a['volume']:,}")
    
    # Step 6: Run scanner with sim_mode
    print("\n📌 Step 6: Run scanner with MockMarketData")
    from nexus2.domain.automation.services import create_unified_scanner_callback
    
    scanner_func = await create_unified_scanner_callback(
        min_quality=5,  # Lower threshold for testing
        max_stop_percent=10.0,
        stop_mode="atr",
        max_stop_atr=2.0,  # More lenient
        scan_modes=["ep", "breakout"],
        sim_mode=True,  # KEY: This injects MockMarketData
    )
    
    # Run scan
    print("   Running scan...")
    scan_result = await scanner_func()
    
    # Extract signals from result (may be UnifiedScanResult or list)
    if hasattr(scan_result, 'all_signals'):
        signals = scan_result.all_signals
    elif hasattr(scan_result, 'signals'):
        signals = scan_result.signals
    elif isinstance(scan_result, list):
        signals = scan_result
    else:
        signals = []
    
    print(f"   Signals found: {len(signals)}")
    for sig in signals[:5]:
        if isinstance(sig, dict):
            print(f"   - {sig.get('symbol', 'N/A')}: {sig.get('signal_type', 'N/A')}")
        else:
            print(f"   - {sig}")
    
    # Step 7: Summary
    print("\n" + "=" * 60)
    print("E2E TEST RESULTS")
    print("=" * 60)
    print(f"✅ Clock functional: {clock.get_trading_day()}")
    print(f"✅ MockMarketData loaded: {len(data.get_symbols())} symbols")
    print(f"{'✅' if gainers else '⚠️'} get_gainers: {len(gainers)} stocks")
    print(f"{'✅' if actives else '⚠️'} get_actives: {len(actives)} stocks")
    print(f"{'✅' if signals else '⚠️'} Scanner signals: {len(signals)} signals")
    print(f"✅ MockBroker: ${broker.get_account()['cash']:,.2f}")
    
    if len(gainers) == 0:
        print("\n⚠️ NOTE: No gainers found. This could be because:")
        print("   - All loaded stocks were down/flat on the sim date")
        print("   - Try advancing the clock to find a day with gainers")
    
    return {
        "clock": clock.get_trading_day(),
        "symbols": data.get_symbols(),
        "gainers": len(gainers),
        "actives": len(actives),
        "signals": len(signals),
    }


if __name__ == "__main__":
    result = asyncio.run(run_e2e_test())
    print(f"\n✅ Test complete: {result}")
