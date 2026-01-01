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
    
    # Step 3: Find a date with a BIG gainer (5%+) for EP testing
    print("\n📌 Step 3: Search for a date with 5%+ gainer for EP test")
    first_symbol = list(data._data.keys())[0]
    first_bars = data._data[first_symbol]
    
    best_date = None
    best_gainer = None
    best_change = 0
    
    # Search through dates starting at bar 30 (for lookback)
    for idx in range(30, len(first_bars) - 1):
        target_date_str = first_bars[idx].date
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d")
        clock.set_time(ET.localize(target_date.replace(hour=9, minute=30)))
        
        # Check for gainers on this date
        gainers = data.get_gainers()
        if gainers and gainers[0]['change_percent'] > best_change:
            best_change = gainers[0]['change_percent']
            best_date = target_date_str
            best_gainer = gainers[0]
            
            # Stop if we find a 5%+ gainer
            if best_change >= 5.0:
                print(f"   🎯 Found EP candidate! {gainers[0]['symbol']} +{best_change:.2f}% on {best_date}")
                break
    
    if best_date:
        target_date = datetime.strptime(best_date, "%Y-%m-%d")
        clock.set_time(ET.localize(target_date.replace(hour=9, minute=30)))
        print(f"   Clock set to: {clock.get_trading_day()} (best gainer: +{best_change:.2f}%)")
    else:
        print("   ⚠️ No significant gainers found in data range")
    
    # Step 4: Test get_gainers on best date
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
    
    # Step 6: Test EP scanner directly to debug
    print("\n📌 Step 6: Test EP scanner directly")
    from nexus2.domain.scanner.ep_scanner_service import EPScannerService, EPScanSettings
    
    # Create EP scanner with our MockMarketData
    ep_scanner = EPScannerService(
        settings=EPScanSettings(
            min_gap=3.0,  # Lowered from 5% for testing
            min_rvol=0.5,  # Lowered for testing
            min_price=5.0,
        ),
        market_data=data,  # Use our MockMarketData directly!
    )
    
    print("   Testing EP scanner with MockMarketData...")
    print(f"   - get_gainers() returns: {len(data.get_gainers())} stocks")
    print(f"   - Clock date: {clock.get_trading_day()}")
    
    # Manually test what EP scanner would do
    try:
        # Try to run the EP scan
        ep_result = ep_scanner.scan(verbose=True)  # Verbose for debug
        print(f"   EP scan result: {len(ep_result.candidates)} candidates, processed {ep_result.processed_count}")
        for r in ep_result.candidates[:5]:
            print(f"   - {r.symbol}: gap={r.gap_percent}%, status={r.status}")
    except Exception as e:
        print(f"   EP scan error: {e}")
        import traceback
        traceback.print_exc()
    
    # Step 7: Run unified scanner
    print("\n📌 Step 7: Run unified scanner with MockMarketData")
    from nexus2.domain.automation.services import create_unified_scanner_callback
    
    scanner_func = await create_unified_scanner_callback(
        min_quality=3,  # Lower threshold for testing
        max_stop_percent=15.0,
        stop_mode="atr",
        max_stop_atr=3.0,  # More lenient
        scan_modes=["ep"],  # Only EP for now
        sim_mode=True,  # KEY: This injects MockMarketData
    )
    
    # Debug: Check if MockMarketData singletons match
    from nexus2.adapters.simulation import get_mock_market_data as get_md
    service_data = get_md()
    print(f"   DEBUG: Test data id={id(data)}, service data id={id(service_data)}")
    print(f"   DEBUG: Test data symbols={data.get_symbols()}")
    print(f"   DEBUG: Service data symbols={service_data.get_symbols()}")
    
    # Run scan
    print("   Running unified scan...")
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
    
    # Show diagnostics (rejections)
    if hasattr(scan_result, 'diagnostics'):
        for diag in scan_result.diagnostics:
            print(f"   - {diag.scanner}: found={diag.candidates_found}, passed={diag.candidates_passed}")
            for rej in diag.rejections[:3]:
                print(f"     REJECTED: {rej.symbol} - {rej.reason} (threshold={rej.threshold}, actual={rej.actual_value})")
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
