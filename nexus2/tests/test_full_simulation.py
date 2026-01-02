"""
Full Simulation E2E Test

This test runs the REAL AutomationEngine with MockBroker to verify
the complete trading loop:
1. Scanner finds EP setups
2. Engine generates signals
3. Engine submits orders to MockBroker
4. MockBroker fills orders and creates positions
5. Time advances, stops are checked
6. P&L is calculated

Run: python -m nexus2.tests.test_full_simulation
"""

import asyncio
import sys
from datetime import datetime
from decimal import Decimal
import pytz

# Set up path
sys.path.insert(0, ".")


async def run_full_simulation():
    print("=" * 70)
    print("FULL SIMULATION E2E TEST")
    print("Testing: Scanner → Engine → MockBroker → Positions → P&L")
    print("=" * 70)
    
    ET = pytz.timezone("US/Eastern")
    
    # ========== STEP 1: Reset Simulation Environment ==========
    print("\n📌 Step 1: Reset simulation environment")
    from nexus2.adapters.simulation import (
        reset_simulation_clock,
        reset_mock_market_data,
        get_simulation_clock,
        get_mock_market_data,
    )
    from nexus2.adapters.simulation.mock_broker import MockBroker
    
    # Reset clock to a date well within our data range
    start_date = datetime(2025, 9, 15, 9, 30)
    clock = reset_simulation_clock(start_time=ET.localize(start_date))
    data = reset_mock_market_data()
    data.set_clock(clock)
    broker = MockBroker(initial_cash=100_000)
    
    print(f"   Clock: {clock.get_trading_day()}")
    print(f"   Cash: ${broker.get_account()['cash']:,.2f}")
    
    # ========== STEP 2: Load Historical Data ==========
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
            print(f"   {symbol}: {count} bars loaded")
    
    # ========== STEP 3: Find a Day with Big Gainers ==========
    print("\n📌 Step 3: Search for a date with 5%+ gainer")
    first_symbol = list(data._data.keys())[0]
    first_bars = data._data[first_symbol]
    
    best_date = None
    best_change = 0
    
    for idx in range(30, len(first_bars) - 1):
        target_date_str = first_bars[idx].date
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d")
        clock.set_time(ET.localize(target_date.replace(hour=9, minute=30)))
        
        gainers = data.get_gainers()
        if gainers and gainers[0]['change_percent'] > best_change:
            best_change = gainers[0]['change_percent']
            best_date = target_date_str
            if best_change >= 5.0:
                break
    
    if best_date:
        target_date = datetime.strptime(best_date, "%Y-%m-%d")
        clock.set_time(ET.localize(target_date.replace(hour=9, minute=30)))
        print(f"   🎯 Clock set to: {best_date} (best gainer: +{best_change:.2f}%)")
    
    # Set broker prices for this date
    for symbol in data.get_symbols():
        price = data.get_current_price(symbol)
        if price:
            broker.set_price(symbol, price)
    
    # ========== STEP 4: Create AutomationEngine with MockBroker ==========
    print("\n📌 Step 4: Create AutomationEngine with sim callbacks")
    from nexus2.domain.automation.engine import AutomationEngine, EngineConfig
    from nexus2.domain.automation.services import create_unified_scanner_callback
    
    # Create scanner callback (uses MockMarketData)
    scanner_func = await create_unified_scanner_callback(
        min_quality=3,
        max_stop_percent=15.0,
        stop_mode="atr",
        max_stop_atr=3.0,
        scan_modes=["ep"],
        sim_mode=True,
    )
    
    # Create order callback that routes to MockBroker
    async def mock_order_callback(symbol: str, shares: int, stop_price: float, setup_type: str):
        """Route orders to MockBroker instead of Alpaca."""
        print(f"   📝 Order: {symbol} x {shares} @ market, stop=${stop_price:.2f}")
        
        result = broker.submit_bracket_order(
            symbol=symbol,
            side="buy",
            qty=shares,
            stop_price=stop_price,
        )
        
        if result.is_accepted:
            print(f"   ✅ Filled: {shares} @ ${result.avg_fill_price:.2f}")
            return {
                "symbol": symbol,
                "shares": shares,
                "fill_price": result.avg_fill_price,
                "order_id": result.entry_order_id,
            }
        else:
            print(f"   ❌ Rejected: {result.error}")
            return None
    
    # Create engine with sim callbacks
    config = EngineConfig(
        risk_per_trade=Decimal("250"),  # $250 risk per trade
        max_positions=3,
        min_quality_score=3,
    )
    
    engine = AutomationEngine(
        config=config,
        scanner_func=scanner_func,
        order_func=mock_order_callback,
    )
    
    print(f"   Engine configured: risk=${config.risk_per_trade}, max_positions={config.max_positions}")
    
    # ========== STEP 5: Run Scanner Cycle ==========
    print("\n📌 Step 5: Run scanner cycle")
    scan_result = await engine.run_scan_cycle()
    
    if hasattr(scan_result, 'signals'):
        signals = scan_result.signals
    elif hasattr(scan_result, 'all_signals'):
        signals = scan_result.all_signals
    elif isinstance(scan_result, list):
        signals = scan_result
    else:
        signals = []
    
    print(f"   Signals found: {len(signals)}")
    
    # ========== STEP 6: Process Signals (Submit Orders) ==========
    print("\n📌 Step 6: Process signals → submit orders")
    orders_placed = 0
    
    for sig in signals[:3]:  # Process top 3 signals
        print(f"   Processing: {sig.symbol}, quality={sig.quality_score}")
        result = await engine.process_signal(sig)
        if result:
            orders_placed += 1
    
    print(f"   Orders placed: {orders_placed}")
    
    # ========== STEP 7: Check Positions ==========
    print("\n📌 Step 7: Check MockBroker positions")
    positions = broker.get_positions()
    print(f"   Positions: {len(positions)}")
    for pos in positions:
        print(f"   - {pos['symbol']}: {pos['qty']} shares @ ${pos['avg_price']:.2f}, stop=${pos.get('stop_price', 'N/A')}")
    
    # ========== STEP 8: Advance Time and Check Stops ==========
    print("\n📌 Step 8: Advance time 1 day and check stops")
    old_date = clock.get_trading_day()
    clock.advance(days=1)
    new_prices = data.advance_day()
    
    # Update broker prices
    for sym, price in new_prices.items():
        broker.set_price(sym, price)
    
    print(f"   Time: {old_date} → {clock.get_trading_day()}")
    print(f"   New prices: {new_prices}")
    
    # Check for stop triggers
    for symbol in [p['symbol'] for p in positions]:
        broker._check_stop_orders(symbol)
    
    # ========== STEP 9: Final Report ==========
    print("\n" + "=" * 70)
    print("SIMULATION RESULTS")
    print("=" * 70)
    
    account = broker.get_account()
    final_positions = broker.get_positions()
    
    print(f"✅ Clock: {clock.get_trading_day()}")
    print(f"✅ Signals found: {len(signals)}")
    print(f"✅ Orders placed: {orders_placed}")
    print(f"✅ Positions: {len(final_positions)}")
    print(f"✅ Cash: ${account['cash']:,.2f}")
    print(f"✅ Equity: ${account['portfolio_value']:,.2f}")
    print(f"✅ Unrealized P&L: ${account['unrealized_pnl']:,.2f}")
    print(f"✅ Realized P&L: ${account['realized_pnl']:,.2f}")
    
    return {
        "signals": len(signals),
        "orders": orders_placed,
        "positions": len(final_positions),
        "cash": account['cash'],
        "equity": account['portfolio_value'],
        "unrealized_pnl": account['unrealized_pnl'],
        "realized_pnl": account['realized_pnl'],
    }


if __name__ == "__main__":
    result = asyncio.run(run_full_simulation())
    print(f"\n✅ Simulation complete: {result}")
